"""
Script convert cameras từ config_origin.py sang format MongoDB
"""
import json
import re
from bson import ObjectId


def extract_camera_id_from_ip(rtsp_url: str) -> int:
    """
    Extract 2 số cuối từ IP address trong RTSP URL.
    Ví dụ: rtsp://admin:Thado12@@192.168.1.102:554/... -> cameraId = 2
    """
    # Pattern để match IP address
    pattern = r'(\d+)\.(\d+)\.(\d+)\.(\d+)'
    match = re.search(pattern, rtsp_url)
    
    if match:
        # Lấy octet cuối cùng (ví dụ: 102)
        last_octet = int(match.group(4))
        # Lấy 2 số cuối
        camera_id = last_octet % 100
        return camera_id
    
    return 0  # Default nếu không parse được


def convert_rois_to_dict(rois_list: list) -> dict:
    """
    Convert ROIs từ list sang dict format.
    
    Input: [{"node_id": "start_10000060", "roi": [163, 156, 79, 66]}, ...]
    Output: {"start_10000060": [163, 156, 79, 66], ...}
    """
    rois_dict = {}
    for roi_item in rois_list:
        node_id = roi_item.get("node_id")
        roi = roi_item.get("roi")
        if node_id and roi:
            rois_dict[node_id] = roi
    
    return rois_dict


def convert_camera_to_mongodb_format(camera: dict, index: int) -> dict:
    """
    Convert một camera object sang MongoDB format.
    
    Args:
        camera: dict từ CAMERAS list
        index: index trong list (dùng làm fallback nếu không parse được IP)
    
    Returns:
        dict: MongoDB document format
    """
    rtsp_url = camera.get("rtsp", "")
    zone = camera.get("zone")
    rois_list = camera.get("rois", [])
    
    # Extract cameraId từ IP
    camera_id = extract_camera_id_from_ip(rtsp_url)
    if camera_id == 0:  # Nếu không parse được, dùng index
        camera_id = index
    
    # Convert rois từ list sang dict
    rois_dict = convert_rois_to_dict(rois_list)
    
    # Tạo MongoDB document
    mongo_doc = {
        "_id": {"$oid": str(ObjectId())},
        "url": rtsp_url,
        "cameraId": camera_id,
        "source_owner": 1,
        "type_model": 1,
        "node_id": "1",  # Default string "1" theo yêu cầu schema
        "area_name": zone if zone else None,
        "rois": rois_dict,
        "current_worker": None,  # Thêm field cho distributed system
        "fencing_token": 0,      # Thêm field cho distributed system
        "last_assigned": None    # Thêm field cho distributed system
    }
    
    return mongo_doc


def main():
    """Main function để convert và export cameras"""
    
    # Import CAMERAS từ config_origin
    import sys
    sys.path.insert(0, '.')
    from config_origin import CAMERAS
    
    # Convert tất cả cameras
    mongo_cameras = []
    
    for idx, camera in enumerate(CAMERAS):
        mongo_doc = convert_camera_to_mongodb_format(camera, idx)
        mongo_cameras.append(mongo_doc)
    
    # Export ra JSON file
    output_file = "cameras_export.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mongo_cameras, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Đã export {len(mongo_cameras)} cameras vào file: {output_file}")
    print(f"\nThống kê:")
    print(f"  - Tổng số cameras: {len(mongo_cameras)}")
    
    # Thống kê theo zone
    zones = {}
    for cam in mongo_cameras:
        zone = cam.get("area_name", "Unknown")
        zones[zone] = zones.get(zone, 0) + 1
    
    print(f"  - Phân bố theo zone:")
    for zone, count in sorted(zones.items()):
        print(f"    + {zone}: {count} cameras")
    
    # Thống kê cameraId
    camera_ids = [cam["cameraId"] for cam in mongo_cameras]
    unique_ids = set(camera_ids)
    duplicates = [cid for cid in unique_ids if camera_ids.count(cid) > 1]
    
    if duplicates:
        print(f"\n⚠️  Cảnh báo: Có {len(duplicates)} cameraId bị trùng:")
        for dup_id in duplicates:
            print(f"    - cameraId {dup_id} xuất hiện {camera_ids.count(dup_id)} lần")
    else:
        print(f"\n✅ Tất cả cameraId đều unique")
    
    # In 3 ví dụ đầu tiên
    print(f"\n📝 Ví dụ 3 cameras đầu tiên:")
    for i, cam in enumerate(mongo_cameras[:3]):
        print(f"\n--- Camera {i+1} ---")
        print(f"cameraId: {cam['cameraId']}")
        print(f"url: {cam['url']}")
        print(f"area_name: {cam['area_name']}")
        print(f"rois count: {len(cam['rois'])}")
        if cam['rois']:
            first_roi = list(cam['rois'].items())[0]
            print(f"  Example ROI: {first_roi[0]} -> {first_roi[1]}")


if __name__ == "__main__":
    main()
