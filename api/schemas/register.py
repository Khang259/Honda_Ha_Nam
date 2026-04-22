from typing import Optional, Dict
from pydantic import BaseModel

class RegisterPayload(BaseModel):
    worker_id: str
    worker_ip: str
    start_time: str
    last_time: str
    capacity: Dict[str, int]