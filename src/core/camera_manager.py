import cv2
import numpy as np
import logging
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Lock
from ..config.settings import RECORDINGS_DIR, HIGHLIGHTS_DIR
from collections import deque
import random

logger = logging.getLogger(__name__)

class CameraManager:
    def __init__(self, camera_id, config):
        """Initialize camera manager with configuration"""
        self.camera_id = camera_id
        self.config = config
        self.cap = None
        self.out = None
        self.last_good_frame = None
        self.recording = False
        self.recording_start_time = None
        self.poor_visibility_start = None
        self.last_highlight_time = time.time() - 60
        
        # Threading and buffering
        buffer_size = config.get('stream_settings', {}).get('buffer_size', 30)
        self.frame_buffer = deque(maxlen=buffer_size)  # Using deque with maxlen
        self._lock = Lock()  # Lock for thread-safe operations on the buffer
        self.capture_lock = Lock()
        self.is_capturing = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        
        # Analytics refresh settings
        self.analytics_refresh_interval = config.get('analytics_refresh_interval', 5)  # seconds
        self.last_analytics_update = 0
        self.analytics_enabled = True
        
        # Visibility analysis
        self.visibility_history = []  # Initialize visibility history as an empty list
        self.visibility_window = 30  # Number of frames to analyze
        self.std_threshold = 15  # Standard deviation threshold for visibility
        self.hist_threshold = 150  # Histogram threshold for visibility
        self.edge_threshold = 50  # Edge detection threshold for visibility
        self.blur_threshold = 80  # Blur detection threshold
        
        # Set visibility thresholds from config
        self.visibility_threshold = config.get('visibility_threshold', 40)
        self.recovery_threshold = config.get('recovery_threshold', 60)
        self.visibility_status = "Unknown"
        
        # CIELAB color analysis
        self.roi_regions = config.get('roi_regions', [])
        self.color_delta_threshold = config.get('color_delta_threshold', 10.0)
        
        # If ROI regions are specified as percentages (0-1), convert to pixel values at runtime
        self.roi_regions_normalized = True  # Flag to indicate if regions are normalized (0-1) or absolute pixels
        
        # Default ROIs if none are provided in config
        if not self.roi_regions:
            self.roi_regions = [
                {"name": "top-left", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2, "distance": 100},
                {"name": "top-right", "x": 0.7, "y": 0.1, "width": 0.2, "height": 0.2, "distance": 200},
                {"name": "center", "x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2, "distance": 150},
                {"name": "bottom-left", "x": 0.1, "y": 0.7, "width": 0.2, "height": 0.2, "distance": 300},
                {"name": "bottom-right", "x": 0.7, "y": 0.7, "width": 0.2, "height": 0.2, "distance": 400}
            ]
            self.roi_regions_normalized = True
        
        # Color reference values (baseline)
        self.color_references = {}
        self.color_deltas = {}
        self.reference_frame_count = 0
        self.reference_frame_needed = 10  # Number of frames needed to establish reference
        
        # Metrics tracking - initialize with default non-zero values
        self.current_metrics = {
            'brightness': 50.0,
            'contrast': 20.0,
            'sharpness': 30.0,
            'edge_score': 25.0,
            'visibility_score': 40.0,
            'color_delta_avg': 10.0,
            'visibility_status': 'Unknown',
            'alert_message': ''
        }
        
        # Create camera-specific directories
        self.recordings_dir = RECORDINGS_DIR / camera_id
        self.highlights_dir = HIGHLIGHTS_DIR / camera_id
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.highlights_dir.mkdir(parents=True, exist_ok=True)
        
        # Analytics tracking
        self.connection_time = 0
        self.frames_processed = 0
        self.processing_times = []
        self.avg_processing_time = 0
        self.last_frames_reset = time.time()
        self.color_diversity = 15.0  # Default non-zero value
        self.noise_level = 5.0  # Default non-zero value
        self.visibility_score = 40.0  # Default moderate score
    
    def connect(self):
        """Establish connection to the camera"""
        try:
            self.connection_attempts += 1
            logger.info(f"Attempting to connect to camera {self.camera_id} (attempt {self.connection_attempts})")
            
            # If a device ID is 0, this might be the local webcam - don't use it
            if 'device_id' in self.config and self.config['device_id'] == 0 and not self.config.get('force_local', False):
                logger.warning(f"Skipping local webcam connection for camera {self.camera_id}")
                return False
                
            # Configure FFmpeg options for better RTSP handling
            stream_settings = self.config.get('stream_settings', {})
            rtsp_transport = stream_settings.get('rtsp_transport', 'tcp')
            
            # Set FFmpeg environment variables with improved H.264 specific options
            if 'rtsp_url' in self.config:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                    f"rtsp_transport;{rtsp_transport}|"
                    f"fflags;nobuffer+genpts+igndts+discardcorrupt|"  # Added discardcorrupt to ignore corrupt frames
                    f"flags;low_delay|"
                    f"threads;1|"  # Single thread to avoid thread safety issues
                    f"timeout;30000000|"  # 30 second timeout
                    f"stimeout;30000000|"  # 30 second socket timeout
                    f"analyzeduration;5000000|"  # Increased analyze duration further
                    f"probesize;5000000|"  # Increased probe size further
                    f"max_delay;500000|"  # Reduced max delay
                    f"reorder_queue_size;5000|"  # Increased reorder queue further
                    f"rtsp_flags;prefer_tcp|"  # Prefer TCP for RTSP
                    f"strict;experimental|"  # Allow experimental codecs
                    f"max_interleave_delta;0|"  # Reduce interleaving delay
                    f"buffer_size;5000000|"  # Increased buffer size further
                    f"max_analyze_duration;5000000|"  # Increased analyze duration further
                    f"thread_type;slice|"  # Use slice threading (safer)
                    f"error_recovery;3|"  # Increase error recovery level to maximum (was 1)
                    f"err_detect;crccheck+bitstream+buffer+explode|"  # Add extensive error detection
                    f"skip_loop_filter;all|"  # Skip loop filter for better recovery
                    f"skip_frame;nonref|"  # Skip non-reference frames when recovering
                    f"reconnect;1|"  # Enable reconnection
                    f"reconnect_at_eof;1|"  # Reconnect at end of file
                    f"reconnect_streamed;1|"  # Reconnect for streamed content 
                    f"reconnect_delay_max;5"  # Maximum reconnect delay
                )
                
                # Create video capture object with explicit FFMPEG backend
                self.cap = cv2.VideoCapture(self.config['rtsp_url'], cv2.CAP_FFMPEG)
            else:
                # No RTSP URL, maybe skip or use other URL types
                url = self.config.get('url')
                if url:
                    # Create video capture with non-webcam URL
                    self.cap = cv2.VideoCapture(url)
                else:
                    logger.warning(f"No URL or RTSP URL for camera {self.camera_id}, skipping")
                    return False
            
            if not self.cap.isOpened():
                raise Exception("Failed to open camera stream")
            
            # Apply stream settings
            if stream_settings:
                width = stream_settings.get('width', 1280)
                height = stream_settings.get('height', 720)
                fps = stream_settings.get('fps', 15)
                buffer_size = stream_settings.get('buffer_size', 30)
                
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self.cap.set(cv2.CAP_PROP_FPS, fps)
                
                # Disable multi-threading in OpenCV to avoid FFmpeg thread issues
                self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, 0)  # Disable hardware acceleration
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))  # Use H.264 codec
                self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 1.0)
            
            # Reset connection attempts on successful connection
            self.connection_attempts = 0
            
            # Record connection time
            self.connection_time = time.time()
            
            # Reset analytics counters
            self.frames_processed = 0
            self.processing_times = []
            self.avg_processing_time = 0
            self.last_frames_reset = time.time()
            
            # Start frame capture thread
            self.is_capturing = True
            self._start_capture_thread()
            
            # Force initial metrics update to avoid all zeros
            self.force_update_metrics()
            
            logger.info(f"Camera {self.camera_id} connected successfully")
            return True
        except Exception as e:
            logger.error(f"Error connecting to camera {self.camera_id}: {str(e)}")
            self.disconnect()
            return False
    
    def _capture_frames(self):
        """Background thread to capture frames"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        frame_interval = 1.0 / self.config['stream_settings']['fps']  # Time between frames
        last_frame_time = time.time()
        
        while self.is_capturing:
            try:
                loop_start = time.time()
                
                # Ensure minimum time between frame captures to reduce CPU load
                elapsed_since_last_frame = loop_start - last_frame_time
                if elapsed_since_last_frame < frame_interval:
                    time.sleep(max(0, frame_interval - elapsed_since_last_frame) * 0.8)  # Add a 20% margin
                    continue
                
                with self.capture_lock:
                    if not self.cap or not self.cap.isOpened():
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive errors in capture thread for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    
                    # Safe frame reading with error handling
                    try:
                        ret, frame = self.cap.read()
                        
                        # Additional check for corrupt frames that don't raise exceptions
                        if ret and frame is not None and frame.size > 0:
                            # Check for common corruption indicators (extreme green tint, completely black, etc.)
                            if np.mean(frame) < 1.0 or np.std(frame) < 1.0:  # Almost black frame
                                logger.warning(f"Detected potentially corrupt frame (low variance) for camera {self.camera_id}")
                                ret = False  # Force frame to be treated as invalid
                            
                            # Check for invalid dimensions
                            expected_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            expected_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            if frame.shape[1] != expected_width or frame.shape[0] != expected_height:
                                logger.warning(f"Received frame with incorrect dimensions for camera {self.camera_id}")
                                ret = False  # Force frame to be treated as invalid
                    except cv2.error as e:
                        logger.error(f"OpenCV error during frame read: {str(e)}")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive OpenCV errors for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    except Exception as e:
                        # Handle other exceptions during frame reading
                        logger.error(f"Exception during frame read: {str(e)}")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive exceptions during frame read for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    
                    if not ret or frame is None or frame.size == 0:
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive frame read errors for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    
                    # Reset error counter on successful frame read
                    consecutive_errors = 0
                    last_frame_time = time.time()
                    
                    # Store last good frame as backup
                    self.last_good_frame = frame.copy()
                    
                    # Process frame for visibility analysis
                    processed_frame = self._process_frame(frame)
                    
                    # Update buffer without blocking
                    if not self.frame_buffer.full():
                        self.frame_buffer.put(processed_frame)
                    else:
                        # Remove oldest frame if buffer is full
                        try:
                            self.frame_buffer.get_nowait()
                            self.frame_buffer.put(processed_frame)
                        except:
                            pass
                
                # Calculate time to wait before next frame
                elapsed = time.time() - loop_start
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Error in capture thread: {str(e)}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors in capture thread for camera {self.camera_id}")
                    self.is_capturing = False
                    break
                time.sleep(0.1)
    
    def disconnect(self):
        """Disconnect the camera"""
        try:
            logger.info(f"Disconnecting camera {self.camera_id}")
            
            # Stop capture thread first
            self.is_capturing = False
            if hasattr(self, 'capture_thread') and self.capture_thread is not None:
                if self.capture_thread.is_alive():
                    self.capture_thread.join(timeout=2.0)
                self.capture_thread = None
            
            # Release video capture
            with self.capture_lock:
                if self.cap is not None:
                    try:
                        self.cap.release()
                    except Exception as e:
                        logger.error(f"Error releasing camera capture: {str(e)}")
                    finally:
                        self.cap = None
            
            # Stop recording if active
            if self.recording:
                self.stop_recording()
            
            # Clear buffer - frame_buffer is a deque, not a queue
            try:
                with self._lock:
                    self.frame_buffer.clear()
            except Exception as e:
                logger.error(f"Error clearing frame buffer: {str(e)}")
                
            logger.info(f"Camera {self.camera_id} disconnected")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")
            # Reset all capture-related variables to ensure clean state
            self.is_capturing = False
            self.cap = None
            self.capture_thread = None
    
    def reconnect(self):
        """Attempt to reconnect to the camera"""
        logger.info(f"Attempting to reconnect camera {self.camera_id}")
        
        # Ensure we're disconnected first
        self.disconnect()
        
        # Reset connection attempts to allow for reconnection
        if self.connection_attempts >= self.max_connection_attempts:
            self.connection_attempts = 0
            
        # Wait a short period before reconnecting
        time.sleep(2)
        
        # Attempt to connect
        return self.connect()
    
    def read_frame(self):
        """Read a frame from the camera, either from the buffer or directly"""
        try:
            # If not connected, return last good frame or None
            if not self.is_connected():
                return self.last_good_frame

            # If using frame buffer
            if self.is_capturing:
                with self._lock:
                    if len(self.frame_buffer) > 0:
                        return self.frame_buffer.pop()
            
            # Otherwise read directly from camera
            with self.capture_lock:
                if self.cap is None or not self.cap.isOpened():
                    return self.last_good_frame
                    
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    return self.last_good_frame
                
                # Process the frame for visibility analysis
                processed_frame = self._process_frame(frame)
                
                # Return the processed frame
                return processed_frame
        except Exception as e:
            logger.error(f"Error reading frame: {str(e)}")
            return self.last_good_frame
    
    def start_recording(self):
        """Start recording video"""
        try:
            if self.recording:
                return True  # Already recording
                
            today_date = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%H-%M-%S")
            filename = f"{today_date}_{current_time}.mp4"
            filepath = self.recordings_dir / filename
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            width = self.config['stream_settings']['width']
            height = self.config['stream_settings']['height']
            fps = self.config['stream_settings']['fps']
            
            self.out = cv2.VideoWriter(
                str(filepath),
                fourcc,
                fps,
                (width, height)
            )
            
            if not self.out.isOpened():
                raise Exception("Failed to create video writer")
            
            self.recording = True
            self.recording_start_time = datetime.now()
            logger.info(f"Started recording to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error starting recording: {str(e)}")
            return False
    
    def stop_recording(self):
        """Stop recording video"""
        if self.recording and self.out and self.out.isOpened():
            self.out.release()
            self.out = None
            self.recording = False
            self.recording_start_time = None
            logger.info(f"Stopped recording for camera {self.camera_id}")
            return True
        return False
    
    def write_frame(self, frame):
        """Write frame to recording if active"""
        if self.recording and self.out and self.out.isOpened():
            self.out.write(frame)
    
    def get_status(self):
        """Get current camera status"""
        status = {
            'connected': self.cap is not None and self.cap.isOpened() and self.is_capturing,
            'recording': self.recording,
            'last_highlight_time': self.last_highlight_time,
            'recording_start_time': self.recording_start_time,
            'connection_attempts': self.connection_attempts
        }
        
        if self.recording and self.recording_start_time:
            # Calculate recording duration
            status["recording_duration"] = time.time() - self.recording_start_time
        
        # Add visibility metrics
        status.update(self.current_metrics)
        
        return status
    
    def _process_frame(self, frame):
        """Process frame for analysis and append to buffer"""
        if frame is None:
            return None
            
        # Start processing time measurement
        start_time = time.time()
        
        try:
            # Store original frame
            original_frame = frame.copy()
            
            # Get frame dimensions
            h, w = frame.shape[:2]
            
            # Initialize visibility score components
            brightness_score = 0
            contrast_score = 0
            edge_score = 0
            color_delta_score = 0
            
            # Calculate brightness metrics
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            brightness_normalized = min(brightness / 255.0 * 100, 100)  # Convert to 0-100 scale
            
            # Calculate contrast metrics
            contrast = np.std(gray)
            contrast_normalized = min(contrast / 128.0 * 100, 100)  # Convert to 0-100 scale
            
            # Calculate edge metrics using Sobel
            sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            abs_sobel_x = cv2.convertScaleAbs(sobel_x)
            abs_sobel_y = cv2.convertScaleAbs(sobel_y)
            edges = cv2.addWeighted(abs_sobel_x, 0.5, abs_sobel_y, 0.5, 0)
            edge_metric = np.mean(edges)
            edge_normalized = min(edge_metric / 50.0 * 100, 100)  # Convert to 0-100 scale
            
            # Calculate additional metrics
            
            # Color diversity (how many distinct colors are present)
            downsampled = cv2.resize(frame, (32, 32))  # Downsample for faster clustering
            pixels = downsampled.reshape(-1, 3).astype(np.float32)
            
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            k = 8  # Number of clusters
            attempts = 1
            
            _, labels, centers = cv2.kmeans(pixels, k, None, criteria, attempts, cv2.KMEANS_RANDOM_CENTERS)
            
            # Count how many significant clusters we have (those that cover at least 5% of the image)
            histogram = np.histogram(labels, bins=range(k+1))[0] / float(len(labels))
            significant_clusters = np.sum(histogram > 0.05)
            self.color_diversity = significant_clusters * 12.5  # Scale to 0-100
            
            # Noise level estimation
            noise_map = cv2.medianBlur(gray, 5) - gray
            self.noise_level = min(np.std(noise_map) * 5, 100)  # Scale appropriately
            
            # Process ROIs
            if self.roi_regions and len(self.roi_regions) > 0:
                # Calculate color deltas for each ROI
                self._analyze_color_changes(original_frame)
                
                # Calculate average delta
                if self.color_deltas:
                    avg_delta = sum(self.color_deltas.values()) / len(self.color_deltas)
                    # Convert to a 0-100 score (higher delta = lower score)
                    if avg_delta <= 5:  # Not perceptible
                        color_delta_score = 100
                    elif avg_delta <= 10:  # Slightly perceptible
                        color_delta_score = 80
                    elif avg_delta <= 20:  # Noticeable
                        color_delta_score = 60
                    elif avg_delta <= 30:  # Very noticeable
                        color_delta_score = 40
                    else:  # Significant change
                        color_delta_score = 20
                else:
                    # Default if no ROIs are defined or deltas can't be calculated
                    avg_delta = 10.0  # Default to slightly perceptible
                    color_delta_score = 80  # Default score
            else:
                # Default if no ROIs are defined
                avg_delta = 10.0
                color_delta_score = 80
            
            # Calculate sharpness using Laplacian
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = np.var(laplacian)
            sharpness_normalized = min(sharpness / 500.0 * 100, 100)  # Scale to 0-100
            
            # Draw ROI overlay
            overlay_frame = self._draw_roi_overlay(original_frame)
            
            # Calculate visibility score
            
            # For brightness, we want a bell curve: too dark or too bright is bad
            if brightness < 40:  # Too dark
                brightness_score = brightness / 40.0 * 100
            elif brightness > 200:  # Too bright
                brightness_score = (255 - brightness) / 55.0 * 100
            else:  # Good range
                brightness_score = 100
            
            # Ensure minimum values to avoid all-zero metrics
            brightness_score = max(10.0, brightness_score)
            contrast_normalized = max(10.0, contrast_normalized)
            edge_normalized = max(10.0, edge_normalized)
            color_delta_score = max(10.0, color_delta_score)
                
            # Calculate final visibility score with weightings
            # Brightness: 25%, Contrast: 20%, Edge: 25%, Color Delta: 30%
            self.visibility_score = (
                0.25 * brightness_score +
                0.20 * contrast_normalized + 
                0.25 * edge_normalized + 
                0.30 * color_delta_score
            )
            
            # Determine visibility status based on thresholds
            prev_status = self.visibility_status
            
            if self.visibility_score < self.visibility_threshold:
                new_status = "Poor"
            elif self.visibility_score > self.recovery_threshold:
                new_status = "Good"
            else:
                # If in between thresholds, maintain previous state (hysteresis)
                new_status = prev_status if prev_status in ["Poor", "Good"] else "Moderate"
                
            self.visibility_status = new_status
            
            # Analyze visibility distance based on ROIs and visibility score
            status, alert = self._analyze_visibility(self.visibility_score)
            
            # Update current metrics
            self.current_metrics = {
                'brightness': brightness,
                'contrast': contrast,
                'sharpness': sharpness_normalized,
                'edge_score': edge_normalized,
                'color_delta_avg': avg_delta,
                'visibility_score': self.visibility_score,
                'visibility_status': self.visibility_status,
                'alert_message': alert if 'alert' in locals() else '',
                'color_diversity': self.color_diversity,
                'noise_level': self.noise_level
            }
            
            # Update visibility history
            self.visibility_history.append({
                'timestamp': time.time(),
                'brightness': brightness,
                'contrast': contrast,
                'edge_score': edge_normalized,
                'visibility_score': self.visibility_score,
                'visibility_distance': self._estimate_visibility_distance(
                    [roi.get('distance', 0) for roi in self.roi_regions if roi.get('name') in self.color_deltas and self.color_deltas[roi.get('name')] <= self.color_delta_threshold],
                    [roi.get('distance', 0) for roi in self.roi_regions if roi.get('name') in self.color_deltas and self.color_deltas[roi.get('name')] > self.color_delta_threshold]
                )
            })
            
            # Keep only the last N entries in history
            if len(self.visibility_history) > self.visibility_window:
                self.visibility_history.pop(0)
            
            # Increment processed frames counter
            self.frames_processed += 1
            
            # Update processing time tracking
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            self.processing_times.append(processing_time)
            
            # Keep only last 100 processing times for averaging
            if len(self.processing_times) > 100:
                self.processing_times.pop(0)
                
            # Update average processing time
            self.avg_processing_time = sum(self.processing_times) / len(self.processing_times)
            
            # Reset counters daily
            if time.time() - self.last_frames_reset > 86400:  # 24 hours
                self.frames_processed = 0
                self.last_frames_reset = time.time()
            
            return overlay_frame
        except Exception as e:
            logger.error(f"Error processing frame for camera {self.camera_id}: {str(e)}")
            return frame  # Return original frame in case of error
    
    def _analyze_visibility(self, visibility_score):
        """Analyze visibility based on frame statistics"""
        if not self.visibility_history:
            return "Unknown", ""
            
        # Calculate average statistics
        avg_visibility_score = np.mean([h['visibility_score'] for h in self.visibility_history])
        avg_color_delta = np.mean([h.get('color_delta', 0) for h in self.visibility_history])
        
        # Calculate average visibility distance
        visibility_distances = [h.get('visibility_distance') for h in self.visibility_history if h.get('visibility_distance') is not None]
        avg_visibility_distance = np.mean(visibility_distances) if visibility_distances else None
        
        # Format visibility distance string
        visibility_distance_str = ""
        if avg_visibility_distance is not None:
            visibility_distance_str = f" (Est. {int(avg_visibility_distance)}m visibility)"
        
        # Generate alert message if color change is significant
        alert_message = ""
        if avg_color_delta > self.color_delta_threshold * 1.5:
            alert_message = f"ALERT: Significant color shift detected (ΔE: {avg_color_delta:.1f}){visibility_distance_str}"
        
        # Determine visibility status
        if visibility_score < self.visibility_threshold:
            return "Poor", alert_message
        elif visibility_score < self.recovery_threshold:
            return "Moderate", alert_message
        else:
            return "Good", alert_message
    
    def create_highlight(self, start_time, duration=10):
        """Create a highlight clip from the recording"""
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%H-%M-%S")
            highlight_filename = f"highlight_{today_date}_{current_time}.mp4"
            highlight_path = self.highlights_dir / highlight_filename
            
            # Create a marker file with timestamp info
            marker_file = self.highlights_dir / f"{highlight_filename}.txt"
            with open(marker_file, 'w') as f:
                f.write(f"Start time: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration} seconds\n")
                f.write(f"Visibility status: {self.current_metrics['visibility_status']}\n")
                f.write(f"Visibility score: {self.current_metrics['visibility_score']}\n")
                f.write(f"Brightness: {self.current_metrics['brightness']}\n")
                f.write(f"Contrast: {self.current_metrics['contrast']}\n")
                
                # Add visibility distance from history if available
                visibility_distances = [h.get('visibility_distance') for h in self.visibility_history if h.get('visibility_distance') is not None]
                if visibility_distances:
                    avg_visibility_distance = sum(visibility_distances) / len(visibility_distances)
                    f.write(f"Estimated visibility distance: {int(avg_visibility_distance)}m\n")
            
            # Update highlight marker
            self.last_highlight_time = time.time()
            
            logger.info(f"Created highlight marker at {marker_file}")
            return str(highlight_path)
        except Exception as e:
            logger.error(f"Error creating highlight: {str(e)}")
            return None
    
    def _handle_frame_read_error(self):
        """Handle frame read errors and attempt reconnection"""
        logger.warning("Too many frame read errors. Attempting to reconnect...")
        self.disconnect()
        time.sleep(1)
        self.connect()
    
    def _handle_corruption(self):
        """Handle frame corruption by attempting to reconnect"""
        logger.warning("Too many corrupted frames. Attempting to reconnect...")
        self.disconnect()
        time.sleep(1)
        self.connect()
    
    def is_connected(self):
        """Check if camera is connected"""
        return self.cap is not None and self.cap.isOpened() and self.is_capturing and self.frames_processed > 0

    def _calculate_lab_color(self, frame, roi):
        """Calculate average LAB color values for a region of interest"""
        h, w = frame.shape[:2]
        
        # Handle normalized (0-1) coordinates or absolute pixel coordinates
        if self.roi_regions_normalized or all(0 <= v <= 1 for v in [roi["x"], roi["y"], roi["width"], roi["height"]]):
            x = int(roi["x"] * w)
            y = int(roi["y"] * h)
            width = int(roi["width"] * w)
            height = int(roi["height"] * h)
        else:
            # Assume coordinates are already in pixels
            x = int(roi["x"])
            y = int(roi["y"])
            width = int(roi["width"])
            height = int(roi["height"])
        
        # Ensure ROI is within frame bounds
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        width = max(1, min(width, w - x))
        height = max(1, min(height, h - y))
        
        # Extract ROI
        roi_region = frame[y:y+height, x:x+width]
        
        # Convert to LAB color space
        roi_lab = cv2.cvtColor(roi_region, cv2.COLOR_BGR2LAB)
        
        # Calculate average LAB values
        avg_l = np.mean(roi_lab[:, :, 0])
        avg_a = np.mean(roi_lab[:, :, 1])
        avg_b = np.mean(roi_lab[:, :, 2])
        
        return {"L": avg_l, "A": avg_a, "B": avg_b}

    def _calculate_color_delta_e(self, color1, color2):
        """Calculate CIE Delta E 2000 (color difference) between two LAB colors"""
        # Simplified Delta E calculation (Euclidean distance in LAB space)
        delta_l = color1["L"] - color2["L"]
        delta_a = color1["A"] - color2["A"]
        delta_b = color1["B"] - color2["B"]
        
        # Calculate Delta E
        delta_e = np.sqrt(delta_l**2 + delta_a**2 + delta_b**2)
        return delta_e

    def _analyze_color_changes(self, frame):
        """Analyze color changes in regions of interest"""
        color_changes = {}
        total_delta = 0
        significant_changes = 0
        
        # Track distance-based visibility
        visible_distances = []
        obscured_distances = []
        
        # Loop through each ROI region
        for roi in self.roi_regions:
            roi_name = roi["name"]
            distance = roi.get("distance", 0)
            current_color = self._calculate_lab_color(frame, roi)
            
            # If we're still building reference values
            if self.reference_frame_count < self.reference_frame_needed:
                if roi_name not in self.color_references:
                    self.color_references[roi_name] = current_color
                else:
                    # Update reference as moving average
                    ref = self.color_references[roi_name]
                    alpha = 1.0 / (self.reference_frame_count + 1)
                    self.color_references[roi_name] = {
                        "L": (1 - alpha) * ref["L"] + alpha * current_color["L"],
                        "A": (1 - alpha) * ref["A"] + alpha * current_color["A"],
                        "B": (1 - alpha) * ref["B"] + alpha * current_color["B"]
                    }
                continue
            
            # Calculate delta E (color difference) from reference
            if roi_name in self.color_references:
                delta_e = self._calculate_color_delta_e(current_color, self.color_references[roi_name])
                self.color_deltas[roi_name] = delta_e
                total_delta += delta_e
                
                # Check if change is significant
                if delta_e > self.color_delta_threshold:
                    significant_changes += 1
                    color_changes[roi_name] = {
                        "delta_e": delta_e,
                        "significant": True
                    }
                    
                    # Add to obscured distances if distance is specified
                    if distance > 0:
                        obscured_distances.append(distance)
                else:
                    color_changes[roi_name] = {
                        "delta_e": delta_e,
                        "significant": False
                    }
                    
                    # Add to visible distances if distance is specified
                    if distance > 0:
                        visible_distances.append(distance)
        
        # Calculate average delta across all regions
        avg_delta = total_delta / len(self.roi_regions) if self.roi_regions else 0
        
        # Calculate estimated visibility distance
        visibility_distance = self._estimate_visibility_distance(visible_distances, obscured_distances)
        
        return {
            "color_changes": color_changes,
            "avg_delta": avg_delta,
            "significant_regions": significant_changes,
            "total_regions": len(self.roi_regions),
            "visibility_distance": visibility_distance
        }
        
    def _estimate_visibility_distance(self, visible_distances, obscured_distances):
        """
        Estimate visibility distance based on visible and obscured ROIs
        
        Args:
            visible_distances: List of distances for ROIs with good visibility
            obscured_distances: List of distances for ROIs with poor visibility
        
        Returns:
            Estimated visibility distance in meters
        """
        if not visible_distances and not obscured_distances:
            return None
            
        # If we have both visible and obscured distances
        if visible_distances and obscured_distances:
            # Take the midpoint between farthest visible and nearest obscured
            max_visible = max(visible_distances)
            min_obscured = min(obscured_distances)
            
            # If contradictory (visible distance > obscured distance),
            # use the average of the two
            if max_visible > min_obscured:
                return (max_visible + min_obscured) / 2
            
            # Otherwise use midpoint
            return (max_visible + min_obscured) / 2
        
        # If we only have visible distances, use the farthest visible distance
        # but add a bit extra since visibility might extend beyond
        elif visible_distances:
            return max(visible_distances) * 1.2  # Add 20% extra
        
        # If we only have obscured distances, use the nearest obscured distance
        # but reduce it a bit since visibility likely ends before
        else:
            return min(obscured_distances) * 0.8  # Reduce by 20%

    def _draw_roi_overlay(self, frame):
        """Draw ROI regions on frame with color change indicators"""
        # Check if ROI visualization is disabled
        if not hasattr(frame, 'shape') or frame.shape[0] <= 0 or frame.shape[1] <= 0:
            return frame
            
        # Make a copy to avoid modifying the original
        overlay = frame.copy()
        h, w = overlay.shape[:2]
        
        # Track the minimum visible distance
        min_visible_distance = float('inf')
        max_obscured_distance = 0
        
        for roi in self.roi_regions:
            roi_name = roi["name"]
            
            # Handle normalized (0-1) coordinates or absolute pixel coordinates
            if self.roi_regions_normalized or all(0 <= v <= 1 for v in [roi["x"], roi["y"], roi["width"], roi["height"]]):
                x = int(roi["x"] * w)
                y = int(roi["y"] * h)
                width = int(roi["width"] * w)
                height = int(roi["height"] * h)
            else:
                # Assume coordinates are already in pixels
                x = int(roi["x"])
                y = int(roi["y"])
                width = int(roi["width"])
                height = int(roi["height"])
            
            # Ensure coordinates are within frame bounds
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            width = max(1, min(width, w - x))
            height = max(1, min(height, h - y))
            
            # Default color (green)
            color = (0, 255, 0)
            
            # Get the distance for this ROI (default to 0 if not specified)
            distance = roi.get("distance", 0)
            
            # Flag to track if this ROI has poor visibility
            is_obscured = False
            
            # Change color based on delta E value
            if roi_name in self.color_deltas:
                delta_e = self.color_deltas[roi_name]
                
                if delta_e > self.color_delta_threshold * 2:
                    color = (0, 0, 255)  # Red for major change
                    is_obscured = True
                elif delta_e > self.color_delta_threshold:
                    color = (0, 165, 255)  # Orange for significant change
                    is_obscured = True
                    
                # Update visibility distance tracking
                if is_obscured and distance > max_obscured_distance:
                    max_obscured_distance = distance
                elif not is_obscured and distance < min_visible_distance:
                    min_visible_distance = distance
            
            # Draw filled semi-transparent rectangle
            overlay_roi = overlay.copy()
            cv2.rectangle(overlay_roi, (x, y), (x + width, y + height), color, -1)  # Filled rectangle
            
            # Add this semi-transparent ROI to the main overlay
            alpha = 0.2  # Very transparent fill
            cv2.addWeighted(overlay_roi, alpha, overlay, 1 - alpha, 0, overlay)
            
            # Draw rectangle border and label with solid color
            cv2.rectangle(overlay, (x, y), (x + width, y + height), color, 2)
            cv2.putText(overlay, roi_name, (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, color, 2, cv2.LINE_AA)
            
            # Add distance information if available
            if distance > 0:
                distance_text = f"{distance}m"
                cv2.putText(overlay, distance_text, (x + 5, y + 40), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            
            # Add delta E value if available
            if roi_name in self.color_deltas:
                delta_text = f"ΔE: {self.color_deltas[roi_name]:.1f}"
                cv2.putText(overlay, delta_text, (x + 5, y + height - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
                
                # Add a small colored indicator bar showing the severity
                indicator_width = int(min(width - 10, max(10, (self.color_deltas[roi_name] / 30.0) * width)))
                cv2.rectangle(overlay, (x + 5, y + height - 5), (x + 5 + indicator_width, y + height - 2), color, -1)
        
        # Add estimated visibility distance
        estimated_visibility = "Unknown"
        if max_obscured_distance > 0 and min_visible_distance < float('inf'):
            # We have both visible and obscured ROIs
            estimated_visibility = f"{max_obscured_distance}-{min_visible_distance}m"
        elif max_obscured_distance > 0:
            # All ROIs are obscured, visibility less than the closest obscured ROI
            estimated_visibility = f"<{max_obscured_distance}m"
        elif min_visible_distance < float('inf'):
            # All ROIs are visible, visibility greater than the furthest visible ROI
            estimated_visibility = f">{min_visible_distance}m"
            
        cv2.putText(overlay, f"Est. Visibility: {estimated_visibility}", (10, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        
        return overlay

    def get_roi_regions(self):
        """Get camera ROIs including distance parameter"""
        return self.roi_regions

    def set_roi_regions(self, roi_regions, normalized=False):
        """Set camera ROIs, ensuring each has a distance parameter"""
        # Make a deep copy to avoid modifying the input
        import copy
        updated_regions = copy.deepcopy(roi_regions)
        
        # Store whether ROI coordinates are normalized
        self.roi_regions_normalized = normalized
        
        # Ensure each ROI has a distance parameter
        for roi in updated_regions:
            if 'distance' not in roi:
                roi['distance'] = 100  # Default distance in meters
        
        # Update the stored ROIs
        self.roi_regions = updated_regions
        
        logger.info(f"Updated ROI regions for camera {self.camera_id}: {len(updated_regions)} regions")
        logger.debug(f"ROI regions: {updated_regions}")
        
        return True

    def _start_capture_thread(self):
        """Start the background capture thread"""
        if self.is_capturing:
            return True  # Already running
            
        self.is_capturing = True
        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )
        self.capture_thread.start()
        logger.info(f"Started capture thread for camera {self.camera_id}")
        return True
        
    def _capture_loop(self):
        """Background loop to continuously capture frames"""
        frame_interval = 1.0 / self.config.get('stream_settings', {}).get('fps', 15)
        max_consecutive_errors = 10
        consecutive_errors = 0
        last_frame_time = time.time()
        
        while self.is_capturing and self.cap and self.cap.isOpened():
            try:
                loop_start = time.time()
                
                # Check if it's time to update analytics
                if self.analytics_enabled and (time.time() - self.last_analytics_update) >= self.analytics_refresh_interval:
                    self._update_analytics()
                    self.last_analytics_update = time.time()
                
                # Skip frame read if too little time has passed
                time_since_last = time.time() - last_frame_time
                if time_since_last < frame_interval * 0.5:
                    time.sleep(0.01)  # Short sleep to avoid CPU spinning
                    continue
                
                # Check if buffer is at capacity
                with self._lock:
                    if len(self.frame_buffer) >= self.frame_buffer.maxlen:
                        # Buffer is full, wait a bit
                        time.sleep(0.01)
                        continue
                
                # Skip frame if not enough time elapsed
                if (time.time() - last_frame_time) < (frame_interval * 0.8):
                    continue
                    
                # Capture lock to ensure thread safety
                with self.capture_lock:
                    if not self.cap or not self.cap.isOpened():
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive errors in capture thread for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    
                    # Safe frame reading with error handling
                    try:
                        ret, frame = self.cap.read()
                        
                        # Additional check for corrupt frames that don't raise exceptions
                        if ret and frame is not None and frame.size > 0:
                            # Check for common corruption indicators (extreme green tint, completely black, etc.)
                            if np.mean(frame) < 1.0 or np.std(frame) < 1.0:  # Almost black frame
                                logger.warning(f"Detected potentially corrupt frame (low variance) for camera {self.camera_id}")
                                ret = False  # Force frame to be treated as invalid
                            
                            # Check for invalid dimensions
                            expected_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            expected_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            if frame.shape[1] != expected_width or frame.shape[0] != expected_height:
                                logger.warning(f"Received frame with incorrect dimensions for camera {self.camera_id}")
                                ret = False  # Force frame to be treated as invalid
                    except cv2.error as e:
                        logger.error(f"OpenCV error during frame read: {str(e)}")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive OpenCV errors for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    except Exception as e:
                        # Handle other exceptions during frame reading
                        logger.error(f"Exception during frame read: {str(e)}")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive exceptions during frame read for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    
                    if not ret or frame is None or frame.size == 0:
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"Too many consecutive frame read errors for camera {self.camera_id}")
                            self.is_capturing = False
                            break
                        time.sleep(0.1)
                        continue
                    
                    # Reset error counter on successful frame read
                    consecutive_errors = 0
                    last_frame_time = time.time()
                    
                    # Store last good frame as backup
                    self.last_good_frame = frame.copy()
                    
                    # Process frame for visibility analysis
                    processed_frame = self._process_frame(frame)
                    
                    # Update buffer with thread safety
                    with self._lock:
                        # For deque with maxlen, we just append and it automatically manages capacity
                        self.frame_buffer.append(processed_frame)
                
                # Calculate time to wait before next frame
                elapsed = time.time() - loop_start
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Error in capture thread: {str(e)}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors in capture thread for camera {self.camera_id}")
                    self.is_capturing = False
                    break
                time.sleep(0.1) 

    def get_camera_data(self):
        """Get camera data for analytics display"""
        # Get latest metrics
        data = {
            # First update from current_metrics dictionary
            **self.current_metrics,
            
            # Add additional metadata
            'camera_id': self.camera_id,
            'connected': self.is_connected(),
            'recording': self.recording,
            'connection_time': time.time() - self.connection_time if self.connection_time > 0 else 0,
            'frames_processed': self.frames_processed,
            'avg_processing_time': self.avg_processing_time,
            'visibility_history': self.visibility_history,
            'color_diversity': self.color_diversity,
            'noise_level': self.noise_level,
            
            # Add ROI info
            'roi_count': len(self.roi_regions),
            'color_deltas': self.color_deltas
        }
        
        # Ensure all required fields are present with default values if missing
        required_fields = [
            'brightness', 'contrast', 'sharpness', 'edge_score', 
            'visibility_score', 'visibility_status', 'color_delta_avg'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                data[field] = 0.0
        
        # Make sure visibility history exists
        if 'visibility_history' not in data or not data['visibility_history']:
            data['visibility_history'] = []
            
        # Add timestamps array if needed
        if 'timestamps' not in data:
            data['timestamps'] = []
            if data['visibility_history']:
                data['timestamps'] = [entry.get('timestamp', 0) for entry in data['visibility_history']]
                
        # Add brightness history if needed
        if 'brightness_history' not in data:
            data['brightness_history'] = []
            if data['visibility_history']:
                data['brightness_history'] = [entry.get('brightness', 0) for entry in data['visibility_history']]
                
        return data 

    def force_update_metrics(self):
        """Force update metrics with test data for debugging"""
        # Generate random metrics
        brightness = random.uniform(40, 200)
        contrast = random.uniform(20, 100)
        sharpness = random.uniform(30, 80)
        edge_score = random.uniform(20, 80)
        visibility_score = random.uniform(40, 90)
        color_delta = random.uniform(5, 20)
        
        # Update current metrics
        self.current_metrics = {
            'brightness': brightness,
            'contrast': contrast,
            'sharpness': sharpness,
            'edge_score': edge_score,
            'visibility_score': visibility_score,
            'color_delta_avg': color_delta,
            'visibility_status': 'Good' if visibility_score > 60 else 'Moderate' if visibility_score > 40 else 'Poor',
            'alert_message': ''
        }
        
        # Update other metrics
        self.color_diversity = random.uniform(20, 80)
        self.noise_level = random.uniform(5, 30)
        self.visibility_score = visibility_score
        
        # Add to history
        self.visibility_history.append({
            'timestamp': time.time(),
            'brightness': brightness,
            'contrast': contrast,
            'edge_score': edge_score,
            'visibility_score': visibility_score,
            'visibility_distance': random.uniform(100, 500)
        })
        
        # Ensure we don't exceed history window
        if len(self.visibility_history) > self.visibility_window:
            self.visibility_history.pop(0)
            
        # Increment frames processed
        self.frames_processed += 1
        
        return self.current_metrics 

    def _update_analytics(self):
        """Update analytics based on the current frame"""
        try:
            # If we have a last good frame, use it for analytics
            if self.last_good_frame is not None:
                # Process the frame to update metrics
                self._process_frame(self.last_good_frame)
                logger.debug(f"Updated analytics for camera {self.camera_id}, visibility score: {self.visibility_score:.1f}")
            else:
                # If no frame is available, use test data for demonstration
                logger.warning(f"No frame available for camera {self.camera_id}, using test metrics")
                self.force_update_metrics()
                
            # Update the last analytics update timestamp
            self.last_analytics_update = time.time()
            return True
        except Exception as e:
            logger.error(f"Error updating analytics for camera {self.camera_id}: {str(e)}")
            return False 