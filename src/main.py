import streamlit as st
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import time
import logging
import copy

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.config import (
    load_camera_configs,
    load_display_settings,
    save_display_settings,
    save_camera_configs
)
from src.core.camera_manager import CameraManager
from src.core.weather_manager import WeatherManager
from src.ui.components import UIComponents
from src.utils.logger import setup_logger
from src.config.settings import RECORDINGS_DIR, HIGHLIGHTS_DIR

# Configure logging
logger = setup_logger()

# Import AnalyticsManager and create a single instance
try:
    from src.utils.analytics import AnalyticsManager
    analytics_manager = AnalyticsManager()
except ImportError as e:
    logger.error(f"Failed to import AnalyticsManager: {str(e)}")
    analytics_manager = None
except Exception as e:
    logger.error(f"Error initializing AnalyticsManager: {str(e)}")
    analytics_manager = None

def main():
    """Main application entry point"""
    try:
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('visibilitycam.log'),
                logging.StreamHandler()
            ]
        )
        
        # Set Streamlit page config
        UIComponents.setup_page_config()
        
        # Create logger for this module
        logger = logging.getLogger("VisibilityCam")
        
        # Initialize camera managers
        camera_configs = load_camera_configs()
        st.session_state.camera_managers = {}
        
        for camera_id, config in camera_configs.items():
            st.session_state.camera_managers[camera_id] = CameraManager(camera_id, config)
        
        # Initialize weather manager with a default location
        location = "Manila, Philippines"  # Default location
        st.session_state.weather_manager = WeatherManager(location)
        
        # Load configurations
        display_settings = load_display_settings()
        
        # Store configurations in session state
        if 'cameras' not in st.session_state:
            st.session_state.cameras = camera_configs
        else:
            # Update with latest configs
            st.session_state.cameras = camera_configs
        
        # Initialize weather data in session state if not exists
        if 'weather_data' not in st.session_state:
            st.session_state.weather_data = {}
            st.session_state.last_weather_fetch = {}
        
        # Add initial load delay
        if 'initial_load_complete' not in st.session_state:
            st.info("Loading dashboard... Please wait.")
            time.sleep(display_settings.get('initial_load_delay', 3))
            st.session_state.initial_load_complete = True
            st.rerun()
        
        # Initialize cameras data store
        st.session_state.cameras_data = {}
        
        # Initialize camera loading states
        if 'camera_loading_states' not in st.session_state:
            st.session_state.camera_loading_states = {}
        
        # Create sidebar
        if 'selected_camera' not in st.session_state:
            st.session_state.selected_camera = list(camera_configs.keys())[0]
            st.session_state.camera_connected = False
            st.session_state.streaming = True
            st.session_state.last_frame_time = time.time()
            st.session_state.last_analytics_update = time.time() - 60  # Force initial update
            
            # Initialize ROI regions for the first camera
            if 'roi_regions' not in st.session_state:
                st.session_state.roi_regions = camera_configs[st.session_state.selected_camera].get('roi_regions', [])
        
        def on_camera_change(camera_id):
            # Save ROI settings from previous camera
            prev_camera_id = st.session_state.selected_camera
            
            try:
                # Safely disconnect the previous camera
                if prev_camera_id in st.session_state.camera_managers:
                    prev_camera_manager = st.session_state.camera_managers[prev_camera_id]
                    if prev_camera_manager:
                        logger.info(f"Disconnecting previous camera: {prev_camera_id}")
                        prev_camera_manager.disconnect()
                        logger.info(f"Disconnected previous camera: {prev_camera_id}")
                
                # Save ROI regions if they've been modified
                if hasattr(st.session_state, 'roi_regions'):
                    camera_configs[prev_camera_id]['roi_regions'] = st.session_state.roi_regions
                    
                    # Update camera manager with saved ROIs
                    if prev_camera_id in st.session_state.camera_managers:
                        prev_camera_manager = st.session_state.camera_managers[prev_camera_id]
                        if prev_camera_manager:
                            prev_camera_manager.set_roi_regions(st.session_state.roi_regions, normalized=True)
                
                # Save other settings
                if f"color_delta_threshold_{prev_camera_id}" in st.session_state:
                    camera_configs[prev_camera_id]['color_delta_threshold'] = st.session_state[f"color_delta_threshold_{prev_camera_id}"]
                    
                    # Update camera manager with threshold
                    if prev_camera_id in st.session_state.camera_managers:
                        prev_camera_manager = st.session_state.camera_managers[prev_camera_id]
                        if prev_camera_manager:
                            prev_camera_manager.color_delta_threshold = st.session_state[f"color_delta_threshold_{prev_camera_id}"]
                            
                # Reset connection status for the new camera
                st.session_state.camera_connected = False
                
                # Update selected camera
                st.session_state.selected_camera = camera_id
                logger.info(f"Camera changed to: {camera_id}")
                
                # Clear any cached frames for the camera grid
                if 'frame_cache_' + camera_id in st.session_state:
                    st.session_state['frame_cache_' + camera_id] = None
                
                # Load ROI regions for the new camera
                st.session_state.roi_regions = camera_configs[camera_id].get('roi_regions', [])
                
                # Force new camera to connect when page refreshes
                camera_manager = st.session_state.camera_managers[camera_id]
                if camera_manager and not camera_manager.is_connected():
                    # Reset connection attempt counter
                    camera_manager.connection_attempts = 0
                
                # Reset loading state for the camera
                loading_key = f"loading_{camera_id}"
                if loading_key in st.session_state.camera_loading_states:
                    st.session_state.camera_loading_states[loading_key] = True
                
                logger.info(f"Preparing to connect to camera: {camera_id}")
                
            except Exception as e:
                logger.error(f"Error during camera change: {str(e)}")
                st.error(f"Error during camera change: {str(e)}")
                # Still update the selected camera even if there was an error
                st.session_state.selected_camera = camera_id
            
            # Save configurations
            save_camera_configs(camera_configs)
            
            # Set a flag to indicate a camera change happened
            # The page will automatically refresh due to change in selectbox
            st.session_state.camera_changed = True
        
        # Create sidebar
        UIComponents.create_sidebar(camera_configs, st.session_state.selected_camera, on_camera_change)
        
        # Get current camera configuration and status
        camera_config = camera_configs[st.session_state.selected_camera]
        camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
        
        # Ensure ROI regions exist in session state
        if 'roi_regions' not in st.session_state:
            st.session_state.roi_regions = camera_config.get('roi_regions', [])
            # If there are no ROIs in the config, load defaults
            if not st.session_state.roi_regions:
                st.session_state.roi_regions = [
                    {"name": "top-left", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                    {"name": "top-right", "x": 0.7, "y": 0.1, "width": 0.2, "height": 0.2},
                    {"name": "center", "x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}
                ]
        
        # Only process ROI updates if user is actively editing ROIs
        if hasattr(st.session_state, 'roi_editing') and st.session_state.roi_editing:
            if hasattr(st.session_state, 'roi_regions'):
                # Deep copy ROI regions to avoid reference issues
                roi_regions = copy.deepcopy(st.session_state.roi_regions)
                
                # Update camera config with current ROI regions from session state
                camera_config['roi_regions'] = roi_regions
                
                # Update camera manager with current ROI regions 
                camera_manager.set_roi_regions(roi_regions, normalized=True)
                
                # Log the update
                logger.info(f"Updated ROI regions for camera {st.session_state.selected_camera}: {len(roi_regions)} regions")
        
        # Update other settings in camera manager
        if f"color_delta_threshold_{st.session_state.selected_camera}" in st.session_state:
            threshold = st.session_state[f"color_delta_threshold_{st.session_state.selected_camera}"]
            camera_config['color_delta_threshold'] = threshold
            camera_manager.color_delta_threshold = threshold
        
        if f"visibility_threshold_{st.session_state.selected_camera}" in st.session_state:
            threshold = st.session_state[f"visibility_threshold_{st.session_state.selected_camera}"]
            camera_config['visibility_threshold'] = threshold
            camera_manager.visibility_threshold = threshold
        
        if f"recovery_threshold_{st.session_state.selected_camera}" in st.session_state:
            threshold = st.session_state[f"recovery_threshold_{st.session_state.selected_camera}"]
            camera_config['recovery_threshold'] = threshold
            camera_manager.recovery_threshold = threshold
        
        # Connect to camera if not already connected
        if not st.session_state.camera_connected and not camera_manager.is_connected():
            if camera_manager.connect():
                st.session_state.camera_connected = True
            else:
                st.error(f"Failed to connect to camera {st.session_state.selected_camera}")
                return
        
        # Get weather location for current camera
        weather_city = camera_config.get('weather_city', camera_config.get('location', 'Manila'))
        
        # Get weather data with caching to prevent unnecessary API calls
        current_time = time.time()
        weather_fetch_interval = 60  # Default to 1 minute minimum between fetches
        
        # Check if we need to fetch new weather data
        fetch_new_weather = False
        if weather_city not in st.session_state.weather_data:
            # No cached data for this city
            fetch_new_weather = True
        elif weather_city not in st.session_state.last_weather_fetch:
            # No timestamp for last fetch
            fetch_new_weather = True
        else:
            # Get the configured refresh interval for this city
            city_refresh_interval = st.session_state.weather_manager.get_refresh_interval(weather_city) * 60  # convert minutes to seconds
            time_since_last_fetch = current_time - st.session_state.last_weather_fetch[weather_city]
            if time_since_last_fetch >= city_refresh_interval:
                # Time to refresh
                fetch_new_weather = True
                logger.info(f"Weather data refresh interval reached for {weather_city}, fetching new data")
        
        # Fetch new weather data if needed
        if fetch_new_weather:
            weather_data = st.session_state.weather_manager.get_weather(weather_city)
            st.session_state.weather_data[weather_city] = weather_data
            st.session_state.last_weather_fetch[weather_city] = current_time
            logger.info(f"Fetched fresh weather data for {weather_city}")
        else:
            # Use cached data
            weather_data = st.session_state.weather_data[weather_city]
            logger.debug(f"Using cached weather data for {weather_city}")
        
        # Create main content with camera feed container
        feed_container = st.empty()
        
        # Create main content with tabs
        tabs = UIComponents.create_main_content(camera_config, camera_manager.get_status(), weather_data, feed_container)
        
        # Status placeholder for messages
        placeholder = st.empty()
        
        # Frame rate control
        target_fps = display_settings.get('fps', 15)
        frame_interval = 1.0 / target_fps  # Time between frames
        
        # Analytics update interval (30 seconds)
        analytics_interval = 5  # Reduce from 30 to 5 seconds for testing
        
        # Initialize the camera data structure if it doesn't exist yet
        if st.session_state.selected_camera not in st.session_state.cameras_data:
            st.session_state.cameras_data[st.session_state.selected_camera] = {
                'timestamps': [],
                'brightness_history': [],
                'visibility_history': []
            }
        
        # Ensure all cameras have an entry in cameras_data
        for cam_id in camera_configs.keys():
            if cam_id not in st.session_state.cameras_data:
                st.session_state.cameras_data[cam_id] = {
                    'timestamps': [],
                    'brightness_history': [],
                    'visibility_history': []
                }
        
        # Force an immediate analytics update
        st.session_state.last_analytics_update = time.time() - analytics_interval - 1
        
        # Streaming loop with controlled frame rate
        while st.session_state.streaming and camera_manager.is_connected():
            try:
                # Calculate time since last frame
                current_time = time.time()
                time_since_last_frame = current_time - st.session_state.last_frame_time
                
                # Update analytics data periodically
                if analytics_manager and current_time - st.session_state.last_analytics_update > analytics_interval:
                    # First update the selected camera (which is already being processed)
                    camera_status = camera_manager.get_status()
                    
                    # Initialize camera data if it doesn't exist
                    if st.session_state.selected_camera not in st.session_state.cameras_data:
                        st.session_state.cameras_data[st.session_state.selected_camera] = {
                            'timestamps': [],
                            'brightness_history': [],
                            'visibility_history': []
                        }
                    
                    # Get the camera data for the current camera
                    camera_data = st.session_state.cameras_data[st.session_state.selected_camera]
                    
                    # Update all metrics
                    camera_data['color_deltas'] = camera_manager.color_deltas
                    camera_data['brightness'] = camera_status.get('brightness', 0)
                    camera_data['contrast'] = camera_status.get('contrast', 0)
                    camera_data['sharpness'] = camera_status.get('sharpness', 0)
                    camera_data['edge_score'] = camera_status.get('edge_score', 0)
                    camera_data['visibility_score'] = camera_status.get('visibility_score', 0)
                    camera_data['color_delta_avg'] = camera_status.get('color_delta_avg', 0)
                    camera_data['visibility_status'] = camera_status.get('visibility_status', 'Unknown')
                    
                    # Store data for history graphs
                    current_time_dt = datetime.now()
                    camera_data['timestamps'].append(current_time_dt)
                    camera_data['brightness_history'].append(camera_data['brightness'])
                    
                    # Store visibility history including distance information
                    if 'visibility_history' not in camera_data:
                        camera_data['visibility_history'] = []
                        
                    visibility_entry = {
                        'timestamp': current_time_dt,
                        'score': camera_data['visibility_score'],
                        'status': camera_data['visibility_status'],
                        'brightness': camera_data['brightness']
                    }
                    
                    # Add visibility distance if available
                    if hasattr(camera_manager, 'visibility_distance'):
                        visibility_entry['visibility_distance'] = camera_manager.visibility_distance
                        
                    camera_data['visibility_history'].append(visibility_entry)
                    
                    # Keep only last 100 data points
                    if len(camera_data['timestamps']) > 100:
                        camera_data['timestamps'] = camera_data['timestamps'][-100:]
                        camera_data['brightness_history'] = camera_data['brightness_history'][-100:]
                        camera_data['visibility_history'] = camera_data['visibility_history'][-100:]
                    
                    # Store updated data back to session state
                    st.session_state.cameras_data[st.session_state.selected_camera] = camera_data
                    
                    # Now update analytics for all other connected cameras
                    for cam_id, cam_manager in st.session_state.camera_managers.items():
                        # Skip the currently selected camera which was already processed
                        if cam_id == st.session_state.selected_camera:
                            continue
                            
                        # Only process cameras that are connected
                        if cam_manager.is_connected():
                            # Get camera status
                            try:
                                cam_status = cam_manager.get_status()
                                
                                # Initialize camera data if it doesn't exist
                                if cam_id not in st.session_state.cameras_data:
                                    st.session_state.cameras_data[cam_id] = {
                                        'timestamps': [],
                                        'brightness_history': [],
                                        'visibility_history': []
                                    }
                                
                                # Get the camera data
                                cam_data = st.session_state.cameras_data[cam_id]
                                
                                # Update metrics
                                cam_data['color_deltas'] = cam_manager.color_deltas
                                cam_data['brightness'] = cam_status.get('brightness', 0)
                                cam_data['contrast'] = cam_status.get('contrast', 0)
                                cam_data['sharpness'] = cam_status.get('sharpness', 0)
                                cam_data['edge_score'] = cam_status.get('edge_score', 0)
                                cam_data['visibility_score'] = cam_status.get('visibility_score', 0)
                                cam_data['color_delta_avg'] = cam_status.get('color_delta_avg', 0)
                                cam_data['visibility_status'] = cam_status.get('visibility_status', 'Unknown')
                                
                                # Store data for history
                                cam_data['timestamps'].append(current_time_dt)
                                cam_data['brightness_history'].append(cam_data['brightness'])
                                
                                # Store visibility history
                                if 'visibility_history' not in cam_data:
                                    cam_data['visibility_history'] = []
                                    
                                cam_visibility_entry = {
                                    'timestamp': current_time_dt,
                                    'score': cam_data['visibility_score'],
                                    'status': cam_data['visibility_status'],
                                    'brightness': cam_data['brightness']
                                }
                                
                                # Add visibility distance if available
                                if hasattr(cam_manager, 'visibility_distance'):
                                    cam_visibility_entry['visibility_distance'] = cam_manager.visibility_distance
                                    
                                cam_data['visibility_history'].append(cam_visibility_entry)
                                
                                # Keep only last 100 data points
                                if len(cam_data['timestamps']) > 100:
                                    cam_data['timestamps'] = cam_data['timestamps'][-100:]
                                    cam_data['brightness_history'] = cam_data['brightness_history'][-100:]
                                    cam_data['visibility_history'] = cam_data['visibility_history'][-100:]
                                
                                # Update analytics database
                                if analytics_manager:
                                    analytics_manager.update_daily_stats(
                                        camera_id=cam_id,
                                        brightness=cam_status.get('brightness', 0),
                                        contrast=cam_status.get('contrast', 0),
                                        visibility_score=cam_status.get('visibility_score', 0),
                                        visibility_status=cam_status.get('visibility_status', 'Unknown')
                                    )
                                
                                # Store updated data back to session state
                                st.session_state.cameras_data[cam_id] = cam_data
                                
                            except Exception as e:
                                logger.error(f"Error updating analytics for camera {cam_id}: {str(e)}")
                    
                    # Update analytics with current camera metrics
                    if analytics_manager:
                        analytics_manager.update_daily_stats(
                            camera_id=st.session_state.selected_camera,
                            brightness=camera_status.get('brightness', 0),
                            contrast=camera_status.get('contrast', 0),
                            visibility_score=camera_status.get('visibility_score', 0),
                            visibility_status=camera_status.get('visibility_status', 'Unknown')
                        )
                        
                        # Log analytics update
                        logger.info(f"Updated analytics for all cameras")
                    
                    st.session_state.last_analytics_update = current_time
                
                # Skip frames if we're updating too fast
                if time_since_last_frame < frame_interval:
                    time.sleep(max(0, frame_interval - time_since_last_frame) * 0.8)  # Add 20% margin
                    continue
                
                # Read frame from buffer
                frame = camera_manager.read_frame()
                if frame is not None and frame.size > 0:
                    # Only show ROI overlay if enabled in settings
                    if hasattr(st.session_state, 'show_roi') and st.session_state.show_roi:
                        # ROI overlay is already added by the camera manager's _process_frame method
                        pass
                    
                    # Display frame
                    feed_container.image(frame, channels="BGR", use_container_width=True)
                    st.session_state.last_frame_time = time.time()
                    
                    # Write frame to recording if active
                    camera_manager.write_frame(frame)
                    
                else:
                    # If frame is invalid and camera is disconnected, try to reconnect
                    if not camera_manager.is_connected():
                        placeholder.warning("Camera disconnected. Attempting to reconnect...")
                        camera_manager.reconnect()
                        if not camera_manager.is_connected():
                            placeholder.error("Failed to reconnect. Click 'Reconnect Camera' to try again manually.")
                            break
                        placeholder.success("Camera reconnected successfully.")
                        continue
                    
                    # Add short delay if no frame is available
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in streaming loop: {str(e)}")
                placeholder.error(f"Error: {str(e)}")
                if not camera_manager.is_connected():
                    # Attempt to reconnect automatically
                    placeholder.warning("Attempting to reconnect due to error...")
                    if camera_manager.reconnect():
                        placeholder.success("Camera reconnected successfully after error.")
                        continue
                    else:
                        placeholder.error("Failed to reconnect after error.")
                        break
                time.sleep(1)  # Wait a bit before retrying
                continue
        
        # Update save_roi_configuration button in UI Component to directly save to config
        if 'save_roi_button_clicked' in st.session_state and st.session_state.save_roi_button_clicked:
            if hasattr(st.session_state, 'roi_regions'):
                try:
                    # Update camera config with the latest ROI regions
                    roi_regions = copy.deepcopy(st.session_state.roi_regions)
                    camera_configs[st.session_state.selected_camera]['roi_regions'] = roi_regions
                    
                    # Set normalized flag in config
                    camera_configs[st.session_state.selected_camera]['roi_regions_normalized'] = True
                    
                    # Save to disk
                    save_camera_configs(camera_configs)
                    
                    # Update camera manager directly
                    camera_manager.set_roi_regions(roi_regions, normalized=True)
                    
                    # Clear flag
                    st.session_state.save_roi_button_clicked = False
                    
                    logger.info(f"Saved ROI configuration for camera {st.session_state.selected_camera}")
                    st.success("ROI configuration saved successfully")
                except Exception as e:
                    logger.error(f"Error saving ROI configuration: {str(e)}")
                    st.error(f"Error saving ROI configuration: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error in main application: {str(e)}")
        st.error(f"An error occurred: {str(e)}")
        st.info("Please check the logs for more details")

if __name__ == "__main__":
    main() 