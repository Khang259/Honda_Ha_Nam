from pymongo import MongoClient
from datetime import datetime

# 1. Thông tin cấu hình
CONNECTION_STRING = "mongodb://192.168.1.30:27017/"
DB_NAME = "Honda_AI"
COLLECTION_NAME = "validate_pairs"

# 2. Dữ liệu đầu vào của bạn
data = {
  "_id": {
    "$oid": "69d71e1d3d690c81193a86d9"
  },
  "created_at": {
    "$date": "2026-04-09T03:33:49.063Z"
  },
  "pairs": [
    {
      "start": "start_10000060",
      "end": "end_10000760"
    },
    {
      "start": "start_10000059",
      "end": "end_10000761"
    },
    {
      "start": "start_10001050",
      "end": "end_10000759"
    },
    {
      "start": "start_10001051",
      "end": "end_10000385"
    },
    {
      "start": "start_10001052",
      "end": "end_10000382"
    },
    {
      "start": "start_10001053",
      "end": "end_10000376"
    },
    {
      "start": "start_10001054",
      "end": "end_10000373"
    },
    {
      "start": "start_10001055",
      "end": "end_10000367"
    },
    {
      "start": "start_10001056",
      "end": "end_10000394"
    },
    {
      "start": "start_10001057",
      "end": "end_10000370"
    },
    {
      "start": "start_10000062",
      "end": "end_10000396"
    },
    {
      "start": "start_10002232",
      "end": "end_10000361"
    },
    {
      "start": "start_10002233",
      "end": "end_10000364"
    },
    {
      "start": "start_10001762",
      "end": "end_10001495"
    },
    {
      "start": "start_10001763",
      "end": "end_10000379"
    },
    {
      "start": "start_10000391",
      "end": None
    },
    {
      "start": "start_10001287",
      "end": None
    },
    {
      "start": "start_10001290",
      "end": None
    },
    {
      "start": "start_10001293",
      "end": None
    },
    {
      "start": "start_10001295",
      "end": None
    },
    {
      "start": "start_10001299",
      "end": None
    },
    {
      "start": "start_10001384",
      "end": "end_10000044"
    },
    {
      "start": "start_10001384",
      "end": "end_10000045"
    },
    {
      "start": "start_10001384",
      "end": "end_10000046"
    },
    {
      "start": "start_10001384",
      "end": "end_10000047"
    },
    {
      "start": "start_10001385",
      "end": "end_10000044"
    },
    {
      "start": "start_10001385",
      "end": "end_10000045"
    },
    {
      "start": "start_10001385",
      "end": "end_10000046"
    },
    {
      "start": "start_10001385",
      "end": "end_10000047"
    },
    {
      "start": "start_10001386",
      "end": "end_10000044"
    },
    {
      "start": "start_10001386",
      "end": "end_10000045"
    },
    {
      "start": "start_10001386",
      "end": "end_10000046"
    },
    {
      "start": "start_10001386",
      "end": "end_10000047"
    }
  ],
  "updated_at": {
    "$date": "2026-04-09T03:33:49.063Z"
  },
  "area_name": "AE5"
}

def insert_pairs_to_mongo(input_data):
    try:
        # Kết nối tới MongoDB
        client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        # Chuẩn bị danh sách các bản ghi để insert
        # Mình sẽ chèn thêm area_name và thời gian tạo để dữ liệu đầy đủ hơn
        docs_to_insert = []
        for pair in input_data["pairs"]:
            doc = {
                "id": increment_id(),
                "start": pair["start"],
                "end": pair["end"],
                "area_name": input_data["area_name"],
                "created_at": datetime.utcnow()
            }
            docs_to_insert.append(doc)

        # Thực hiện insert hàng loạt (Bulk Insert)
        if docs_to_insert:
            result = collection.insert_many(docs_to_insert)
            print(f"✅ Thành công! Đã chèn {len(result.inserted_ids)} tài liệu vào collection '{COLLECTION_NAME}'.")
        else:
            print("⚠️ Không tìm thấy dữ liệu trong mảng 'pairs'.")

    except Exception as e:
        print(f"❌ Lỗi kết nối hoặc xử lý: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    insert_pairs_to_mongo(data)