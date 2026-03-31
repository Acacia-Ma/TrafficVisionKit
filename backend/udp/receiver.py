"""Async UDP server that receives STM32 MC5640 JPEG stream and feeds the
existing pipeline infrastructure.

Design overview
---------------
- One asyncio.DatagramProtocol listens on UDP_HOST:UDP_PORT.
- Devices are identified by their source IP address (same lookup logic as the
  TCP server so the same devices table is reused with no schema changes).
- First datagram from a new IP triggers on_device_connected in the
  PipelineManager and creates a DeviceAssembler with its own jitter-buffer
  drain task.
- A watchdog coroutine fires on_device_disconnected after UDP_IDLE_TIMEOUT_S
  seconds of silence per device.
- Complete, validated JPEG frames are placed on ctx.raw_queue via the
  DeviceAssembler drain task.  The inference / dispatch / ws / db pipeline
  tasks run unchanged.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

from sqlalchemy import select

from database import AsyncSessionLocal
from models import Device, SystemLog
from datetime import datetime, timezone

from udp.assembler import DeviceAssembler

logger = logging.getLogger(__name__)

# Seconds of silence before a UDP device is considered offline.
UDP_IDLE_TIMEOUT_S: float = 30.0

# How often the watchdog checks for idle devices (seconds).
WATCHDOG_INTERVAL_S: float = 5.0


class _UDPProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol.  Delegates all business logic to UDPReceiver."""

    def __init__(self, receiver: "UDPReceiver") -> None:
        self._receiver = receiver

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._receiver._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("[UDP] transport error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("[UDP] transport closed")


class UDPReceiver:
    """Single-instance UDP server managed by main.py lifespan.

    Usage::
        receiver = UDPReceiver(host="0.0.0.0", port=8080)
        receiver.set_pipeline_manager(pipeline_manager)
        await receiver.start()
        # ... app runs ...
        await receiver.stop()
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._pipeline_manager = None
        self._transport: asyncio.DatagramTransport | None = None

        # ip -> DeviceAssembler
        self._assemblers: Dict[str, DeviceAssembler] = {}
        # ip -> device_id (cached after first DB lookup)
        self._ip_to_device: Dict[str, int] = {}
        # ip -> last_seen monotonic timestamp
        self._last_seen: Dict[str, float] = {}

        self._watchdog_task: asyncio.Task | None = None
        self._pending_connections: set[str] = set()  # IPs awaiting DB lookup

    def set_pipeline_manager(self, manager) -> None:
        self._pipeline_manager = manager

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self),
            local_addr=(self._host, self._port),
        )
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(), name="udp_watchdog"
        )
        logger.info("[UDP] listening on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        # Disconnect all active devices.
        for ip in list(self._assemblers.keys()):
            await self._disconnect_device(ip, reason="server shutdown")

        if self._transport:
            self._transport.close()
        logger.info("[UDP] stopped")

    # ── Hot path (called from DatagramProtocol, must be non-blocking) ────────

    def _on_datagram(self, data: bytes, addr: tuple) -> None:
        """Called by asyncio for every incoming UDP datagram."""
        src_ip: str = addr[0]
        self._last_seen[src_ip] = time.monotonic()

        if src_ip in self._assemblers:
            # Fast path: device already connected.
            self._assemblers[src_ip].feed(data)
            return

        # Slow path: first datagram from this IP – kick off async connection
        # handling without blocking the event loop.
        if src_ip not in self._pending_connections:
            self._pending_connections.add(src_ip)
            asyncio.create_task(
                self._handle_new_device(src_ip, data),
                name=f"udp_connect_{src_ip}",
            )

    # ── Async device management ──────────────────────────────────────────────

    async def _handle_new_device(self, src_ip: str, first_packet: bytes) -> None:
        """Look up device by IP; if registered, start pipeline + assembler."""
        try:
            device_id = await self._lookup_device(src_ip)
            if device_id is None:
                logger.warning("[UDP] unknown device IP=%s, ignored", src_ip)
                await self._write_log(
                    "warning",
                    f"未知设备 UDP 包（IP: {src_ip}），已忽略",
                )
                return

            # Register.
            self._ip_to_device[src_ip] = device_id

            # Start pipeline.
            if self._pipeline_manager:
                await self._pipeline_manager.on_device_connected(device_id, src_ip)

            # Create assembler and wire it to the pipeline's raw_queue.
            ctx = (
                self._pipeline_manager.get_context(device_id)
                if self._pipeline_manager
                else None
            )
            if ctx is None:
                logger.error("[UDP] device %d has no pipeline context", device_id)
                return

            assembler = DeviceAssembler(device_id=device_id, raw_queue=ctx.raw_queue)
            assembler.start()
            self._assemblers[src_ip] = assembler

            await self._write_log(
                "connected",
                f"设备 {device_id} UDP 流连接（IP: {src_ip}）",
                device_id,
            )
            logger.info("[UDP] device %d IP=%s connected", device_id, src_ip)
            print(f"[UDP] ✓ device_id={device_id} IP={src_ip} connected", flush=True)

            # Process the first packet that triggered this path.
            assembler.feed(first_packet)

            # Resolve any device_offline alert.
            from services.alert_resolver import alert_resolver
            await alert_resolver.on_device_online(device_id)

        finally:
            self._pending_connections.discard(src_ip)

    async def _disconnect_device(self, src_ip: str, reason: str = "idle timeout") -> None:
        """Tear down pipeline for a device that went silent."""
        assembler = self._assemblers.pop(src_ip, None)
        device_id = self._ip_to_device.pop(src_ip, None)
        self._last_seen.pop(src_ip, None)

        if assembler:
            await assembler.stop()
            logger.info(
                "[UDP] device %s frames_received=%d frames_dropped=%d",
                src_ip,
                assembler.frames_received,
                assembler.frames_dropped,
            )

        if device_id is not None:
            await self._write_log(
                "disconnected",
                f"设备 {device_id} UDP 流断开（原因: {reason}）",
                device_id,
            )
            if self._pipeline_manager:
                await self._pipeline_manager.on_device_disconnected(device_id)

            from services.alert_resolver import alert_resolver
            from services.websocket_manager import ws_manager
            await alert_resolver.on_device_offline(device_id)
            await ws_manager.push_device_offline(device_id, reason)

            logger.info("[UDP] device %d IP=%s disconnected (%s)", device_id, src_ip, reason)
            print(f"[UDP] ✗ device_id={device_id} IP={src_ip} disconnected ({reason})", flush=True)

    # ── Watchdog ─────────────────────────────────────────────────────────────

    async def _watchdog_loop(self) -> None:
        """Periodically disconnect devices that have gone silent."""
        try:
            while True:
                await asyncio.sleep(WATCHDOG_INTERVAL_S)
                now = time.monotonic()
                stale = [
                    ip
                    for ip, ts in list(self._last_seen.items())
                    if (now - ts) > UDP_IDLE_TIMEOUT_S and ip in self._assemblers
                ]
                for ip in stale:
                    logger.info(
                        "[UDP] device IP=%s silent for >%.0fs, disconnecting",
                        ip, UDP_IDLE_TIMEOUT_S,
                    )
                    await self._disconnect_device(ip, reason="idle timeout")
        except asyncio.CancelledError:
            raise

    # ── Database helpers ─────────────────────────────────────────────────────

    @staticmethod
    async def _lookup_device(ip: str) -> int | None:
        """Return device_id for the given IP, or None if not registered."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Device).where(Device.ip_address == ip)
            )
            device = result.scalar_one_or_none()
            return device.id if device is not None else None

    @staticmethod
    async def _write_log(
        event_type: str,
        message: str,
        device_id: int | None = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            session.add(SystemLog(
                device_id=device_id,
                event_type=event_type,
                message=message,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ))
            await session.commit()
