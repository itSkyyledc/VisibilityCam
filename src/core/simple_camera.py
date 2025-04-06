import cv2
import time
import logging
import os
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SimpleCamera:
    """Simple camera class for handling RTSP streams"""
    
    def __init__(self, camera_id: str, config: Dict[str, Any]):
        """Initialize camera with configuration"""
        self.camera_id = str(camera_id)  # Ensure camera_id is a string
        self.config = config
        self.cap = None
        self.is_connected = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.last_frame = None
        self.last_frame_time = 0
        self.frame_timeout = 5  # seconds
        
        # Get stream settings from config
        self.stream_settings = config.get('stream_settings', {})
        self.rtsp_url = config.get('rtsp_url')
        
        # Setup recording directories
        try:
            # Try to import from settings
            from ..config.settings import RECORDINGS_DIR, HIGHLIGHTS_DIR
            self.recordings_dir = RECORDINGS_DIR / self.camera_id
            self.highlights_dir = HIGHLIGHTS_DIR / self.camera_id
            
            # Ensure directories exist
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
            self.highlights_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # Fallback to local directories
            logger.warning(f"Error setting up directories from settings: {str(e)}")
            self.recordings_dir = Path(f"recordings/{self.camera_id}")
            self.highlights_dir = Path(f"highlights/{self.camera_id}")
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
            self.highlights_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.rtsp_url:
            raise ValueError(f"No RTSP URL provided for camera {camera_id}")
    
    def connect(self) -> bool:
        """Connect to the camera"""
        if self.connection_attempts >= self.max_connection_attempts:
            logger.error(f"Max connection attempts ({self.max_connection_attempts}) reached for camera {self.camera_id}")
            return False
            
        self.connection_attempts += 1
        logger.info(f"Attempting to connect to camera {self.camera_id} (attempt {self.connection_attempts}/{self.max_connection_attempts})")
        
        try:
            # Close existing connection if any
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            
            # Configure FFmpeg options for better RTSP handling
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|"
                "fflags;nobuffer|"
                "flags;low_delay|"
                "stimeout;5000000|"  # 5 second timeout
                "max_delay;500000|"  # 500ms max delay
                "analyzeduration;1000000|"  # 1 second analyze duration
                "probesize;1000000|"  # 1MB probe size
                "fflags;discardcorrupt|"  # Discard corrupted frames
                "fflags;genpts|"  # Generate presentation timestamps
                "fflags;igndts|"  # Ignore decoding timestamps
                "fflags;nofillin|"  # Don't fill in missing timestamps
                "fflags;noparse"  # Don't parse the input
            )
            
            # Open the stream with FFmpeg backend
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            if not self.cap.isOpened():
                logger.error(f"Failed to open RTSP stream for camera {self.camera_id}")
                return False
            
            # Set buffer size
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.stream_settings.get('buffer_size', 1))
            
            # Set frame size if specified
            if 'width' in self.stream_settings:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.stream_settings['width'])
            if 'height' in self.stream_settings:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.stream_settings['height'])
            
            # Try to read a few frames to ensure connection is stable
            success_count = 0
            for _ in range(3):  # Try 3 times
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    success_count += 1
                    self.last_frame = frame
                    self.last_frame_time = time.time()
            
            if success_count > 0:
                self.is_connected = True
                self.connection_attempts = 0
                logger.info(f"Successfully connected to camera {self.camera_id}")
                return True
            else:
                logger.error(f"Failed to read frames from camera {self.camera_id}")
                self.cap.release()
                self.cap = None
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to camera {self.camera_id}: {str(e)}")
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """Read a frame from the camera"""
        if not self.is_connected or self.cap is None:
            return None
            
        try:
            # Check if we need to reconnect
            current_time = time.time()
            if current_time - self.last_frame_time > self.frame_timeout:
                logger.warning(f"Frame timeout for camera {self.camera_id}, attempting to reconnect")
                self.connect()
                if not self.is_connected:
                    return None
            
            # Read frame
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.last_frame = frame
                self.last_frame_time = current_time
                return frame
            else:
                logger.warning(f"Failed to read frame from camera {self.camera_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error reading frame from camera {self.camera_id}: {str(e)}")
            return None
    
    def release(self):
        """Release camera resources"""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        self.last_frame = None 