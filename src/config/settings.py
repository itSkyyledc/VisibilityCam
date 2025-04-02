import os
from pathlib import Path
import json
import logging
from datetime import datetime

# Base directories
ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
RECORDINGS_DIR = ROOT_DIR / "recordings"
HIGHLIGHTS_DIR = ROOT_DIR / "highlights"
WEATHER_API_KEY_FILE = ROOT_DIR / "api_key.txt"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
RECORDINGS_DIR.mkdir(exist_ok=True)
HIGHLIGHTS_DIR.mkdir(exist_ok=True)

# Logging configuration
LOG_FILE = LOGS_DIR / "visibility_cam.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Camera configuration with ROI support
DEFAULT_CAMERA_CONFIG = {
    "CTC Rooftop": {
        "name": "CTC Rooftop",
        "location": "Manila, Philippines",
        "rtsp_url": "rtsp://TAPO941A:visibility@192.168.0.112:554/stream1",
        "weather_city": "Manila",
        "visibility_threshold": 30,
        "recovery_threshold": 50,
        "color_delta_threshold": 10.0,
        "roi_regions": [
            {
                "name": "Road",
                "x": 0.1,
                "y": 0.6,
                "width": 0.3,
                "height": 0.3
            },
            {
                "name": "Sky",
                "x": 0.6,
                "y": 0.1,
                "width": 0.3,
                "height": 0.2
            }
        ],
        "stream_settings": {
            "width": 1280,
            "height": 720,
            "fps": 15,
            "buffer_size": 3,
            "rtsp_transport": "tcp",
            "connection_timeout": 10,
            "retry_interval": 5,
            "max_retries": 3
        }
    },
    "AIC Camera": {
        "name": "AIC Camera",
        "location": "Manila, Philippines",
        "rtsp_url": "rtsp://TAPOC8EA:visibility@192.168.0.111:554/stream1",
        "weather_city": "Manila",
        "visibility_threshold": 30,
        "recovery_threshold": 50,
        "color_delta_threshold": 10.0,
        "roi_regions": [
            {
                "name": "Road",
                "x": 0.1,
                "y": 0.6,
                "width": 0.3,
                "height": 0.3
            },
            {
                "name": "Sky",
                "x": 0.6,
                "y": 0.1,
                "width": 0.3,
                "height": 0.2
            }
        ],
        "stream_settings": {
            "width": 1280,
            "height": 720,
            "fps": 15,
            "buffer_size": 3,
            "rtsp_transport": "tcp",
            "connection_timeout": 10,
            "retry_interval": 5,
            "max_retries": 3
        }
    },
    "V380 Camera": {
        "name": "V380 Camera",
        "location": "Manila, Philippines",
        "camera_type": "v380",
        "rtsp_url": "rtsp://buth:4ytkfe@192.168.0.100/live/ch00_1",
        "weather_city": "Manila",
        "visibility_threshold": 30,
        "recovery_threshold": 50,
        "color_delta_threshold": 10.0,
        "roi_regions": [
            {
                "name": "Road",
                "x": 0.1,
                "y": 0.6,
                "width": 0.3,
                "height": 0.3
            },
            {
                "name": "Sky",
                "x": 0.6,
                "y": 0.1,
                "width": 0.3,
                "height": 0.2
            }
        ],
        "stream_settings": {
            "width": 1280,
            "height": 720,
            "fps": 15,
            "buffer_size": 3,
            "rtsp_transport": "tcp",
            "connection_timeout": 10,
            "retry_interval": 5,
            "max_retries": 3
        }
    }
}

# Display settings
DEFAULT_DISPLAY_SETTINGS = {
    "refresh_rate": 0.1,
    "auto_refresh": True,
    "display_mode": "Standard",
    "show_fps": True,
    "show_roi": True,
    "show_overlay": True,
    "initial_load_delay": 3,
    "max_retries": 3,
    "retry_delay": 1,
    "stream_width": 640,
    "stream_height": 480,
    "fps": 15,
    "buffer_size": 30,
    "latency": 5000,
    "connection_timeout": 10
}

# Weather settings
WEATHER_UPDATE_INTERVAL = 3600  # 1 hour in seconds 

# Get logger
logger = logging.getLogger(__name__)

def load_camera_configs():
    """Load camera configurations from settings"""
    # We'll use the default config from settings directly
    # Create a deep copy to avoid modifying the original
    import copy
    return copy.deepcopy(DEFAULT_CAMERA_CONFIG)

def save_camera_configs(cameras):
    """Save camera configurations back to settings file"""
    try:
        # Create a backup of the current settings
        backup_file = LOGS_DIR / f"camera_config_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        
        # Update the global DEFAULT_CAMERA_CONFIG
        global DEFAULT_CAMERA_CONFIG
        DEFAULT_CAMERA_CONFIG.update(cameras)
        
        # Save a backup in JSON format for reference
        os.makedirs('config', exist_ok=True)
        with open('config/camera_config_backup.json', 'w') as file:
            json.dump(DEFAULT_CAMERA_CONFIG, file, indent=4)
            
        logger.info("Camera configurations saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving camera configurations: {str(e)}")
        return False

def load_display_settings():
    """Load display settings from defaults"""
    return DEFAULT_DISPLAY_SETTINGS.copy()

def save_display_settings(settings):
    """Save display settings"""
    try:
        global DEFAULT_DISPLAY_SETTINGS
        DEFAULT_DISPLAY_SETTINGS.update(settings)
        
        # Save a backup in JSON format for reference
        os.makedirs('config', exist_ok=True)
        with open('config/display_settings_backup.json', 'w') as file:
            json.dump(DEFAULT_DISPLAY_SETTINGS, file, indent=4)
            
        logger.info("Display settings saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving display settings: {str(e)}")
        return False

# Note about camera 129.150.48.140
"""
The camera at IP 129.150.48.140 was detected and TCP connection works on port 8800,
but RTSP streaming could not be established. Possible solutions:

1. Access the camera's web interface at http://129.150.48.140:8800 to configure RTSP streaming
2. Check the camera's documentation for the correct RTSP URL format
3. Use ONVIF Device Manager software to discover the camera and its streaming URLs
4. Verify that the credentials (admin/AIC_admin) are correct for streaming
5. Check if there are any firewall rules blocking RTSP streaming

From the Wireshark capture, it appears the camera is reachable, but either the streaming
protocol is non-standard or requires additional configuration.
""" 