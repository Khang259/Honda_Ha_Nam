import asyncio
from be.app.services.camera_service import get_all_bounding_boxes_by_camera

print(asyncio.run(get_all_bounding_boxes_by_camera()))