-- 添加本地测试设备到数据库
-- 在 MySQL 客户端中执行此脚本，或用 navicat 等工具运行

USE traffic_detection;

-- 检查设备是否存在，不存在则插入
INSERT IGNORE INTO devices (name, ip_address, location, is_active, total_frames, created_at, updated_at)
VALUES (
    '本地测试设备',
    '127.0.0.1',
    'localhost',
    1,
    0,
    NOW(),
    NOW()
);

-- 获取刚才插入的设备 ID（或已存在的 ID）
SET @device_id = (SELECT id FROM devices WHERE ip_address = '127.0.0.1' LIMIT 1);

-- 为该设备创建默认配置（如果不存在）
INSERT IGNORE INTO device_settings (
    device_id, line_y, confidence, resolution_w, resolution_h, fps_limit,
    alert_l2_threshold, alert_l3_threshold, alert_l4_threshold, park_timeout_seconds, updated_at
) VALUES (
    @device_id,
    1080,
    0.5,
    3840,
    2160,
    30,
    10,
    20,
    30,
    300,
    NOW()
);

-- 验证
SELECT 
    d.id,
    d.name,
    d.ip_address,
    d.is_active,
    ds.fps_limit,
    ds.confidence
FROM devices d
LEFT JOIN device_settings ds ON d.id = ds.device_id
WHERE d.ip_address = '127.0.0.1';
