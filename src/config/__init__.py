"""
Configuration module for the Visibility Camera Dashboard.
"""

from .settings import (
    DEFAULT_CAMERA_CONFIG,
    DEFAULT_DISPLAY_SETTINGS,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    LOG_FILE,
    DATA_DIR
)
from .loader import (
    load_camera_configs,
    load_display_settings,
    save_display_settings,
    save_camera_configs
)

__all__ = [
    'DEFAULT_CAMERA_CONFIG',
    'DEFAULT_DISPLAY_SETTINGS',
    'LOG_FORMAT',
    'LOG_DATE_FORMAT',
    'LOG_FILE',
    'DATA_DIR',
    'load_camera_configs',
    'load_display_settings',
    'save_display_settings',
    'save_camera_configs'
] 