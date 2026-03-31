"""UDP JPEG frame assembler with two-level smooth delivery.

Level 1 - Fragment assembly window
    Holds incoming UDP chunks for a frame.
    If all chunks of a frame arrive within CHUNK_DEADLINE_S, the frame is
    validated (must start with FF D8 and end with FF D9) and promoted to the
    jitter buffer.  Frames that miss the deadline are silently dropped so that
    a single lost packet never freezes the display.

Level 2 - Jitter buffer (playback queue)
    A bounded asyncio.Queue of depth JITTER_DEPTH.  A per-device drain task
    reads one complete frame every (1 / TARGET_FPS) seconds and writes it to
    the pipeline's raw_queue.

    Advantages:
    - Output is paced at a steady rate regardless of bursty UDP arrival.
    - Partial / corrupt JPEG never reaches the inference engine.
    - No frame_id is ever emitted twice (ghosting prevention).
    - If the jitter buffer is empty the drain cycle is simply skipped
      (no stale frame is repeated).
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Wire protocol constants ─────────────────────────────────────────────────
# Magic bytes that prefix every UDP datagram from the STM32
MAGIC0: int = 0xA5
MAGIC1: int = 0x5A
# Header layout after the 2 magic bytes:
# frame_id(u32) chunk_idx(u16) chunk_cnt(u16) jpeg_len(u32) payload_len(u16)
_HDR = struct.Struct("<IHHIH")
HDR_TOTAL: int = 2 + _HDR.size  # 18 bytes total before payload

# ── Tuning knobs ────────────────────────────────────────────────────────────
# How long to wait for all chunks of a frame before giving up (seconds).
# At 100 Mbps local LAN a 20 KB frame (20 chunks × 1016 B) takes ~1.6 ms;
# 500 ms is extremely generous – covers any realistic jitter.
CHUNK_DEADLINE_S: float = 0.5

# Maximum in-flight (incomplete) frames tracked simultaneously per device.
# Old ones are evicted first-in-first-out if this is exceeded.
MAX_PENDING: int = 8

# Depth of the per-device jitter buffer (complete frames waiting to be sent).
# At TARGET_FPS = 12 this is ~2 frames = ~167 ms lookahead.
JITTER_DEPTH: int = 3

# Target output frame rate to the inference pipeline.
# The drain task sleeps 1/TARGET_FPS seconds between each frame push.
# The pipeline's own token-bucket (fps_limit) provides a second gate.
TARGET_FPS: float = 12.0


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class _FrameAssembly:
    """In-flight JPEG frame being assembled from UDP chunks."""
    frame_id: int
    chunk_cnt: int
    jpeg_len: int
    parts: List[Optional[bytes]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.parts = [None] * self.chunk_cnt

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > CHUNK_DEADLINE_S

    def add_chunk(self, idx: int, data: bytes) -> bool:
        """Return True when all chunks have arrived."""
        if 0 <= idx < self.chunk_cnt:
            self.parts[idx] = data
        return all(p is not None for p in self.parts)

    def build(self) -> bytes:
        return b"".join(p if p is not None else b"" for p in self.parts)


class DeviceAssembler:
    """Per-device stateful assembler + jitter buffer.

    Lifecycle:
        assembler = DeviceAssembler(device_id, raw_queue)
        assembler.start()          # starts drain task
        assembler.feed(data)       # call from UDP callback
        await assembler.stop()     # cancels drain task
    """

    def __init__(self, device_id: int, raw_queue: asyncio.Queue) -> None:
        self.device_id = device_id
        self._raw_queue = raw_queue
        self._pending: Dict[int, _FrameAssembly] = {}
        self._last_emitted_id: int = -1
        self._jitter_buf: asyncio.Queue[bytes] = asyncio.Queue(maxsize=JITTER_DEPTH)
        self._drain_task: Optional[asyncio.Task] = None
        self.frames_received: int = 0
        self.frames_dropped: int = 0

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background drain task (call from asyncio context)."""
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(
                self._drain_loop(),
                name=f"udp_drain_{self.device_id}",
            )

    async def stop(self) -> None:
        """Cancel the drain task and wait for it to finish."""
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
        self._drain_task = None
        self._pending.clear()

    def feed(self, data: bytes) -> None:
        """Feed a raw UDP datagram.  Call from the protocol's datagram_received."""
        jpeg = self._parse_and_assemble(data)
        if jpeg is None:
            return
        # Non-blocking: if jitter buffer is full, drop the oldest frame and
        # insert the new one so the buffer always holds the freshest content.
        if self._jitter_buf.full():
            try:
                self._jitter_buf.get_nowait()
                self.frames_dropped += 1
            except asyncio.QueueEmpty:
                pass
        try:
            self._jitter_buf.put_nowait(jpeg)
        except asyncio.QueueFull:
            self.frames_dropped += 1

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _parse_and_assemble(self, data: bytes) -> Optional[bytes]:
        """Parse packet, update assembly, return complete JPEG or None."""
        if len(data) < HDR_TOTAL:
            return None
        if data[0] != MAGIC0 or data[1] != MAGIC1:
            return None
        try:
            frame_id, chunk_idx, chunk_cnt, jpeg_len, payload_len = _HDR.unpack_from(data, 2)
        except struct.error:
            return None

        if chunk_cnt == 0 or chunk_idx >= chunk_cnt or payload_len == 0:
            return None
        if len(data) < HDR_TOTAL - 2 + payload_len:  # HDR_TOTAL includes 2-byte magic
            return None
        payload = data[16: 16 + payload_len]

        # Silently discard frames that we have already emitted.
        if 0 <= self._last_emitted_id < frame_id - MAX_PENDING * 4:
            # Jump in frame_id (device restarted?) – reset tracking.
            self._last_emitted_id = -1
            self._pending.clear()
        if frame_id <= self._last_emitted_id:
            return None

        # Expire timed-out assemblies before adding new data.
        self._expire_pending()

        # Get or create assembly slot.
        if frame_id not in self._pending:
            if len(self._pending) >= MAX_PENDING:
                # Evict oldest frame.
                oldest = min(self._pending.keys())
                logger.debug(
                    "[UDP] device %d evict frame %d (pending full)",
                    self.device_id, oldest,
                )
                del self._pending[oldest]
            self._pending[frame_id] = _FrameAssembly(
                frame_id=frame_id,
                chunk_cnt=chunk_cnt,
                jpeg_len=jpeg_len,
            )

        asm = self._pending[frame_id]
        complete = asm.add_chunk(chunk_idx, payload)
        if not complete:
            return None

        # All chunks collected – build and validate.
        jpeg = asm.build()
        del self._pending[frame_id]
        self._last_emitted_id = frame_id

        if not self._is_valid_jpeg(jpeg):
            logger.debug(
                "[UDP] device %d frame %d invalid JPEG (len=%d), dropped",
                self.device_id, frame_id, len(jpeg),
            )
            self.frames_dropped += 1
            return None

        self.frames_received += 1
        return jpeg

    @staticmethod
    def _is_valid_jpeg(data: bytes) -> bool:
        """Strict JPEG validation: SOI must be FF D8, EOI must be FF D9."""
        return (
            len(data) >= 4
            and data[0] == 0xFF and data[1] == 0xD8
            and data[-2] == 0xFF and data[-1] == 0xD9
        )

    def _expire_pending(self) -> None:
        """Drop assembly slots that have exceeded the chunk deadline."""
        expired = [fid for fid, asm in self._pending.items() if asm.is_expired]
        for fid in expired:
            logger.debug(
                "[UDP] device %d frame %d expired (%.0f ms), dropped",
                self.device_id, fid,
                (time.monotonic() - self._pending[fid].created_at) * 1000,
            )
            del self._pending[fid]
            self.frames_dropped += 1

    # ── Drain loop ───────────────────────────────────────────────────────────

    async def _drain_loop(self) -> None:
        """Pace complete frames to raw_queue at TARGET_FPS.

        Sleeping for exactly 1/TARGET_FPS between outputs turns an irregular
        burst of incoming UDP frames into a smooth, evenly-spaced stream for
        the YOLO inference loop.  If the jitter buffer is momentarily empty
        the cycle is skipped (no stale frame is repeated, solving ghosting).
        If raw_queue is full the frame is discarded (backpressure safety).
        """
        interval = 1.0 / TARGET_FPS
        logger.info("[UDP] device %d drain task started (%.1f fps)", self.device_id, TARGET_FPS)
        try:
            while True:
                t0 = time.monotonic()
                try:
                    jpeg = self._jitter_buf.get_nowait()
                    try:
                        self._raw_queue.put_nowait(jpeg)
                    except asyncio.QueueFull:
                        # Pipeline busy – discard rather than block.
                        self.frames_dropped += 1
                except asyncio.QueueEmpty:
                    # Nothing ready yet – skip, do not repeat old frame.
                    pass

                # Sleep for the remainder of this frame interval.
                elapsed = time.monotonic() - t0
                sleep_s = max(0.0, interval - elapsed)
                await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            logger.info("[UDP] device %d drain task stopped", self.device_id)
            raise
