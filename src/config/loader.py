import json
import os
from pathlib import Path
import logging
from .settings import DEFAULT_CAMERA_CONFIG, DEFAULT_DISPLAY_SETTINGS

# Set up logger
logger = logging.getLogger(__name__)

def load_camera_configs():
    """Load camera configurations from file or return defaults"""
    try:
        config_file = Path(__file__).parent.parent.parent / "data" / "camera_config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)
        return DEFAULT_CAMERA_CONFIG
    except Exception as e:
        logger.error(f"Error loading camera configs: {e}")
        return DEFAULT_CAMERA_CONFIG

def load_display_settings():
    """Load display settings from file or return defaults"""
    try:
        settings_file = Path(__file__).parent.parent.parent / "data" / "display_settings.json"
        if settings_file.exists():
            with open(settings_file, 'r') as f:
                return json.load(f)
        return DEFAULT_DISPLAY_SETTINGS
    except Exception as e:
        logger.error(f"Error loading display settings: {e}")
        return DEFAULT_DISPLAY_SETTINGS

def save_display_settings(settings):
    """Save display settings to file"""
    try:
        data_dir = Path(__file__).parent.parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        settings_file = data_dir / "display_settings.json"
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)
        logger.info("Display settings saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving display settings: {e}")
        return False

def save_camera_configs(cameras):
    """Save camera configurations to file"""
    try:
        data_dir = Path(__file__).parent.parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        config_file = data_dir / "camera_config.json"
        with open(config_file, 'w') as f:
            json.dump(cameras, f, indent=4)
        logger.info("Camera configurations saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving camera configurations: {e}")
        return False
