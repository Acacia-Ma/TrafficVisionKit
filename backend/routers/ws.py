"""WebSocket 路由骨架（Phase 2）。
Phase 3 会在此基础上注入 PipelineManager，实现实时推送。

路径：
  /ws/stream/{device_id}  — 实时视频帧 + 检测结果（见设计稿 5.2 节）
  /ws/health              — 服务端健康数据（每秒广播）
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from core.security import decode_access_token

router = APIRouter(tags=["websocket"])


class WebSocketManager:
    """管理所有前端 WebSocket 连接，内部按 device_id 分组。"""

    def __init__(self) -> None:
        # device_id → list of WebSocket
        self._stream: dict[int, list[WebSocket]] = {}
        # 健康数据订阅者
        self._health: list[WebSocket] = []

    async def connect_stream(self, device_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._stream.setdefault(device_id, []).append(ws)

    def disconnect_stream(self, device_id: int, ws: WebSocket) -> None:
        conns = self._stream.get(device_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast_stream(self, device_id: int, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._stream.get(device_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_stream(device_id, ws)

    async def connect_health(self, ws: WebSocket) -> None:
        await ws.accept()
        self._health.append(ws)

    def disconnect_health(self, ws: WebSocket) -> None:
        if ws in self._health:
            self._health.remove(ws)

    async def broadcast_health(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._health):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_health(ws)


# 全局单例（Phase 3 的 PipelineManager 会持有此对象的引用）
ws_manager = WebSocketManager()


def _verify_ws_token(token: str | None) -> dict | None:
    """验证 WebSocket URL query 参数中的 access_token。"""
    if not token:
        return None
    return decode_access_token(token)


@router.websocket("/ws/stream/{device_id}")
async def ws_stream(
    websocket: WebSocket,
    device_id: int,
    token: str | None = Query(default=None),
) -> None:
    """实时视频帧 + 检测结果推送。Phase 3 填充推理数据，Phase 2 仅做鉴权和心跳响应。"""
    payload = _verify_ws_token(token)
    if payload is None:
        await websocket.close(code=4401)
        return

    await ws_manager.connect_stream(device_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect_stream(device_id, websocket)


@router.websocket("/ws/health")
async def ws_health(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """服务端全局健康数据推送（每秒广播）。Phase 2 仅做鉴权和心跳响应。"""
    payload = _verify_ws_token(token)
    if payload is None:
        await websocket.close(code=4401)
        return

    await ws_manager.connect_health(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect_health(websocket)
