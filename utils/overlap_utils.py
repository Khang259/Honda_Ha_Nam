# File: overlap_utils.py
from config import THRESHOLD_COVERAGE
import numpy as np
import torch


# #TODO: check this is still available
# def calculate_coverage(detection_box, roi_box):
#     det_x1, det_y1, det_x2, det_y2 = detection_box
    
#     roi_x, roi_y, roi_w, roi_h = roi_box
    
#     roi_x1, roi_y1 = roi_x, roi_y
#     roi_x2, roi_y2 = roi_x + roi_w, roi_y + roi_h
    
#     inter_x1 = max(det_x1, roi_x1)
#     inter_y1 = max(det_y1, roi_y1)
#     inter_x2 = min(det_x2, roi_x2)
#     inter_y2 = min(det_y2, roi_y2)
    
#     inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    
#     roi_area = roi_w * roi_h

#     if roi_area == 0:
#         return 0.0
    
#     return inter_area / roi_area
    
# #TODO: check this is still available
# def is_roi_covered_enough(detection_box, roi_box, THRESHOLD_COVERAGE):
#     coverage = calculate_coverage(detection_box, roi_box)
#     return coverage >= THRESHOLD_COVERAGE

def calculate_coverage_batch(detection_boxes, roi_box, device='cuda'):
    """
    GPU-accelerated vectorized coverage calculation.
    
    Args:
        detection_boxes: torch.Tensor shape (N, 4) [x1, y1, x2, y2] or (N, 6) [x1,y1,x2,y2,conf,cls]
        roi_box: list/tuple [x, y, w, h]
        device: 'cuda' or 'cpu'
    
    Returns:
        coverage: torch.Tensor shape (N,) - coverage ratio for each detection
    """
    if len(detection_boxes) == 0:
        return torch.tensor([], device=device)
    
    if not isinstance(detection_boxes, torch.Tensor):
        detection_boxes = torch.tensor(detection_boxes, device=device)
    else:
        detection_boxes = detection_boxes.to(device)
    
    if detection_boxes.shape[1] > 4: #TODO: check the meaning of 4
        det_boxes = detection_boxes[:, :4]
    else:
        det_boxes = detection_boxes
    
    roi_x, roi_y, roi_w, roi_h = roi_box
    roi_xyxy = torch.tensor([roi_x, roi_y, roi_x + roi_w, roi_y + roi_h], #Format: [x1, y1, x2, y2]
                            device=device, dtype=det_boxes.dtype)
    
    inter_x1 = torch.maximum(det_boxes[:, 0], roi_xyxy[0])
    inter_y1 = torch.maximum(det_boxes[:, 1], roi_xyxy[1])
    inter_x2 = torch.minimum(det_boxes[:, 2], roi_xyxy[2])
    inter_y2 = torch.minimum(det_boxes[:, 3], roi_xyxy[3])
    
    inter_area = torch.clamp(inter_x2 - inter_x1, min=0) * \
                 torch.clamp(inter_y2 - inter_y1, min=0)
    
    roi_area = roi_w * roi_h
    
    if roi_area == 0:
        return torch.zeros(len(det_boxes), device=device)
    
    coverage = inter_area / roi_area
    
    return coverage