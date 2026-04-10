import asyncio
import cv2
import numpy as np
from fastapi.responses import StreamingResponse
from typing import Optional, Dict, Any

from utils.draw_detections import draw_detections_and_rois
from utils.setup_log import setup_logger
from api.clients.mongo_node_id_client import MongoNodeIdClient
import api.state as api_state

logger = setup_logger("streaming_service", "logs/streaming_service/log")

class StreamingService:
    """
    Service streaming video với detected objects và ROIs.
    Sử dụng MJPEG protocol (simple, không cần ffmpeg subprocess).
    """
    
    def __init__(self):
        self.jpeg_quality = 85
        self.target_fps = 10
        self.frame_delay = 1.0 / self.target_fps
        self._mongo_client = MongoNodeIdClient(collection_name="node_id")
    
    async def _resolve_cam_id(self, cam_id_param: str) -> Optional[str]:
        """
        Resolve cam_id từ parameter.
        Hỗ trợ cả cameraId (số) và cam_id đầy đủ (cam_0_0).
        
        Args:
            cam_id_param: có thể là "0" (cameraId) hoặc "cam_0_0" (full cam_id)
        
        Returns:
            cam_id đầy đủ hoặc None nếu không tìm thấy
        """
        if not api_state.camera_manager:
            return None
        
        latest_frames = api_state.camera_manager.latest_frames
        
        # Nếu cam_id_param đã có trong latest_frames, return luôn
        if cam_id_param in latest_frames:
            return cam_id_param
        
        # Nếu là số (cameraId), tìm cam_id tương ứng
        try:
            camera_id = int(cam_id_param)
            # Tìm trong latest_frames theo pattern cam_{i}_{cameraId}
            for key in latest_frames.keys():
                if key.endswith(f"_{camera_id}"):
                    return key
        except ValueError:
            pass
        
        return None
    
    async def _get_rois_from_mongo(self, cam_id: str) -> Optional[Dict[str, Any]]:
        """
        Lấy ROIs từ MongoDB theo camera_id.
        
        Args:
            cam_id: format "cam_0_101" -> extract cameraId = 101
        
        Returns:
            Dict ROIs hoặc None
        """
        try:
            # Parse cameraId từ cam_id string (format: cam_0_101)
            parts = cam_id.split('_')
            if len(parts) >= 3:
                camera_id = int(parts[-1])
            else:
                logger.warning(f"Invalid cam_id format: {cam_id}")
                return None
            
            # Query MongoDB
            all_cameras = await self._mongo_client.get_all()
            for cam_doc in all_cameras:
                if cam_doc.get('cameraId') == camera_id:
                    return cam_doc.get('rois', {})
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting ROIs from MongoDB: {e}", exc_info=True)
            return None
    
    async def generate_mjpeg_stream(self, cam_id_param: str):
        """
        Generator cho MJPEG stream với detections + ROIs.
        
        Args:
            cam_id_param: ID của camera (có thể là cameraId như "0" hoặc cam_id như "cam_0_0")
        
        Yields:
            MJPEG frames với boundary
        """
        # Resolve cam_id từ parameter
        cam_id = await self._resolve_cam_id(cam_id_param)
        if not cam_id:
            logger.error(f"Cannot resolve cam_id from parameter: {cam_id_param}")
            return
        
        logger.info(f"Streaming for cam_id: {cam_id} (from param: {cam_id_param})")
        
        while True:
            try:
                # Check camera_manager availability
                if not api_state.camera_manager:
                    logger.error("Camera manager not initialized")
                    await asyncio.sleep(1)
                    continue
                
                # Get frame từ latest_frames
                latest_frames = api_state.camera_manager.latest_frames
                if cam_id not in latest_frames:
                    logger.warning(f"Camera {cam_id} not found in latest_frames. Available: {list(latest_frames.keys())}")
                    await asyncio.sleep(0.5)
                    continue
                
                frame = latest_frames[cam_id].copy()
                
                # Get detections từ camera_manager
                detections = api_state.camera_manager.get_camera_detections(cam_id)
                
                # Get ROIs từ MongoDB
                rois = await self._get_rois_from_mongo(cam_id)
                
                # Vẽ detections + ROIs lên frame
                annotated_frame = draw_detections_and_rois(frame, detections, rois)
                
                # Encode JPEG
                success, buffer = cv2.imencode(
                    '.jpg',
                    annotated_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                )
                
                if not success:
                    logger.error(f"Failed to encode frame for {cam_id}")
                    await asyncio.sleep(self.frame_delay)
                    continue
                
                # Yield MJPEG frame với boundary
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    buffer.tobytes() +
                    b'\r\n'
                )
                
                await asyncio.sleep(self.frame_delay)
                
            except Exception as e:
                logger.error(f"Error in stream for {cam_id}: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def get_video_feed(self, cam_id_param: str) -> StreamingResponse:
        """
        Trả về StreamingResponse cho video feed.
        
        Args:
            cam_id_param: ID của camera (có thể là cameraId như "0" hoặc cam_id như "cam_0_0")
        
        Returns:
            StreamingResponse với MJPEG stream
        """
        return StreamingResponse(
            self.generate_mjpeg_stream(cam_id_param),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )

# Singleton instance
streaming_service = StreamingService()
