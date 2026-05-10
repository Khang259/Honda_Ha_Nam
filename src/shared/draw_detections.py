import cv2
import numpy as np
import torch
from typing import Dict, List, Optional

def draw_detections_and_rois(
    frame: np.ndarray,
    detections: Optional[torch.Tensor],
    rois: Optional[Dict[str, List[float]]] = None
) -> np.ndarray:
    """
    Vẽ detected objects và ROIs lên frame.
    
    Args:
        frame: numpy array (H, W, 3) BGR
        detections: torch.Tensor (N, 6) hoặc None
                   Format: [x1, y1, x2, y2, confidence, class_id]
        rois: Dict từ MongoDB format: {"1": [x, y, w, h], "2": [x, y, w, h]}
    
    Returns:
        annotated_frame: frame với bbox và ROIs đã vẽ
    """
    if frame is None:
        return np.zeros((480, 640, 3), dtype=np.uint8)
    
    annotated = frame.copy()
    
    # Vẽ ROIs trước (background layer)
    if rois and isinstance(rois, dict):
        for roi_id, roi_coords in rois.items():
            if not roi_coords or len(roi_coords) < 4:
                continue
            
            x, y, w, h = [int(v) for v in roi_coords[:4]]
            
            # ROI rectangle (màu xanh dương, line thickness 2)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (255, 0, 0), 2)
            
            # Label cho ROI
            label = f"ROI {roi_id}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            
            # Background cho text
            cv2.rectangle(
                annotated,
                (x, y - label_size[1] - 5),
                (x + label_size[0], y),
                (255, 0, 0),
                -1
            )
            
            # Text
            cv2.putText(
                annotated,
                label,
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                2
            )
    
    # Vẽ detected objects (foreground layer)
    if detections is not None:
        # Convert GPU tensor to CPU numpy
        if isinstance(detections, torch.Tensor):
            if detections.numel() == 0:
                return annotated
            boxes = detections.cpu().numpy() if detections.is_cuda else detections.numpy()
        else:
            boxes = detections if len(detections) > 0 else []
        
        for box in boxes:
            if len(box) < 6:
                continue
            
            x1, y1, x2, y2, conf, cls = box[:6]
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            # Bbox rectangle (màu xanh lá, line thickness 2)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Label với confidence
            label = f"Object {int(cls)}: {conf:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            
            # Background cho text
            cv2.rectangle(
                annotated,
                (x1, y1 - label_size[1] - 5),
                (x1 + label_size[0], y1),
                (0, 255, 0),
                -1
            )
            
            # Text
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                2
            )
    
    return annotated
