import streamlit as st
import cv2
import numpy as np
from pathlib import Path
import os
import sys
import time
import logging

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.config import load_camera_configs
from src.core.simple_camera import SimpleCamera
from src.utils.logger import setup_logger
from src.config.settings import DEFAULT_CAMERA_CONFIG

# Initialize logger
logger = setup_logger()

def create_placeholder_frame(width=640, height=360):
    """Create a placeholder frame with status text"""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame.fill(50)  # Dark gray background
    return frame

def add_status_text(frame, text, color=(255, 255, 255)):
    """Add status text to a frame"""
    height, width = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    thickness = 2
    
    # Get text size
    (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
    
    # Calculate position to center text
    x = (width - text_width) // 2
    y = (height + text_height) // 2
    
    # Add text
    cv2.putText(frame, text, (x, y), font, font_scale, color, thickness)
    return frame

def main():
    """Simple dashboard to view multiple camera streams"""
    try:
        st.set_page_config(
            page_title="Camera Dashboard",
            page_icon="📹",
            layout="wide"
        )
        
        st.title("Camera Dashboard")
        
        # Add refresh controls
        col1, col2 = st.columns(2)
        with col1:
            refresh_rate = st.slider("Refresh Rate (seconds)", 0.1, 5.0, 0.5, 0.1)
        with col2:
            auto_refresh = st.checkbox("Auto Refresh", value=True)
        
        # Load camera configurations
        try:
            cameras = load_camera_configs()
            if not cameras:
                st.error("No camera configurations found. Please check your settings.")
                return
        except Exception as e:
            st.error(f"Failed to load camera configurations: {str(e)}")
            return
        
        # Initialize cameras in session state if not exists
        if 'cameras' not in st.session_state:
            st.session_state.cameras = {}
            for camera_id, config in cameras.items():
                try:
                    st.session_state.cameras[camera_id] = SimpleCamera(camera_id, config)
                    st.session_state.cameras[camera_id].connect()
                except Exception as e:
                    st.error(f"Failed to initialize camera {camera_id}: {str(e)}")
        
        # Camera selection
        selected_camera = st.selectbox(
            "Select Camera to Focus",
            options=["All Cameras"] + list(cameras.keys()),
            key="selected_camera"
        )
        
        # Display mode selection
        display_mode = st.radio(
            "Display Mode",
            ["Grid View", "Single Camera"],
            horizontal=True
        )
        
        # Debug information
        with st.expander("Debug Information"):
            st.write("Camera Status:")
            for camera_id, camera in st.session_state.cameras.items():
                st.write(f"- {camera_id}:")
                st.write(f"  Connected: {camera.is_connected}")
                st.write(f"  Connection Attempts: {camera.connection_attempts}")
                st.write(f"  RTSP URL: {camera.rtsp_url}")
                st.write(f"  Last Frame Time: {time.strftime('%H:%M:%S', time.localtime(camera.last_frame_time)) if camera.last_frame_time > 0 else 'Never'}")
        
        # Create a container for the camera feeds
        feed_container = st.container()
        
        # Display camera feeds
        with feed_container:
            if display_mode == "Grid View" or selected_camera == "All Cameras":
                # Calculate grid dimensions based on number of cameras
                num_cameras = len(cameras)
                cols = min(4, num_cameras)  # Max 4 columns
                rows = (num_cameras + cols - 1) // cols  # Calculate rows needed
                
                # Create grid of cameras
                for i in range(rows):
                    cols_list = st.columns(cols)
                    for j in range(cols):
                        camera_idx = i * cols + j
                        if camera_idx < num_cameras:
                            camera_id = list(cameras.keys())[camera_idx]
                            camera = st.session_state.cameras[camera_id]
                            
                            with cols_list[j]:
                                st.subheader(camera_id)
                                
                                try:
                                    # Read and display frame
                                    frame = camera.read_frame()
                                    if frame is not None:
                                        # Convert BGR to RGB
                                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                        st.image(frame_rgb, use_container_width=True)
                                    else:
                                        # Create placeholder frame with status
                                        placeholder = create_placeholder_frame()
                                        if not camera.is_connected:
                                            status_text = "Connecting..." if camera.connection_attempts < camera.max_connection_attempts else "Connection Failed"
                                        else:
                                            status_text = "No Signal"
                                        placeholder = add_status_text(placeholder, status_text)
                                        st.image(placeholder, use_container_width=True)
                                    
                                    # Connection status with color
                                    if camera.is_connected:
                                        st.success("Connected")
                                    else:
                                        st.error("Disconnected")
                                        if st.button(f"Reconnect {camera_id}"):
                                            camera.connect()
                                except Exception as e:
                                    st.error(f"Error displaying camera {camera_id}: {str(e)}")
            else:
                # Single camera view
                camera = st.session_state.cameras[selected_camera]
                st.subheader(selected_camera)
                
                try:
                    # Read and display frame
                    frame = camera.read_frame()
                    if frame is not None:
                        # Convert BGR to RGB
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        st.image(frame_rgb, use_container_width=True)
                    else:
                        # Create placeholder frame with status
                        placeholder = create_placeholder_frame(width=1280, height=720)
                        if not camera.is_connected:
                            status_text = "Connecting..." if camera.connection_attempts < camera.max_connection_attempts else "Connection Failed"
                        else:
                            status_text = "No Signal"
                        placeholder = add_status_text(placeholder, status_text)
                        st.image(placeholder, use_container_width=True)
                    
                    # Connection status
                    if camera.is_connected:
                        st.success("Connected")
                    else:
                        st.error("Disconnected")
                        if st.button("Reconnect"):
                            camera.connect()
                except Exception as e:
                    st.error(f"Error displaying camera {selected_camera}: {str(e)}")
        
        # Add manual refresh button
        if not auto_refresh:
            if st.button("Refresh"):
                st.session_state.clear()
                st.experimental_rerun()
                
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
        logger.error(f"Dashboard error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 