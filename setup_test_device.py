#!/usr/bin/env python3
"""快速添加本地测试设备到数据库"""

import asyncio
from datetime import datetime, timezone
from sqlalchemy import select

# 导入后端的数据库模块
import sys
sys.path.insert(0, 'backend')

from database import AsyncSessionLocal
from models import Device, DeviceSettings


async def setup_test_device():
    """创建测试设备"""
    async with AsyncSessionLocal() as session:
        # 检查是否已存在
        result = await session.execute(
            select(Device).where(Device.ip_address == "127.0.0.1")
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"✓ 测试设备已存在 (ID: {existing.id})")
            return existing.id
        
        # 创建新设备
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        device = Device(
            name="本地测试设备",
            ip_address="127.0.0.1",
            location="localhost",
            is_active=True,
            total_frames=0,
            created_at=now,
            updated_at=now,
        )
        session.add(device)
        await session.flush()
        device_id = device.id
        
        # 创建默认设置
        settings = DeviceSettings(
            device_id=device_id,
            line_y=1080,
            confidence=0.5,
            resolution_w=3840,
            resolution_h=2160,
            fps_limit=30,
            alert_l2_threshold=10,
            alert_l3_threshold=20,
            alert_l4_threshold=30,
            park_timeout_seconds=300,
            updated_at=now,
        )
        session.add(settings)
        
        await session.commit()
        
        print(f"✓ 测试设备创建成功!")
        print(f"  - Device ID: {device_id}")
        print(f"  - IP Address: 127.0.0.1")
        print(f"  - Name: 本地测试设备")
        print(f"  - Location: localhost")
        print()
        print("现在可以运行测试脚本:")
        print("  python test_video_inference.py Video11.mp4")
        
        return device_id


if __name__ == "__main__":
    asyncio.run(setup_test_device())
