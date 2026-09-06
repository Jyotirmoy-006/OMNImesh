from typing import List, Dict, Any
import numpy as np

class VehicleDetector:
    """
    Lightweight vehicle & emergency vehicle detector using YOLOv8n NCNN INT8 format.
    Runs in Thread A at 15 FPS.
    """
    def __init__(self, model_format: str = "ncnn_int8"):
        self.model_format = model_format

    def detect_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        # In actual HiL deployment, runs ncnn/onnx forward pass
        # Simulated return: bounding boxes, class names, and tracking IDs
        return [
            {"bbox": [100, 150, 200, 250], "class": "car", "confidence": 0.94, "track_id": 101},
        ]
