"""分发协程：从 result_queue 取推理结果 → 同时写 ws_queue 和 db_queue。

Phase 3：仅做分发，Phase 4 会在此处接入计数、停车检测、预警逻辑。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pipeline.context import DevicePipelineContext

logger = logging.getLogger(__name__)


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


async def dispatch_loop(ctx: DevicePipelineContext) -> None:
    """分发协程主循环。"""
    logger.info(f"[DispatchLoop] device {ctx.device_id} started")

    # ── Phase 4 将在此处注入计数器和预警解除器 ──────────────────────────────────
    # from inference.counter import count_crossings
    # from inference.parking_detector import ParkingDetector
    # from services.alert_resolver import alert_resolver
    # parking_detector = ParkingDetector()
    # ─────────────────────────────────────────────────────────────────────────────

    seq = 0

    while True:
        try:
            data: dict = await ctx.result_queue.get()
        except asyncio.CancelledError:
            break

        seq += 1
        results = data.get("results", [])
        inference_ms = data.get("inference_ms", 0.0)

        # 更新车辆数快照
        ctx.stats.vehicle_count = len(results)

        # 读取热缓存的计数线配置（Phase 4 会用到）
        line_y = ctx.settings_cache.get("line_y", 240)

        # ── Phase 4 钩子（占位，当前直接跳过业务逻辑）──────────────────────────
        # passed_in, passed_out = count_crossings(results, line_y, ctx.crossing_tracker)
        # ctx.passed_in_count += passed_in
        # ctx.passed_out_count += passed_out
        # parked_ids = parking_detector.check_all(results, ctx.parked_tracker, ...)
        # await alert_resolver.check_and_resolve(ctx.device_id, results, ctx.stats)
        # ─────────────────────────────────────────────────────────────────────────

        timestamp = _utcnow_str()

        # 构造 WebSocket 推送消息（stream_frame，见设计稿 5.2 节）
        ws_msg = {
            "type": "stream_frame",
            "device_id": ctx.device_id,
            "timestamp": timestamp,
            "frame": {
                "data": data.get("frame_b64", ""),
                "width": data.get("width", 640),
                "height": data.get("height", 480),
                "seq": seq,
            },
            "detection": {
                "vehicle_count": len(results),
                "passed_count": ctx.passed_in_count + ctx.passed_out_count,
                "passed_in_count": ctx.passed_in_count,
                "passed_out_count": ctx.passed_out_count,
                "alert_level": ctx.stats.alert_level,
                "vehicles": [
                    {
                        "tracking_id": r.tracking_id,
                        "class_id": r.class_id,
                        "class_name": r.class_name,
                        "confidence": round(r.confidence, 2),
                        "bbox": list(r.bbox),
                        "is_parked": False,  # Phase 4 填充
                    }
                    for r in results
                ],
                "line_y": line_y,
                "inference_ms": inference_ms,
            },
        }

        # 非阻塞写入 ws_queue
        try:
            ctx.ws_queue.put_nowait(ws_msg)
        except asyncio.QueueFull:
            pass

        # 构造 DB 写入任务（Phase 5 的 db_write_loop 会消费）
        db_task = {
            "device_id": ctx.device_id,
            "timestamp": timestamp,
            "vehicle_count": len(results),
            "inference_ms": inference_ms,
            "passed_in": 0,   # Phase 4 填充
            "passed_out": 0,  # Phase 4 填充
        }
        try:
            ctx.db_queue.put_nowait(db_task)
        except asyncio.QueueFull:
            pass

    logger.info(f"[DispatchLoop] device {ctx.device_id} stopped")
