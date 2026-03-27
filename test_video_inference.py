#!/usr/bin/env python3
"""
本地视频文件 TCP 推理测试脚本

用法：
    python test_video_inference.py <video_file> [--device-id=1] [--fps=None] [--verbose]

示例：
    python test_video_inference.py video.mp4
    python test_video_inference.py video.mp4 --device-id=1 --fps=10 --verbose
"""

from __future__ import annotations

import asyncio
import argparse
import struct
import sys
from pathlib import Path
from typing import Optional, Tuple

import cv2


class TCPFrameClient:
    """TCP 客户端：将视频帧通过 TCP 发送给后端"""

    HEARTBEAT_FRAME = 0xFFFFFFFF
    VERSION_FRAME = 0xFFFFFFFE
    IMAGE_FRAME = 0

    def __init__(self, host: str = "localhost", port: int = 9000):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def connect(self):
        """连接到后端 TCP 服务器"""
        print(f"[TCP] 正在连接 {self.host}:{self.port}...")
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port
            )
            print(f"[TCP] ✓ 连接成功")
        except Exception as e:
            print(f"[TCP] ✗ 连接失败: {e}")
            raise

    async def disconnect(self):
        """断开连接"""
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            print(f"[TCP] 连接已关闭")

    async def send_heartbeat(self):
        """发送心跳包"""
        data = struct.pack(">I", self.HEARTBEAT_FRAME)
        self.writer.write(data)
        await self.writer.drain()
        print(f"[TCP] 心跳包已发送")

    async def send_version(self, version: str = "test_v1.0"):
        """发送版本信息"""
        version_bytes = version.encode("ascii")[:20]
        # 后端协议要求版本包 payload 固定读取 20 字节
        version_bytes = version_bytes.ljust(20, b"\x00")
        data = struct.pack(">I", self.VERSION_FRAME) + version_bytes
        self.writer.write(data)
        await self.writer.drain()
        print(f"[TCP] 版本信息已发送: {version}")

    async def send_frame(self, jpeg_data: bytes):
        """发送 JPEG 图像帧"""
        frame_len = len(jpeg_data)
        header = struct.pack(">I", frame_len)
        data = header + jpeg_data
        self.writer.write(data)
        await self.writer.drain()

    async def send_frames_from_video(
        self,
        video_path: str,
        target_fps: int = None,
        verbose: bool = False,
        jpeg_quality: int = 85,
        resize: Optional[Tuple[int, int]] = (1280, 720),
    ):
        """从视频文件中读取帧并发送"""
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        print(f"\n[Video] 打开视频文件: {video_path}")
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"[Video] 原始分辨率: {width}x{height}")
        if resize:
            print(f"[Video] 缩放至: {resize[0]}x{resize[1]}")
        print(f"[Video] 帧率: {fps:.2f} FPS")
        print(f"[Video] 总帧数: {frame_count}")

        # 计算发送帧的延迟
        if target_fps is None:
            target_fps = fps
        frame_delay = 1.0 / target_fps

        print(f"[Video] 发送帧率: {target_fps:.2f} FPS (延迟: {frame_delay*1000:.1f}ms)")
        print(f"\n[Video] 开始发送帧...\n")

        frame_idx = 0
        sent_frames = 0
        start_ts = asyncio.get_running_loop().time()
        next_send_ts = start_ts

        try:
            # 先发送版本信息
            await self.send_version()
            await asyncio.sleep(0.5)

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_idx += 1

                # 缩放帧（4K → 1280x720 大幅减少数据量）
                if resize:
                    frame = cv2.resize(frame, resize, interpolation=cv2.INTER_LINEAR)

                # 转换为 JPEG
                success, jpeg_data = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
                )
                if not success:
                    print(f"[Video] 警告: 第 {frame_idx} 帧编码失败，跳过")
                    continue

                # 发送帧
                await self.send_frame(jpeg_data.tobytes())
                sent_frames += 1

                if verbose or (sent_frames % 30 == 0):
                    print(
                        f"[Video] [{sent_frames:4d}] 帧 {frame_idx:4d}/{frame_count} "
                        f"({sent_frames*100//frame_count:3d}%) | "
                        f"大小: {len(jpeg_data):6d} bytes"
                    )

                # 按目标帧率精准节流：
                # 旧逻辑是“每帧固定 sleep(frame_delay)”，会把编码/发送耗时也算进去，
                # 导致实际 FPS 明显低于 target_fps。这里改为按时间轴对齐，只睡“剩余时间”。
                next_send_ts += frame_delay
                now = asyncio.get_running_loop().time()
                sleep_s = next_send_ts - now
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
                else:
                    # 发送端已落后：重置时间轴，避免累计漂移
                    next_send_ts = now

        finally:
            cap.release()

        elapsed = max(asyncio.get_running_loop().time() - start_ts, 1e-6)
        actual_fps = sent_frames / elapsed
        print(f"\n[Video] ✓ 发送完成! 共发送 {sent_frames} 帧")
        print(f"[Video] 实际发送速率: {actual_fps:.2f} FPS")
        return sent_frames


async def main():
    parser = argparse.ArgumentParser(
        description="本地视频文件 TCP 推理测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_video_inference.py video.mp4
  python test_video_inference.py video.mp4 --device-id=1 --fps=10 --verbose
  python test_video_inference.py C:/videos/traffic.mp4 --host=127.0.0.1 --port=9000
        """,
    )

    parser.add_argument("video_file", help="本地视频文件路径 (MP4, AVI, MOV 等)")
    parser.add_argument(
        "--host",
        default="localhost",
        help="后端 TCP 服务器地址 (默认: localhost)",
    )
    parser.add_argument(
        "--port", type=int, default=9000, help="后端 TCP 服务器端口 (默认: 9000)"
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=1,
        help="设备 ID (默认: 1) - 用于数据库关联",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=None,
        help="发送帧率 (默认: 与原视频相同)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=85,
        help="JPEG 质量 (1-100，默认: 85)",
    )
    parser.add_argument(
        "--resize",
        type=str,
        default="1280x720",
        help="缩放分辨率，格式 WxH (默认: 1280x720，设为 none 禁用)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="详细输出每一帧的信息"
    )

    args = parser.parse_args()

    # 验证视频文件
    video_path = Path(args.video_file)
    if not video_path.exists():
        print(f"✗ 错误: 视频文件不存在 - {video_path}")
        sys.exit(1)

    # 解析 resize 参数
    resize = None
    if args.resize.lower() != "none":
        try:
            w, h = args.resize.lower().split("x")
            resize = (int(w), int(h))
        except Exception:
            print(f"✗ 错误: --resize 格式错误，应为 WxH，如 1280x720")
            sys.exit(1)

    print("=" * 70)
    print("本地视频 TCP 推理测试脚本")
    print("=" * 70)
    print(f"视频文件: {video_path}")
    print(f"后端地址: {args.host}:{args.port}")
    print(f"设备 ID: {args.device_id}")
    print(f"JPEG 质量: {args.quality}")
    print(f"发送分辨率: {args.resize}")
    print("=" * 70)

    client = TCPFrameClient(host=args.host, port=args.port)

    try:
        # 连接到后端
        await client.connect()

        # 发送视频帧
        sent_frames = await client.send_frames_from_video(
            args.video_file,
            target_fps=args.fps,
            verbose=args.verbose,
            jpeg_quality=args.quality,
            resize=resize,
        )

        print("\n" + "=" * 70)
        print("✓ 测试完成!")
        print("=" * 70)
        print("\n📊 接下来你可以:")
        print(f"  1. 打开前端: http://localhost:5173")
        print(f"  2. 在仪表板查看实时数据")
        print(f"  3. 查看设备 {args.device_id} 的检测结果")
        print(f"  4. 检查 API: http://localhost:8000/docs")
        print()

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
