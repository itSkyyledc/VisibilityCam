import os
import logging
import streamlit as st
import time
from datetime import datetime

from src.core.camera_manager import CameraManager
from src.ui.components import UIComponents
from src.utils.config import load_config, save_config
from src.utils.weather import get_weather_data

# Configure logger
logger = logging.getLogger(__name__)

def initialize_cameras(config):
    """Initialize camera managers from config"""
    cameras = {}
    if "cameras" in config:
        for camera_id, camera_config in config["cameras"].items():
            # Add default camera config if needed
            if "stream_settings" not in camera_config:
                camera_config["stream_settings"] = {
                    "width": 1280,
                    "height": 720,
                    "fps": 15,
                    "buffer_size": 30
                }
            
            # Only initialize cameras that are enabled
            if camera_config.get("enabled", True):
                logger.info(f"Initializing camera: {camera_id}")
                cameras[camera_id] = CameraManager(camera_id, camera_config)
                # We don't automatically connect here anymore - user will connect in UI
    return cameras

def run_app():
    """Main application entry point"""
    # Set page config
    st.set_page_config(
        page_title="VisibilityCam",
        page_icon="🎥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    if 'config' not in st.session_state:
        st.session_state.config = load_config()
        logger.info("Config loaded")
    
    if 'cameras' not in st.session_state:
        st.session_state.cameras = initialize_cameras(st.session_state.config)
        logger.info(f"Initialized {len(st.session_state.cameras)} cameras")
    
    if 'active_camera' not in st.session_state:
        camera_ids = list(st.session_state.cameras.keys())
        st.session_state.active_camera = camera_ids[0] if camera_ids else None
        
    if 'camera_connected' not in st.session_state:
        st.session_state.camera_connected = False
    
    if 'weather_data' not in st.session_state:
        try:
            st.session_state.weather_data = get_weather_data(st.session_state.config.get('location', 'New York'))
        except Exception as e:
            logger.error(f"Failed to get weather data: {str(e)}")
            st.session_state.weather_data = None
    
    # Create main UI
    create_main_ui()

def connect_camera(camera_id):
    """Connect to a specific camera"""
    if camera_id in st.session_state.cameras:
        camera_manager = st.session_state.cameras[camera_id]
        success = camera_manager.connect()
        if success:
            logger.info(f"Successfully connected to camera {camera_id}")
            st.session_state.camera_connected = True
            return True
        else:
            logger.error(f"Failed to connect to camera {camera_id}")
            st.session_state.camera_connected = False
            return False
    return False

def create_main_ui():
    """Create the main application UI"""
    # App title and header
    st.title("VisibilityCam")
    st.markdown("Monitor camera visibility and environmental conditions")
    
    # Create sidebar
    create_sidebar()
    
    # Create tabs for main content
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Live Feed", "Analytics", "Weather", "ROI Config", "Recordings", "Settings"
    ])
    
    # Get active camera manager
    active_camera_id = st.session_state.active_camera
    camera_manager = None
    if active_camera_id and active_camera_id in st.session_state.cameras:
        camera_manager = st.session_state.cameras[active_camera_id]
    
    # Set up connection if needed
    if camera_manager and not st.session_state.camera_connected:
        with st.spinner(f"Connecting to camera {active_camera_id}..."):
            success = connect_camera(active_camera_id)
            if success:
                st.success(f"Connected to camera {active_camera_id}")
            else:
                st.error(f"Failed to connect to camera {active_camera_id}. Check camera settings and try again.")
    
    # Create tab content
    with tab1:
        UIComponents.create_live_feed_tab(camera_manager)
    
    with tab2:
        if camera_manager:
            UIComponents.create_analytics_tab(camera_manager)
        else:
            st.info("Select and connect to a camera to view analytics")
    
    with tab3:
        UIComponents.create_weather_tab(st.session_state.weather_data)
    
    with tab4:
        if camera_manager:
            UIComponents.create_roi_config_tab(camera_manager)
        else:
            st.info("Select and connect to a camera to configure ROIs")
    
    with tab5:
        if camera_manager:
            UIComponents.create_recordings_tab(camera_manager)
        else:
            st.info("Select and connect to a camera to view recordings")
    
    with tab6:
        create_settings_tab()

def create_sidebar():
    """Create the sidebar UI"""
    st.sidebar.header("Controls")
    
    # Camera selection
    camera_ids = list(st.session_state.cameras.keys())
    if camera_ids:
        active_camera = st.sidebar.selectbox(
            "Select Camera",
            options=camera_ids,
            index=camera_ids.index(st.session_state.active_camera) if st.session_state.active_camera in camera_ids else 0
        )
        
        # Update active camera if changed
        if active_camera != st.session_state.active_camera:
            st.session_state.active_camera = active_camera
            st.session_state.camera_connected = False
            st.rerun()
        
        # Camera connection button
        camera = st.session_state.cameras.get(active_camera)
        if camera:
            if camera.is_connected():
                if st.sidebar.button("Disconnect Camera"):
                    camera.disconnect()
                    st.session_state.camera_connected = False
                    st.rerun()
                
                # Camera recording controls
                if camera.recording:
                    if st.sidebar.button("Stop Recording"):
                        camera.stop_recording()
                        st.rerun()
                else:
                    if st.sidebar.button("Start Recording"):
                        camera.start_recording()
                        st.rerun()
            else:
                if st.sidebar.button("Connect Camera"):
                    with st.spinner(f"Connecting to camera {active_camera}..."):
                        success = connect_camera(active_camera)
                        if success:
                            st.sidebar.success(f"Connected to camera {active_camera}")
                        else:
                            st.sidebar.error(f"Failed to connect to {active_camera}")
                        st.rerun()
    else:
        st.sidebar.warning("No cameras configured")
    
    # Weather refresh
    st.sidebar.subheader("Weather")
    if st.sidebar.button("Refresh Weather"):
        with st.spinner("Refreshing weather data..."):
            try:
                st.session_state.weather_data = get_weather_data(st.session_state.config.get('location', 'New York'))
                st.sidebar.success("Weather data updated")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Failed to update weather: {str(e)}")
    
    # App info
    st.sidebar.markdown("---")
    st.sidebar.info("VisibilityCam v1.0\n\nMonitor camera visibility and environmental conditions")
    
def create_settings_tab():
    """Create settings UI"""
    st.header("Settings")
    
    # Create tabs for different settings
    settings_tab1, settings_tab2, settings_tab3 = st.tabs(["Camera Settings", "Visibility Settings", "System Settings"])
    
    with settings_tab1:
        st.subheader("Camera Configuration")
        
        # Display current cameras and their settings
        for camera_id, camera in st.session_state.cameras.items():
            with st.expander(f"Camera: {camera_id}", expanded=False):
                # Show current config
                config = camera.config
                st.json(config)
                
                # Enable/disable camera
                enabled = st.checkbox(f"Enable {camera_id}", value=config.get("enabled", True), key=f"enable_{camera_id}")
                if enabled != config.get("enabled", True):
                    config["enabled"] = enabled
                    st.session_state.config["cameras"][camera_id]["enabled"] = enabled
                    save_config(st.session_state.config)
                    st.success(f"Updated {camera_id} status: {'Enabled' if enabled else 'Disabled'}")
                    
                # Camera URL/device settings
                col1, col2 = st.columns(2)
                with col1:
                    url = st.text_input("Camera URL", value=config.get("url", ""), key=f"url_{camera_id}")
                with col2:
                    device_id = st.number_input("Device ID", value=config.get("device_id", 0), key=f"device_id_{camera_id}")
                
                # Stream settings
                st.subheader("Stream Settings")
                stream_col1, stream_col2, stream_col3 = st.columns(3)
                with stream_col1:
                    width = st.number_input("Width", value=config["stream_settings"].get("width", 1280), key=f"width_{camera_id}")
                with stream_col2:
                    height = st.number_input("Height", value=config["stream_settings"].get("height", 720), key=f"height_{camera_id}")
                with stream_col3:
                    fps = st.number_input("FPS", value=config["stream_settings"].get("fps", 15), key=f"fps_{camera_id}")
                
                # Save button
                if st.button("Save Camera Settings", key=f"save_{camera_id}"):
                    # Update config
                    st.session_state.config["cameras"][camera_id]["url"] = url
                    st.session_state.config["cameras"][camera_id]["device_id"] = int(device_id)
                    st.session_state.config["cameras"][camera_id]["stream_settings"]["width"] = int(width)
                    st.session_state.config["cameras"][camera_id]["stream_settings"]["height"] = int(height)
                    st.session_state.config["cameras"][camera_id]["stream_settings"]["fps"] = int(fps)
                    
                    # Save to file
                    save_config(st.session_state.config)
                    
                    # Update camera manager
                    camera.config = st.session_state.config["cameras"][camera_id]
                    
                    # Force reconnect if connected
                    if camera.is_connected():
                        camera.disconnect()
                        st.session_state.camera_connected = False
                    
                    st.success(f"Settings saved for {camera_id}")
        
        # Add new camera
        st.subheader("Add New Camera")
        new_camera_id = st.text_input("Camera ID", key="new_camera_id")
        new_camera_name = st.text_input("Camera Name", key="new_camera_name")
        new_camera_url = st.text_input("Camera URL", key="new_camera_url")
        new_camera_device_id = st.number_input("Device ID (for local cameras)", value=0, key="new_camera_device_id")
        
        if st.button("Add Camera"):
            if new_camera_id and (new_camera_url or new_camera_device_id is not None):
                # Create new camera config
                new_camera_config = {
                    "name": new_camera_name,
                    "enabled": True,
                    "stream_settings": {
                        "width": 1280,
                        "height": 720,
                        "fps": 15,
                        "buffer_size": 30
                    }
                }
                
                if new_camera_url:
                    new_camera_config["url"] = new_camera_url
                else:
                    new_camera_config["device_id"] = int(new_camera_device_id)
                
                # Add to config
                st.session_state.config["cameras"][new_camera_id] = new_camera_config
                
                # Save to file
                save_config(st.session_state.config)
                
                # Create new camera manager
                st.session_state.cameras[new_camera_id] = CameraManager(new_camera_id, new_camera_config)
                
                # Set as active camera
                st.session_state.active_camera = new_camera_id
                st.session_state.camera_connected = False
                
                st.success(f"Added new camera: {new_camera_id}")
                st.rerun()
            else:
                st.error("Please provide a Camera ID and either a URL or Device ID")
    
    with settings_tab2:
        st.subheader("Visibility Analysis Settings")
        
        # Get active camera for visibility settings
        active_camera_id = st.session_state.active_camera
        if active_camera_id and active_camera_id in st.session_state.cameras:
            camera = st.session_state.cameras[active_camera_id]
            
            # Visibility thresholds
            st.subheader("Visibility Thresholds")
            vis_col1, vis_col2 = st.columns(2)
            
            with vis_col1:
                visibility_threshold = st.slider("Poor Visibility Threshold", 
                                                min_value=0, max_value=100, 
                                                value=camera.visibility_threshold,
                                                help="Score below this is considered poor visibility")
            
            with vis_col2:
                recovery_threshold = st.slider("Recovery Threshold", 
                                              min_value=0, max_value=100, 
                                              value=camera.recovery_threshold,
                                              help="Score above this is considered good visibility")
            
            # Color delta threshold
            color_delta_threshold = st.slider("Color Change Threshold", 
                                             min_value=0.0, max_value=50.0, 
                                             value=camera.color_delta_threshold,
                                             help="Maximum color difference allowed before flagging visibility issues")
            
            # Save visibility settings
            if st.button("Save Visibility Settings"):
                # Update camera settings
                camera.visibility_threshold = visibility_threshold
                camera.recovery_threshold = recovery_threshold
                camera.color_delta_threshold = color_delta_threshold
                
                # Update config
                st.session_state.config["cameras"][active_camera_id]["visibility_threshold"] = visibility_threshold
                st.session_state.config["cameras"][active_camera_id]["recovery_threshold"] = recovery_threshold
                st.session_state.config["cameras"][active_camera_id]["color_delta_threshold"] = color_delta_threshold
                
                # Save to file
                save_config(st.session_state.config)
                
                st.success("Visibility settings saved")
        else:
            st.info("Select a camera to configure visibility settings")
    
    with settings_tab3:
        st.subheader("System Settings")
        
        # Location for weather
        location = st.text_input("Location for Weather", 
                                value=st.session_state.config.get("location", "New York"),
                                help="City name or location for weather data")
        
        # API keys
        api_key = st.text_input("Weather API Key", 
                               value=st.session_state.config.get("weather_api_key", ""),
                               help="API key for weather service (if required)",
                               type="password")
        
        # Save system settings
        if st.button("Save System Settings"):
            # Update config
            st.session_state.config["location"] = location
            st.session_state.config["weather_api_key"] = api_key
            
            # Save to file
            save_config(st.session_state.config)
            
            # Refresh weather data
            try:
                st.session_state.weather_data = get_weather_data(location)
            except Exception as e:
                st.error(f"Failed to update weather: {str(e)}")
            
            st.success("System settings saved")
            
        # Advanced settings
        with st.expander("Advanced Settings", expanded=False):
            # Debug mode
            debug_mode = st.checkbox("Debug Mode", 
                                    value=st.session_state.config.get("debug", False),
                                    help="Enable additional logging and debug information")
            
            if st.button("Save Advanced Settings"):
                st.session_state.config["debug"] = debug_mode
                save_config(st.session_state.config)
                st.success("Advanced settings saved") 