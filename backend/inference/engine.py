"""YOLO + ByteTrack 推理引擎全局单例。

设计要点：
- 模型仅加载一次，所有设备共享同一实例（GPU 显存开销固定）
- 推理方法 NOT 线程安全，由调用方通过 ThreadPoolExecutor（max_workers=2）串行化
- ByteTrack 跟踪器每个设备独立，不共享（防止 tracking_id 跨设备碰撞）
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """单个目标的检测结果。"""
    tracking_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    center: tuple[int, int]          # bbox 中心点


# 默认车辆类别（COCO），若模型类别不同会在 initialize() 中动态覆盖
DEFAULT_VEHICLE_CLASS_IDS = {2: "car", 5: "bus", 7: "truck"}


class InferenceEngine:
    """YOLOv8n 推理引擎，全局单例，线程安全加载，推理串行由外部保证。"""

    _instance: Optional["InferenceEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "InferenceEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def initialize(self, model_path: str, device: str) -> None:
        """加载 YOLO 模型（仅第一次调用有效）。"""
        if self._initialized:
            return
        try:
            from ultralytics import YOLO
            logger.info(f"[InferenceEngine] loading model: {model_path} on {device}")
            self._model = YOLO(model_path)
            self._model.to(device)
            self._device = device
            # 按模型类别名动态选择车辆类，兼容自训练模型（如仅有 {0: "car"}）
            model_names = getattr(self._model, "names", {}) or {}
            vehicle_classes: dict[int, str] = {}
            for cls_id, cls_name in model_names.items():
                name = str(cls_name).lower()
                if name in {"car", "bus", "truck", "vehicle"}:
                    vehicle_classes[int(cls_id)] = name
            if not vehicle_classes:
                # 若模型没有标准命名，回退到 COCO 默认映射
                vehicle_classes = DEFAULT_VEHICLE_CLASS_IDS.copy()
                logger.warning(
                    "[InferenceEngine] no vehicle-like class names found in model, "
                    "fallback to COCO ids 2/5/7"
                )
            self._vehicle_class_ids = vehicle_classes
            logger.info(f"[InferenceEngine] vehicle classes: {self._vehicle_class_ids}")
            self._initialized = True
            logger.info("[InferenceEngine] model loaded OK")
        except Exception as exc:
            logger.error(f"[InferenceEngine] model load failed: {exc}")
            # 允许无 GPU/无模型文件时以 dummy 模式运行（Phase 3 开发阶段）
            self._model = None
            self._vehicle_class_ids = DEFAULT_VEHICLE_CLASS_IDS.copy()
            self._initialized = True  # 标记为已初始化，避免循环重试

    @property
    def ready(self) -> bool:
        return self._initialized and self._model is not None

    def detect(
        self,
        frame: np.ndarray,
        tracker_state: dict,
        confidence: float = 0.5,
    ) -> tuple[list[DetectionResult], np.ndarray]:
        """
        对单帧进行 YOLO 推理 + ByteTrack 跟踪。

        参数：
            frame         : BGR numpy array（OpenCV 格式）
            tracker_state : 每设备独立的跟踪器状态字典（由调用方持有，此函数会修改它）
            confidence    : 置信度阈值

        返回：
            (results, rendered_frame)
            results       : DetectionResult 列表（仅车辆类别）
            rendered_frame: 带检测框的渲染帧（BGR numpy array）
        """
        if not self.ready:
            return [], frame.copy()

        # 使用 ByteTrack，每设备通过 persist=True + 隔离 model 调用实现独立跟踪
        vehicle_class_ids = getattr(self, "_vehicle_class_ids", DEFAULT_VEHICLE_CLASS_IDS)
        raw = self._model.track(
            frame,
            persist=True,
            conf=confidence,
            classes=list(vehicle_class_ids.keys()),
            tracker="bytetrack.yaml",
            verbose=False,
        )

        results: list[DetectionResult] = []
        rendered = raw[0].plot() if raw else frame.copy()

        if raw and raw[0].boxes is not None:
            boxes = raw[0].boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                if cls_id not in vehicle_class_ids:
                    continue
                tid = int(box.id[0]) if box.id is not None else -1
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                results.append(DetectionResult(
                    tracking_id=tid,
                    class_id=cls_id,
                    class_name=vehicle_class_ids[cls_id],
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center=(cx, cy),
                ))

        return results, rendered


# 全局单例入口
engine = InferenceEngine()
