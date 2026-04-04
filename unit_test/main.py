from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
import os
from datetime import datetime

app = FastAPI()

LOG_FILE = "payload_log.json"


def save_payload(data: dict):
    # Nếu file chưa tồn tại → tạo list rỗng
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

    # Đọc dữ liệu cũ
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)

    logs.append(data)

    # Ghi lại file
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


@app.api_route("/test-api", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def test_api(request: Request):
    headers = dict(request.headers)
    query_params = dict(request.query_params)
    content_type = headers.get("content-type", "")

    body = None

    try:
        if "application/json" in content_type:
            body = await request.json()
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            body = dict(await request.form())
        else:
            raw = await request.body()
            body = raw.decode("utf-8", errors="ignore")
    except Exception as e:
        body = f"Error parsing body: {str(e)}"

    payload_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "client_ip": request.client.host if request.client else None,
        "method": request.method,
        "url": str(request.url),
        "headers": headers,
        "query_params": query_params,
        "content_type": content_type,
        "body": body,
    }

    save_payload(payload_data)

    return JSONResponse(
        content={
            "status": "ok",
            "message": "Payload saved to payload_log.json"
        }
    )
