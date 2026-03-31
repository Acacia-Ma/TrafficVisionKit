# TrafficVisionKit

[中文](#中文) | [English](#english)

---

## 中文

### 1. 项目简介

TrafficVisionKit 是一个面向真实场景的端到端智能交通视觉系统。  
它打通了 **边缘设备采集 -> UDP/TCP 接入 -> 后端帧组装与推理 -> Web 实时可视化与管理** 的完整链路，适合课程设计、工程原型和二次开发。

核心价值（从用户视角）：
- 你可以在一个系统里同时完成设备接入、实时监控、历史统计和系统运维。
- 你可以基于已有前后端能力快速接入自己的设备或模型。
- 你可以用它作为可演示、可复现实验结果的开源基线项目。

### 2. 功能特性

- 实时视频接入：支持边缘端分片流接入（UDP/TCP）。
- 推理与分析：后端负责帧处理、目标检测、统计聚合。
- 可视化看板：Web 端提供实时画面、轨迹与统计展示。
- 设备与用户管理：提供认证、设备管理和基础运维接口。
- 健康检查与可观测：支持健康状态查询与实时广播能力。

### 3. 系统架构（简要）

1. 边缘设备（STM32F407 + 摄像头）采集图像并发送数据流。  
2. 后端接收并组装帧，调用推理引擎进行检测与计数。  
3. 结果写入数据库并通过 WebSocket/HTTP 提供给前端。  
4. 前端展示实时画面、状态和历史数据。

### 4. 技术栈

- **Frontend**: React + TypeScript + Vite + Zustand + TanStack Query + Recharts
- **Backend**: FastAPI + SQLAlchemy + Alembic + Uvicorn
- **AI/CV**: Ultralytics YOLO + OpenCV
- **Database**: MySQL
- **Firmware**: STM32F407（包含工程与驱动基线）

### 5. 环境要求

- Python 3.10+
- Node.js 18+
- pnpm 8+
- MySQL 8+（默认端口 3306）
- Windows（推荐直接使用一键脚本）

### 6. 快速开始（Windows，一键启动）

```bash
start.bat
```

脚本会自动完成：
- 依赖检查（Python / Node / pnpm）
- 后端 `.env` 与前端 `.env.local` 初始化
- Python 虚拟环境与依赖安装
- 前端依赖安装
- 数据库连通性与初始化流程
- 启动后端与前端服务

默认访问地址：
- 前端: `http://localhost:5173`
- API 文档: `http://localhost:8000/docs`

默认管理员账号（首次体验）：
- 用户名: `admin`
- 密码: `admin123`

> 首次登录后请立即修改默认密码。

### 7. 手动启动（开发模式）

#### 7.1 后端

```bash
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\alembic upgrade head
venv\Scripts\python init_db.py
venv\Scripts\uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 7.2 前端

```bash
cd frontend
pnpm install
pnpm dev
```

### 8. 仓库结构

```text
.
├─ backend/      # FastAPI 服务、推理与数据处理
├─ frontend/     # React 可视化控制台
├─ firmware/     # STM32F407 固件工程与驱动
├─ docs/         # 设计与接入文档
└─ start.bat     # Windows 一键检查与启动脚本
```

### 9. 常见问题

- **前端无法请求后端**：检查 `frontend/.env.local` 的 API 地址配置。
- **后端启动失败**：检查 `backend/.env`、数据库账号密码与 MySQL 服务状态。
- **模型不存在**：首次运行会按配置自动处理，或手动放置模型文件到指定路径。
- **端口冲突**：检查 5173/8000/9000 端口占用，必要时调整 `.env`。

### 10. 路线图

- 更完善的设备接入协议抽象
- 更丰富的统计报表与告警机制
- 容器化部署与 CI/CD 支持
- 多模型切换与评估工具

### 11. 贡献指南

欢迎 Issue 与 PR。

建议流程：
1. Fork 本仓库并创建功能分支。
2. 保持改动小而清晰，附带必要说明。
3. 提交 PR 并描述动机、改动点和验证方法。

### 12. 免责声明

本项目用于学习研究与工程原型验证。请遵守当地法律法规和隐私合规要求，不得用于非法监控等用途。

---

## English

### 1. Overview

TrafficVisionKit is an end-to-end intelligent traffic vision system for real-world prototyping.  
It connects the full workflow from **edge capture -> UDP/TCP ingestion -> backend frame assembly and inference -> real-time web visualization and management**.

Why it is useful (from a user perspective):
- You can manage device ingestion, live monitoring, and historical analytics in one stack.
- You can quickly adapt your own devices and models on top of an existing baseline.
- You can use it as a reproducible open-source foundation for demos and experiments.

### 2. Features

- Real-time stream ingestion from edge devices (UDP/TCP).
- Backend frame processing, detection, and aggregation pipeline.
- Real-time dashboard for visualization and operational control.
- Authentication, user/device management, and system endpoints.
- Health reporting and runtime observability support.

### 3. Architecture (High-level)

1. Edge device (STM32F407 + camera) captures images and sends stream data.  
2. Backend receives and assembles frames, then runs detection/inference.  
3. Results are persisted and published via WebSocket/HTTP APIs.  
4. Frontend renders live views, states, and historical metrics.

### 4. Tech Stack

- **Frontend**: React + TypeScript + Vite + Zustand + TanStack Query + Recharts
- **Backend**: FastAPI + SQLAlchemy + Alembic + Uvicorn
- **AI/CV**: Ultralytics YOLO + OpenCV
- **Database**: MySQL
- **Firmware**: STM32F407 project baseline

### 5. Requirements

- Python 3.10+
- Node.js 18+
- pnpm 8+
- MySQL 8+ (default port 3306)
- Windows (recommended for one-click startup script)

### 6. Quick Start (Windows, One-click)

```bash
start.bat
```

The script handles:
- dependency checks (Python / Node / pnpm)
- backend `.env` and frontend `.env.local` bootstrap
- Python venv and backend dependency installation
- frontend dependency installation
- database connectivity and initialization
- backend/frontend startup

Default endpoints:
- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

Default admin account (for first-time setup):
- Username: `admin`
- Password: `admin123`

> Change the default password immediately after first login.

### 7. Manual Run (Development)

#### 7.1 Backend

```bash
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\alembic upgrade head
venv\Scripts\python init_db.py
venv\Scripts\uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 7.2 Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### 8. Repository Layout

```text
.
├─ backend/      # FastAPI services, inference, and data pipeline
├─ frontend/     # React dashboard UI
├─ firmware/     # STM32F407 firmware project and drivers
├─ docs/         # Design and integration documentation
└─ start.bat     # One-click startup checker (Windows)
```

### 9. FAQ

- **Frontend cannot reach backend**: verify API addresses in `frontend/.env.local`.
- **Backend startup fails**: verify `backend/.env`, database credentials, and MySQL service.
- **Model missing**: place model file at configured path or follow first-run bootstrap flow.
- **Port conflicts**: check 5173/8000/9000 and update env configs when needed.

### 10. Roadmap

- Better protocol abstraction for diverse edge devices
- Richer analytics reporting and alert mechanisms
- Containerized deployment and CI/CD support
- Multi-model management and evaluation tools

### 11. Contributing

Issues and pull requests are welcome.

Suggested flow:
1. Fork and create a feature branch.
2. Keep changes focused and well-described.
3. Open a PR with motivation, change details, and validation steps.

### 12. Disclaimer

This project is intended for learning, research, and engineering prototyping.  
Please comply with local laws, regulations, and privacy requirements.
