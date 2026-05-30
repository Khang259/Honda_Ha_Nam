"""
Script convert validate pairs từ config_origin.py sang format MongoDB
"""
import json
from datetime import datetime
from bson import ObjectId


def convert_pairs_to_mongodb(pairs_list: list, area_name: str) -> list:
    """
    Convert list of pairs sang MongoDB format.
    
    Args:
        pairs_list: List of tuples (start,) hoặc (start, end)
        area_name: Tên area (AE5, AE6, AF, 5L, 6L, SUB5)
    
    Returns:
        List of MongoDB documents
    """
    mongo_docs = []
    
    for pair in pairs_list:
        # Tạo ObjectId mới cho mỗi document
        doc_id = str(ObjectId())
        
        # Lấy start node
        start_node = pair[0] if len(pair) > 0 else None
        
        # Lấy end node (nếu có)
        end_node = pair[1] if len(pair) > 1 else None
        
        # Tạo document
        mongo_doc = {
            "_id": {"$oid": doc_id},
            "start": start_node,
            "end": end_node,
            "area_name": area_name,
            "created_at": {"$date": datetime.utcnow().isoformat() + "Z"}
        }
        
        mongo_docs.append(mongo_doc)
    
    return mongo_docs


def main():
    """Main function để convert và export validate pairs"""
    
    # Import PAIRS từ config_origin
    import sys
    sys.path.insert(0, '.')
    from config_origin import (
        PAIRS_AE_5,
        PAIRS_AE_6,
        PAIRS_SUB_5,
        PAIR_AF,
        PAIR_5L,
        PAIR_6L
    )
    
    # Convert tất cả pairs với area_name tương ứng
    all_pairs = []
    
    # AE5
    ae5_pairs = convert_pairs_to_mongodb(PAIRS_AE_5, "AE5")
    all_pairs.extend(ae5_pairs)
    print(f"✅ Converted {len(ae5_pairs)} pairs from PAIRS_AE_5 (AE5)")
    
    # AE6
    ae6_pairs = convert_pairs_to_mongodb(PAIRS_AE_6, "AE6")
    all_pairs.extend(ae6_pairs)
    print(f"✅ Converted {len(ae6_pairs)} pairs from PAIRS_AE_6 (AE6)")
    
    # SUB5
    sub5_pairs = convert_pairs_to_mongodb(PAIRS_SUB_5, "SUB5")
    all_pairs.extend(sub5_pairs)
    print(f"✅ Converted {len(sub5_pairs)} pairs from PAIRS_SUB_5 (SUB5)")
    
    # AF
    af_pairs = convert_pairs_to_mongodb(PAIR_AF, "AF")
    all_pairs.extend(af_pairs)
    print(f"✅ Converted {len(af_pairs)} pairs from PAIR_AF (AF)")
    
    # 5L
    l5_pairs = convert_pairs_to_mongodb(PAIR_5L, "5L")
    all_pairs.extend(l5_pairs)
    print(f"✅ Converted {len(l5_pairs)} pairs from PAIR_5L (5L)")
    
    # 6L
    l6_pairs = convert_pairs_to_mongodb(PAIR_6L, "6L")
    all_pairs.extend(l6_pairs)
    print(f"✅ Converted {len(l6_pairs)} pairs from PAIR_6L (6L)")
    
    # Export ra JSON file
    output_file = "pairs_export.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_pairs, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Đã export {len(all_pairs)} pairs vào file: {output_file}")
    
    # Thống kê
    print(f"\n📊 Thống kê:")
    print(f"  - Tổng số pairs: {len(all_pairs)}")
    
    # Thống kê theo area
    areas = {}
    for pair in all_pairs:
        area = pair.get("area_name", "Unknown")
        areas[area] = areas.get(area, 0) + 1
    
    print(f"  - Phân bố theo area:")
    for area, count in sorted(areas.items()):
        print(f"    + {area}: {count} pairs")
    
    # Thống kê pairs có end vs không có end
    with_end = sum(1 for p in all_pairs if p.get("end") is not None)
    without_end = len(all_pairs) - with_end
    
    print(f"\n  - Phân loại:")
    print(f"    + Pairs có end node: {with_end}")
    print(f"    + Pairs không có end (xe trống): {without_end}")
    
    # In 5 ví dụ
    print(f"\n📝 Ví dụ 5 pairs đầu tiên:")
    for i, pair in enumerate(all_pairs[:5]):
        print(f"\n--- Pair {i+1} ---")
        print(f"start: {pair['start']}")
        print(f"end: {pair['end']}")
        print(f"area_name: {pair['area_name']}")
    
    # Tìm và hiển thị ví dụ về xe trống
    empty_pairs = [p for p in all_pairs if p.get("end") is None]
    if empty_pairs:
        print(f"\n📝 Ví dụ 3 xe trống (không có end node):")
        for i, pair in enumerate(empty_pairs[:3]):
            print(f"\n--- Xe trống {i+1} ---")
            print(f"start: {pair['start']}")
            print(f"end: {pair['end']}")
            print(f"area_name: {pair['area_name']}")


if __name__ == "__main__":
    main()
