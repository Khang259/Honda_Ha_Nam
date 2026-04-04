# File: roi_drawer.py
#TODO: check if this is still available

import cv2

def draw_rois_on_frame(frame, rois, states_dict, coverage_dict=None):
    """
    Vẽ các vùng ROI với màu sắc và coverage percentage.
    
    Args:
        frame: ảnh gốc
        rois: list of {"node_id": str, "roi": [x,y,w,h]}
        states_dict: dict {node_id: bool}
        coverage_dict: dict {node_id: float} (0.0-1.0)
    """
    if coverage_dict is None:
        coverage_dict = {}
    
    for roi_dict in rois:
        node_id = roi_dict["node_id"]
        x, y, w, h = roi_dict["roi"]
        
        has_object = states_dict.get(node_id, False)
        coverage = coverage_dict.get(node_id, 0.0)
        
        # Vẽ box
        color = (0, 255, 0) if has_object else (0, 0, 255)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        
        # Vẽ node_id + coverage
        text = f"{node_id}: {coverage:.1%}"
        cv2.putText(
            frame,
            text,
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2
        )