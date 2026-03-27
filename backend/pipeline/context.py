"""Pipeline 数据结构：每个 STM32 设备独享一套 Context。

见设计稿第 10 节：每设备独立 Pipeline，包含 4 条 asyncio 队列和 4 个协程 Task。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeviceStats:
    """运行时统计数据（供 /ws/health 推送使用）。"""
    fps: float = 0.0                # 近 1 秒平均推理帧率
    dropped_frames: int = 0        # 本分钟累计丢帧数（因令牌桶限流或队列满）
    avg_inference_ms: float = 0.0  # 本分钟平均推理耗时（毫秒）
    vehicle_count: int = 0         # 最新帧车辆数快照
    alert_level: int = 0           # 当前最高预警等级（0=正常）
    degradation_level: int = 0     # 性能降级等级（0~3，见设计稿 11.1 节）
    # 内部计算用
    _frame_times: list = field(default_factory=list)
    _inference_ms_buf: list = field(default_factory=list)

    def record_frame(self, inference_ms: float) -> None:
        now = time.monotonic()
        self._frame_times.append(now)
        self._inference_ms_buf.append(inference_ms)
        # 保留近 1 分钟内数据
        cutoff = now - 60.0
        self._frame_times = [t for t in self._frame_times if t > cutoff]
        self._inference_ms_buf = self._inference_ms_buf[-len(self._frame_times):]
        # 更新 fps（近 1 秒）
        recent = [t for t in self._frame_times if t > now - 1.0]
        self.fps = float(len(recent))
        # 更新均值推理耗时
        if self._inference_ms_buf:
            self.avg_inference_ms = round(
                sum(self._inference_ms_buf) / len(self._inference_ms_buf), 1
            )


@dataclass
class DevicePipelineContext:
    """每个设备的独立 Pipeline 上下文（见设计稿 10.1 节）。"""

    device_id: int
    device_ip: str

    # 四条 asyncio 队列，maxsize=2 防止内存堆积
    raw_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2))
    result_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2))
    ws_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2))
    db_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2))

    # 四个协程 Task（启动后赋值）
    inference_task: Optional[asyncio.Task] = field(default=None)
    dispatch_task: Optional[asyncio.Task] = field(default=None)
    ws_task: Optional[asyncio.Task] = field(default=None)
    db_task: Optional[asyncio.Task] = field(default=None)

    # 设备配置热缓存（PUT settings 后调用 invalidate_settings_cache 清空）
    settings_cache: dict = field(default_factory=dict)

    # 运行时统计
    stats: DeviceStats = field(default_factory=DeviceStats)

    # 异常停车检测状态：{tracking_id: {"last_center": (x,y), "still_since": float}}
    # 与 Context 同生命周期，设备断线重连后全部清零（见设计稿 10.1 节说明）
    parked_tracker: dict = field(default_factory=dict)

    # 虚拟线双向计数：{tracking_id: {"prev_cy": int, "side": str}}
    crossing_tracker: dict = field(default_factory=dict)

    # 本次 TCP 连接内累计过线计数
    passed_in_count: int = 0
    passed_out_count: int = 0

    # TCP 连接建立时间（用于 connection_session 记录）
    connected_at: float = field(default_factory=time.monotonic)

    # 令牌桶状态（fps_limit 限流，见设计稿 11.2 节）
    _token_bucket: float = field(default=0.0)
    _last_token_time: float = field(default_factory=time.monotonic)

    def consume_token(self, fps_limit: int) -> bool:
        """令牌桶限流：返回 True 表示本帧允许处理，False 表示丢帧。"""
        now = time.monotonic()
        elapsed = now - self._last_token_time
        self._token_bucket = min(fps_limit, self._token_bucket + elapsed * fps_limit)
        self._last_token_time = now
        if self._token_bucket >= 1.0:
            self._token_bucket -= 1.0
            return True
        self.stats.dropped_frames += 1
        return False

    async def cancel_all_tasks(self) -> None:
        """取消并等待全部协程 Task 结束（设备断线时调用）。"""
        tasks = [
            t for t in [
                self.inference_task,
                self.dispatch_task,
                self.ws_task,
                self.db_task,
            ]
            if t is not None
        ]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
