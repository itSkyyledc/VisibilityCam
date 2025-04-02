"""
V380 Camera Manager module

This module provides specialized handling for V380 cameras, which use a proprietary
protocol rather than standard ONVIF/RTSP protocols.
"""

import cv2
import time
import os
import logging
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)

class V380CameraManager:
    """
    Manager for V380 IP cameras.
    
    V380 cameras typically use a proprietary protocol rather than standard RTSP/ONVIF.
    This class provides specialized handling for these cameras, determined through
    reverse engineering of the V380 Pro desktop application.
    """
    
    def __init__(self, camera_id, config):
        """
        Initialize a V380 camera manager.
        
        Args:
            camera_id (str): Unique identifier for the camera
            config (dict): Camera configuration including IP, credentials, etc.
        """
        self.camera_id = camera_id
        self.config = config
        self.name = config.get("name", "V380 Camera")
        self.location = config.get("location", "Unknown")
        
        # Extract IP and credentials
        self.username = config.get("username", "admin")
        self.password = config.get("password", "AIC_admin")
        self.ip = config.get("ip", "")
        self.port = int(config.get("port", "8800"))
        
        # Initialize connection objects
        self.cap = None
        self.connected = False
        
        # Set up paths for recordings and highlights
        data_dir = Path(config.get("data_dir", "data"))
        self.recordings_dir = data_dir / "recordings" / camera_id
        self.highlights_dir = data_dir / "highlights" / camera_id
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.highlights_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up stream settings
        self.stream_settings = config.get("stream_settings", {
            "width": 1280,
            "height": 720,
            "fps": 20,
            "buffer_size": 1  # Smallest buffer for less delay
        })
        
        # Initialize recording state
        self.recording = False
        self.out = None
        self.last_highlight_time = 0
        
        # Frame buffer for highlights
        self.frame_buffer = deque(maxlen=20 * self.stream_settings["fps"])  # 20 seconds buffer
        
        # Frame caching
        self.last_good_frame = None
    
    def connect(self):
        """
        Attempt to connect to the V380 camera using RTSP.
        
        Returns:
            bool: True if connection is successful, False otherwise
        """
        logger.info(f"Connecting to V380 camera {self.name} at {self.ip}:{self.port}")
        
        try:
            # Configure FFmpeg options for better stability
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;tcp|"
                f"analyzeduration;10000000|"
                f"buffer_size;65536|"
                f"stimeout;5000000|"
                f"max_delay;500000|"
                f"fflags;nobuffer|"
                f"flags;low_delay"
            )
            
            # Create video capture object
            self.cap = cv2.VideoCapture(f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/live/ch00_1", cv2.CAP_FFMPEG)
            
            if not self.cap.isOpened():
                raise Exception("Failed to open RTSP stream")
            
            # Apply stream settings
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Smallest buffer for less delay
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.stream_settings["width"])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.stream_settings["height"])
            self.cap.set(cv2.CAP_PROP_FPS, self.stream_settings["fps"])
            
            # Verify settings
            actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            logger.info(f"Camera {self.name} connected successfully")
            logger.info(f"Stream settings: {actual_width}x{actual_height}@{actual_fps:.1f}")
            
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            if self.cap:
                self.cap.release()
                self.cap = None
            return False
    
    def disconnect(self):
        """Release camera resources"""
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None
        
        if self.recording:
            self.stop_recording()
        
        self.connected = False
        logger.info(f"Disconnected from V380 camera {self.name}")
    
    def read_frame(self):
        """
        Read a frame from the camera
        
        Returns:
            numpy.ndarray or None: Frame if successful, None otherwise
        """
        if not self.connected or not self.cap or not self.cap.isOpened():
            logger.warning("Cannot read frame: camera not connected")
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to read frame")
            return None
        
        # Process frame
        if frame.shape[1] != self.stream_settings["width"] or frame.shape[0] != self.stream_settings["height"]:
            frame = cv2.resize(frame, (self.stream_settings["width"], self.stream_settings["height"]))
        
        # Add frame to buffer
        self.frame_buffer.append(frame)
        
        # Analyze frame
        brightness, is_corrupted = self._analyze_visibility(frame)
        
        # Handle corrupted frames
        if is_corrupted:
            if self.last_good_frame is not None:
                frame = self.last_good_frame.copy()
        else:
            self.last_good_frame = frame.copy()
        
        return frame
    
    def start_recording(self):
        """Start recording video"""
        if self.recording:
            logger.warning("Recording already in progress")
            return
        
        if not self.connected:
            logger.warning("Cannot start recording: camera not connected")
            return
        
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            filename = f"{today_date}_{datetime.now().strftime('%H-%M-%S')}.mp4"
            filepath = self.recordings_dir / filename
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.out = cv2.VideoWriter(
                str(filepath),
                fourcc,
                self.stream_settings["fps"],
                (self.stream_settings["width"], self.stream_settings["height"])
            )
            
            if not self.out.isOpened():
                raise Exception("Failed to create video writer")
            
            self.recording = True
            logger.info(f"Started recording to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error starting recording: {str(e)}")
            return False
    
    def stop_recording(self):
        """Stop recording video"""
        if self.out and self.out.isOpened():
            self.out.release()
            self.recording = False
    
    def write_frame(self, frame):
        """Write frame to recording if active"""
        if self.recording and self.out and self.out.isOpened():
            self.out.write(frame)
    
    def create_highlight(self, timestamp):
        """Create a highlight clip from the recording"""
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            highlight_filename = f"highlight_{today_date}_{datetime.now().strftime('%H-%M-%S')}.mp4"
            highlight_path = self.highlights_dir / highlight_filename
            
            # Create highlight writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            highlight_writer = cv2.VideoWriter(
                str(highlight_path),
                fourcc,
                self.stream_settings["fps"],
                (self.stream_settings["width"], self.stream_settings["height"])
            )
            
            if not highlight_writer.isOpened():
                raise Exception("Failed to create highlight writer")
            
            # Write buffered frames to highlight
            for frame in self.frame_buffer:
                highlight_writer.write(frame)
            
            highlight_writer.release()
            
            # Update highlight marker
            self.last_highlight_time = time.time()
            
            return str(highlight_path)
        except Exception as e:
            logger.error(f"Error creating highlight: {str(e)}")
            return None
    
    def get_status(self):
        """Get current camera status"""
        return {
            'connected': self.connected,
            'recording': self.recording,
            'last_highlight_time': self.last_highlight_time
        }
    
    def _analyze_visibility(self, frame, std_threshold=10, hist_threshold=100):
        """Analyze frame visibility and detect corruption"""
        # Convert to grayscale if needed
        if len(frame.shape) == 2:
            gray = frame
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate brightness
        brightness = np.mean(gray)
        
        # Detect corruption
        std_dev = np.std(gray)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist_std = np.std(hist)
        
        is_corrupted = (std_dev < std_threshold) or (hist_std < hist_threshold)
        
        return brightness, is_corrupted 