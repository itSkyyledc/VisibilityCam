import os
import json
import logging
from pathlib import Path
import importlib.util
import importlib
import sys

logger = logging.getLogger(__name__)

# Path to settings.py
SETTINGS_PATH = Path(__file__).parent.parent / 'config' / 'settings.py'

# Default configuration (fallback)
DEFAULT_CONFIG = {
    "cameras": {
        "default_camera": {
            "name": "Default Camera",
            "enabled": True,
            "device_id": 0,  # Use default webcam
            "stream_settings": {
                "width": 1280,
                "height": 720,
                "fps": 15,
                "buffer_size": 30
            },
            "visibility_threshold": 40,
            "recovery_threshold": 60,
            "color_delta_threshold": 10.0,
            "roi_regions": [
                {"name": "top-left", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2, "distance": 100},
                {"name": "top-right", "x": 0.7, "y": 0.1, "width": 0.2, "height": 0.2, "distance": 200},
                {"name": "center", "x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2, "distance": 150},
                {"name": "bottom-left", "x": 0.1, "y": 0.7, "width": 0.2, "height": 0.2, "distance": 300},
                {"name": "bottom-right", "x": 0.7, "y": 0.7, "width": 0.2, "height": 0.2, "distance": 400}
            ]
        }
    },
    "location": "New York",
    "weather_api_key": "",
    "debug": False
}

CONFIG_FILE = Path("config/config.json")

def get_settings_config():
    """Load camera configurations from settings.py"""
    try:
        # Try to import settings module
        if SETTINGS_PATH.exists():
            logger.info(f"Loading settings from {SETTINGS_PATH}")
            
            # Import the settings module dynamically
            spec = importlib.util.spec_from_file_location("settings", SETTINGS_PATH)
            settings = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(settings)
            
            # Check if settings has DEFAULT_CAMERA_CONFIG
            if hasattr(settings, 'DEFAULT_CAMERA_CONFIG'):
                cameras_config = settings.DEFAULT_CAMERA_CONFIG
                logger.info(f"Found {len(cameras_config)} cameras in settings.py")
                
                # Convert to our config format
                config = {
                    "cameras": {},
                    "location": getattr(settings, 'DEFAULT_DISPLAY_SETTINGS', {}).get('weather_city', 'New York'),
                    "weather_api_key": "",
                    "debug": False
                }
                
                # Process each camera from settings
                for camera_id, camera_config in cameras_config.items():
                    # Modify the URL parameter
                    if 'rtsp_url' in camera_config:
                        camera_config['url'] = camera_config.pop('rtsp_url')
                    
                    # Add the camera to our config
                    config["cameras"][camera_id] = camera_config
                
                return config
        
        # Fall back to default config if settings.py doesn't exist or doesn't have camera config
        return None
    except Exception as e:
        logger.error(f"Error loading settings from {SETTINGS_PATH}: {str(e)}")
        return None

def load_config():
    """Load configuration from settings.py, file, or create default if neither exists"""
    # First try to load from settings.py
    settings_config = get_settings_config()
    if settings_config:
        return settings_config
    
    # Then try to load from config file
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info(f"Loaded config from {CONFIG_FILE}")
                return config
        except Exception as e:
            logger.error(f"Error loading config from file: {str(e)}")
    
    # If both failed, create and use default
    logger.info("Using default config")
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG

def save_config(config):
    """Save configuration to file"""
    try:
        # Create parent directory if it doesn't exist
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"Saved config to {CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")
        return False 