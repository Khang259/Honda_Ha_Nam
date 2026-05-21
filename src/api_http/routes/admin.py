from typing import Dict, Any
from fastapi import APIRouter
from persistence.mongo.mongo_start_event_client import MongoStartEventClient
from shared.setup_log import setup_logger

logger = setup_logger("admin_routes", "logs/admin_routes/log")
router = APIRouter()

_start_event_client = MongoStartEventClient()


@router.post("/reset-sent-events")
async def reset_sent_events() -> Dict[str, Any]:
    """
    Admin API: Reset tất cả docs có flag=True và status=sent 
    thành flag=False và status=pending.
    """
    result = await _start_event_client.reset_all_sent_to_pending()
    
    if result["success"]:
        return {
            "code": 1000,
            "message": result["message"],
            "data": {"count": result["count"]}
        }
    else:
        return {
            "code": 1001,
            "message": "Failed to reset events",
            "error": result.get("error")
        }
