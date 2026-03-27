"""TCP 数据帧协议解析（见设计稿第 12 节）。

帧格式：4 字节大端序 frame_length + frame_length 字节 payload

特殊值：
  0xFFFFFFFF → 心跳包（无 payload）
  0xFFFFFFFE → 版本上报包（payload 为 ASCII 版本字符串，最长 20 字节）
  其他       → 普通 JPEG 图像帧
"""
from __future__ import annotations

import struct
from enum import IntEnum
from typing import Optional


class FrameType(IntEnum):
    IMAGE = 0
    HEARTBEAT = 1
    VERSION = 2


class FrameParseError(Exception):
    """帧解析失败（通常意味着连接应被关闭）。"""


async def recv_exactly(reader, n: int) -> bytes:
    """粘包安全读取：严格读取 n 字节，不足则连接已断开，抛出 EOFError。"""
    buf = bytearray()
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            raise EOFError("TCP connection closed unexpectedly")
        buf.extend(chunk)
    return bytes(buf)


async def read_frame(reader) -> tuple[FrameType, bytes]:
    """
    从 asyncio StreamReader 读取完整一帧。

    返回：(frame_type, payload)
      - HEARTBEAT: payload = b""
      - VERSION:   payload = 版本字符串 bytes
      - IMAGE:     payload = JPEG 数据 bytes

    异常：
      EOFError        — 连接正常断开
      FrameParseError — 帧格式错误（payload 过大等）
    """
    header = await recv_exactly(reader, 4)
    length = struct.unpack(">I", header)[0]

    if length == 0xFFFFFFFF:
        return FrameType.HEARTBEAT, b""

    if length == 0xFFFFFFFE:
        raw = await recv_exactly(reader, 20)
        version = raw.rstrip(b"\x00").decode("ascii", errors="replace")
        return FrameType.VERSION, version.encode()

    # 普通图像帧：做合法性检查，最大限制 5MB（防止恶意大包）
    MAX_JPEG_SIZE = 5 * 1024 * 1024
    if length > MAX_JPEG_SIZE:
        raise FrameParseError(f"Oversized frame: {length} bytes")

    payload = await recv_exactly(reader, length)
    return FrameType.IMAGE, payload


ACK_HEARTBEAT = struct.pack(">I", 0x00000001)
