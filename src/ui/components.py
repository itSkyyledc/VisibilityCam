import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import cv2
import numpy as np
import os
import sqlite3
import threading
import time
import logging
from queue import Queue
from ..config.settings import DEFAULT_DISPLAY_SETTINGS, RECORDINGS_DIR, HIGHLIGHTS_DIR
import plotly.express as px

# Configure logger
logger = logging.getLogger(__name__)

class UIComponents:
    @staticmethod
    def setup_page_config():
        """Setup Streamlit page configuration"""
        st.set_page_config(
            page_title="Visibility Camera Dashboard",
            page_icon="🌫️",
            layout="wide",
            initial_sidebar_state="expanded"
        )
    
    @staticmethod
    def setup_css():
        """Setup custom CSS styles"""
        st.markdown("""
        <style>
            /* Main theme colors */
            :root {
                --primary-color: #1E88E5;
                --secondary-color: #0D47A1;
                --background-color: transparent;
                --card-background: transparent;
                --text-color: #212121;
                --border-color: #e0e0e0;
            }
            
            /* Override Streamlit's base container */
            .stApp {
                background-color: transparent !important;
            }
            
            .element-container, div.block-container {
                background-color: transparent !important;
            }
            
            /* Main container */
            .main {
                background-color: transparent !important;
            }
            
            /* Header styles */
            .main-header {
                font-size: 2.5rem;
                margin-bottom: 1rem;
                color: var(--primary-color);
                text-align: center;
                font-weight: 600;
                background-color: transparent !important;
            }
            
            /* Sub-header styles */
            .sub-header {
                font-size: 1.5rem;
                margin-top: 1rem;
                margin-bottom: 0.5rem;
                color: var(--secondary-color);
                font-weight: 500;
                background-color: transparent !important;
            }
            
            /* Card styles */
            .card {
                background-color: transparent !important;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
            }
            
            /* Status indicators */
            .indicator {
                font-size: 1.2rem;
                font-weight: 500;
                display: inline-block;
                padding: 8px 16px;
                border-radius: 5px;
                margin: 4px;
            }
            
            .good-visibility {
                background-color: #e8f5e9;
                color: #2e7d32;
                border: 1px solid #a5d6a7;
            }
            
            .poor-visibility {
                background-color: #ffebee;
                color: #c62828;
                border: 1px solid #ef9a9a;
            }
            
            /* Camera selector */
            .camera-selector {
                background-color: transparent !important;
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 20px;
            }
            
            /* Button styles */
            .stButton button {
                background-color: var(--primary-color);
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: 500;
                transition: background-color 0.3s;
            }
            
            .stButton button:hover {
                background-color: var(--secondary-color);
            }
            
            /* Input styles */
            .stTextInput input, .stNumberInput input, .stSelectbox select {
                border: 1px solid var(--border-color);
                border-radius: 5px;
                padding: 8px;
                background-color: transparent !important;
            }
            
            /* Metric styles */
            .stMetric {
                background-color: transparent !important;
                border-radius: 5px;
                padding: 10px;
                margin: 5px;
            }
            
            /* Tab styles */
            .stTabs [data-baseweb="tab-list"] {
                gap: 2px;
                background-color: transparent !important;
            }
            
            .stTabs [data-baseweb="tab"] {
                background-color: transparent !important;
                border-radius: 5px 5px 0 0;
                padding: 10px 20px;
            }
            
            .stTabs [data-baseweb="tab-panel"] {
                background-color: transparent !important;
            }

            /* Override Streamlit's default backgrounds */
            div[data-testid="stMetricValue"],
            div[data-testid="stMetricDelta"],
            div[data-testid="stMetricLabel"],
            div[data-testid="stVerticalBlock"],
            div[data-testid="stHorizontalBlock"],
            div[data-testid="stMarkdown"],
            div[class^="st-"],
            section[data-testid="stSidebar"],
            div[class="stPlotlyChart"] {
                background-color: transparent !important;
            }

            /* Make plotly charts background transparent */
            .js-plotly-plot .plotly .main-svg,
            .js-plotly-plot .plotly .modebar {
                background: transparent !important;
            }
            
            /* Override any white backgrounds */
            div {
                background-color: transparent !important;
            }
            
            /* Ensure text remains visible */
            .stMarkdown, .stText {
                color: var(--text-color) !important;
            }
            
            /* Style the tab content area */
            .stTabContent {
                background-color: transparent !important;
                padding: 1rem 0;
            }
            
            /* Style the sidebar */
            section[data-testid="stSidebar"] > div {
                background-color: transparent !important;
            }
            
            /* Style all containers */
            .stContainer, .element-container {
                background-color: transparent !important;
            }
        </style>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def create_sidebar(cameras, selected_camera, on_camera_change):
        """Create the sidebar with camera selection and settings"""
        st.sidebar.title("Visibility Camera Dashboard")
        
        # Camera selection dropdown
        st.sidebar.subheader("Camera Selection")
        camera_names = {cam_id: config['name'] for cam_id, config in cameras.items()}
        
        # Use URL parameter as a safe way to change camera
        selected = st.sidebar.selectbox(
            "Select Camera",
            options=list(cameras.keys()),
            format_func=lambda x: camera_names.get(x, x),
            index=list(cameras.keys()).index(selected_camera) if selected_camera in cameras else 0,
            key="camera_selector"
        )
        
        # Check if camera selection changed
        if selected != selected_camera:
            on_camera_change(selected)
        
        # Manual reconnect button
        if st.sidebar.button("Reconnect Camera", use_container_width=True):
            try:
                camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
                camera_manager.connection_attempts = 0  # Reset connection attempts
                if camera_manager.reconnect():
                    st.session_state.camera_connected = True
                    st.sidebar.success("Camera reconnected successfully")
                else:
                    st.sidebar.error("Failed to reconnect camera")
            except Exception as e:
                st.sidebar.error(f"Error reconnecting: {str(e)}")
        
        # Create sidebar sections
        st.sidebar.markdown("---")
        UIComponents._create_stream_settings_section()
        st.sidebar.markdown("---")
        UIComponents._create_display_settings_section()
        st.sidebar.markdown("---")
        UIComponents._create_weather_settings_section()
        st.sidebar.markdown("---")
        UIComponents._create_analytics_settings_section()
        
        return selected
    
    @staticmethod
    def create_main_content(camera_config, camera_status, weather_data, feed_container):
        """Create the main content with tabs"""
        # Create tabs for different sections
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
            "📡 Live Monitoring",
            "📊 Analytics",
            "🌦️ Weather Insights",
            "🔍 ROI Configuration",
            "📼 Recordings",
            "🔍 Highlights",
            "📆 Historical Data",
            "📹 Camera Grid",
            "📋 Dashboard Overview"
        ])
        
        # Live monitoring tab
        with tab1:
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("Refresh Feed", key="ui_refresh_feed_btn"):
                    st.rerun()
            with col2:
                if st.button("Reconnect Camera", key="ui_reconnect_camera_btn"):
                    st.session_state.camera_connected = False
                    st.rerun()
            with col3:
                if st.button("Stop" if st.session_state.streaming else "Start", key="ui_stream_control_btn"):
                    st.session_state.streaming = not st.session_state.streaming
                    st.rerun()
            
            # Display camera feed placeholder
            st.markdown("### Live Feed")
            feed_container

            # Display camera metrics in a condensed format
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Temperature", f"{weather_data['temperature']}°C")
                st.metric("Humidity", f"{weather_data['humidity']}%")
            with col2:
                st.metric("Visibility", f"{weather_data['visibility']} km")
                st.metric("Condition", weather_data['condition'])
        
        # Analytics tab
        with tab2:
            if 'selected_camera' in st.session_state:
                # Pass the camera manager object instead of camera_data
                camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
                UIComponents.create_analytics_tab(camera_manager)
            else:
                st.info("No analytics data available yet. This section will update once data is collected.")
        
        # Weather tab
        with tab3:
            UIComponents.create_weather_tab(weather_data)
        
        # ROI Configuration tab
        with tab4:
            if 'selected_camera' in st.session_state:
                camera_config = st.session_state.cameras[st.session_state.selected_camera]
                camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
                threshold_changes = UIComponents._create_roi_config_tab(camera_config, camera_manager)
                if threshold_changes is not None:
                    # Update camera config with new threshold values
                    for key, value in threshold_changes.items():
                        camera_config[key] = value
            else:
                st.info("Please select a camera to configure ROIs.")
        
        # Recordings tab
        with tab5:
            if 'selected_camera' in st.session_state:
                # Pass the camera manager object instead of just the camera ID
                camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
                UIComponents.create_recordings_tab(camera_manager)
            else:
                st.info("No recordings available. Please select a camera.")
        
        # Highlights tab
        with tab6:
            if 'selected_camera' in st.session_state:
                # Pass the camera manager object instead of just the camera ID
                camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
                UIComponents.create_highlights_tab(camera_manager)
            else:
                st.info("No highlights available. Please select a camera.")
        
        # Historical data tab
        with tab7:
            if 'selected_camera' in st.session_state:
                # Pass the camera manager object instead of just the camera ID
                camera_manager = st.session_state.camera_managers[st.session_state.selected_camera]
                UIComponents.create_historical_tab(camera_manager)
            else:
                st.info("No historical data available. Please select a camera.")
        
        # Camera Grid tab
        with tab8:
            UIComponents.create_camera_grid_tab()
            
        # Dashboard Overview tab
        with tab9:
            UIComponents.create_dashboard_overview()
            
        return (tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9)
    
    @staticmethod
    def update_feed(feed_container, camera_manager, message_queue):
        """Background thread function to update the camera feed"""
        last_update_time = time.time()
        min_interval = 0.1  # Minimum time between updates (100ms)
        
        while True:
            try:
                current_time = time.time()
                # Check if enough time has passed since last update
                if current_time - last_update_time < min_interval:
                    time.sleep(0.01)  # Short sleep to prevent CPU hogging
                    continue
                
                frame = camera_manager.read_frame()
                if frame is not None:
                    # Convert frame to RGB for display
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Add timestamp to frame
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cv2.putText(frame_rgb, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    # Send frame and timestamp through queue
                    message_queue.put({
                        'type': 'frame',
                        'data': (frame_rgb, timestamp)
                    })
                    last_update_time = current_time
                else:
                    # Only send error message if enough time has passed
                    if current_time - last_update_time >= 1.0:
                        message_queue.put({
                            'type': 'error',
                            'data': "No frame available from camera"
                        })
                        last_update_time = current_time
                    time.sleep(0.1)
                
            except Exception as e:
                # Only send error message if enough time has passed
                if time.time() - last_update_time >= 1.0:
                    message_queue.put({
                        'type': 'error',
                        'data': f"Error updating feed: {str(e)}"
                    })
                    last_update_time = time.time()
                time.sleep(0.1)

    @staticmethod
    def create_live_monitoring_tab(camera_config, camera_status, weather_data):
        """Create the live monitoring tab"""
        st.header("Live Camera Feed")
        
        # Initialize camera manager in session state if not exists
        if 'camera_manager' not in st.session_state:
            # Get camera manager from the current camera's manager
            camera_manager = st.session_state.camera_managers[camera_config['name']]
            st.session_state.camera_manager = camera_manager
            st.session_state.camera_connected = False
            st.session_state.feed_thread = None
            st.session_state.message_queue = Queue()
            st.session_state.last_update = None
            st.session_state.last_refresh = time.time()
        
        # Create feed container
        feed_container = st.empty()
        
        # Create status container
        status_container = st.container()
        
        # Create controls container
        controls_container = st.container()
        
        # Check camera connection
        if not st.session_state.camera_connected:
            if st.session_state.camera_manager.connect():
                st.session_state.camera_connected = True
                st.success("Camera connected successfully!")
            else:
                st.error("Failed to connect to camera. Please check the connection and try again.")
        
        # Display camera feed
        if st.session_state.camera_connected:
            # Start feed update thread if not running
            if not st.session_state.feed_thread or not st.session_state.feed_thread.is_alive():
                st.session_state.feed_thread = threading.Thread(
                    target=UIComponents.update_feed,
                    args=(feed_container, st.session_state.camera_manager, st.session_state.message_queue),
                    daemon=True
                )
                st.session_state.feed_thread.start()
            
            # Process messages from the queue with rate limiting
            current_time = time.time()
            if current_time - st.session_state.last_refresh >= st.session_state.refresh_rate:
                messages_processed = 0
                max_messages_per_refresh = 5  # Limit number of messages processed per refresh
                
                while not st.session_state.message_queue.empty() and messages_processed < max_messages_per_refresh:
                    try:
                        msg = st.session_state.message_queue.get_nowait()
                        if msg['type'] == 'frame':
                            frame_rgb, timestamp = msg['data']
                            feed_container.image(frame_rgb, use_container_width=True)
                            st.session_state.last_update = timestamp
                        elif msg['type'] == 'error':
                            st.error(msg['data'])
                        messages_processed += 1
                    except:
                        break
                
                st.session_state.last_refresh = current_time
            
            # Display last update time
            if st.session_state.last_update:
                status_container.text(f"Last update: {st.session_state.last_update}")
            
            # Add manual refresh and reconnect buttons
            col1, col2 = controls_container.columns(2)
            with col1:
                if st.button("Refresh Feed"):
                    if st.session_state.feed_thread and st.session_state.feed_thread.is_alive():
                        st.session_state.feed_thread.join(timeout=1.0)
                    # Clear the message queue
                    while not st.session_state.message_queue.empty():
                        st.session_state.message_queue.get_nowait()
                    # Start new thread
                    st.session_state.feed_thread = threading.Thread(
                        target=UIComponents.update_feed,
                        args=(feed_container, st.session_state.camera_manager, st.session_state.message_queue),
                        daemon=True
                    )
                    st.session_state.feed_thread.start()
                    st.session_state.last_refresh = time.time()
            
            with col2:
                if st.button("Reconnect Camera"):
                    if st.session_state.feed_thread and st.session_state.feed_thread.is_alive():
                        st.session_state.feed_thread.join(timeout=1.0)
                    st.session_state.camera_manager.disconnect()
                    st.session_state.camera_connected = False
                    # Clear the message queue
                    while not st.session_state.message_queue.empty():
                        st.session_state.message_queue.get_nowait()
                    st.rerun()
        else:
            st.warning("Camera disconnected. Click 'Reconnect Camera' to try again.")
            if st.button("Reconnect Camera"):
                st.session_state.camera_connected = False
                st.rerun()
    
    @staticmethod
    def create_analytics_tab(camera_manager):
        """Creates the analytics tab with metrics and visualizations"""
        st.subheader("Camera Analytics")
        
        # Check if camera manager is available
        if camera_manager is None:
            st.warning("No camera is currently selected. Please select a camera to view analytics.")
            return
        
        try:
            # Get camera data with error handling
            camera_data = camera_manager.get_camera_data()
            
            # Check if we have valid metrics data, regardless of connection status
            has_valid_data = camera_data.get('frames_processed', 0) > 0 or camera_data.get('visibility_score', 0) > 0
            
            # If not connected but we have some data, still show the analytics
            if not camera_manager.is_connected() and not has_valid_data:
                st.warning("Camera is not connected or has not processed any frames yet. Connect to the camera to view analytics.")
                # Add a reconnect button
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Reconnect Camera"):
                        with st.spinner("Reconnecting to camera..."):
                            success = camera_manager.reconnect()
                            if success:
                                st.success("Successfully reconnected!")
                                time.sleep(1)  # Give time for user to see message
                                st.experimental_rerun()
                            else:
                                st.error("Failed to reconnect. Please check camera settings and try again.")
                with col2:
                    if st.button("Generate Test Metrics"):
                        with st.spinner("Generating test data..."):
                            camera_manager.force_update_metrics()
                            st.success("Test metrics generated!")
                            time.sleep(1)
                            st.experimental_rerun()
                return
            
            # Only proceed if camera is connected
            if not camera_manager.is_connected():
                st.warning("Camera is not connected. Connect to the camera to view analytics.")
                # Add a reconnect button
                if st.button("Reconnect Camera"):
                    with st.spinner("Reconnecting to camera..."):
                        success = camera_manager.reconnect()
                        if success:
                            st.success("Successfully reconnected!")
                            time.sleep(1)  # Give time for user to see message
                            st.experimental_rerun()
                        else:
                            st.error("Failed to reconnect. Please check camera settings and try again.")
                return
            
            # Helper method to create metrics with tooltips
            def metric_with_tooltip(label, value, delta=None, tooltip="", help_text=""):
                col = st.column_config.Column(
                    label, help=help_text
                )
                with st.container():
                    metric = st.metric(label, value, delta)
                    if tooltip:
                        st.markdown(f"<small><i>{tooltip}</i></small>", unsafe_allow_html=True)
                return metric
            
            try:
                # Get camera data with error handling
                camera_data = camera_manager.get_camera_data()
                
                # Create three columns for metrics
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # Get the current brightness value and format it
                    brightness = camera_data.get('brightness', 0)
                    brightness_text = f"{brightness:.1f}" if brightness is not None else "N/A"
                    
                    # Display the brightness metric with a tooltip
                    metric_with_tooltip("Brightness", brightness_text, 
                                    tooltip="Average pixel brightness (0-255)",
                                    help_text="Average pixel intensity; higher values indicate brighter images")
                    
                    # Get the current edge score and format it
                    edge_score = camera_data.get('edge_score', 0)
                    edge_score_text = f"{edge_score:.1f}%" if edge_score is not None else "N/A"
                    
                    # Display the edge score metric with a tooltip
                    metric_with_tooltip("Edge Score", edge_score_text,
                                    tooltip="Edge density in the image",
                                    help_text="Measures the amount of detail/edges detected in the image")
                    
                    # Get color diversity value
                    color_diversity = camera_data.get('color_diversity', 0)
                    color_diversity_text = f"{color_diversity:.1f}%" if color_diversity is not None else "N/A"
                    
                    # Display color diversity metric with tooltip
                    metric_with_tooltip("Color Diversity", color_diversity_text,
                                    tooltip="Variety of distinct colors in the image",
                                    help_text="Higher values indicate more color variation, which can help with detection")
                
                with col2:
                    # Get the current contrast value and format it
                    contrast = camera_data.get('contrast', 0)
                    contrast_text = f"{contrast:.1f}" if contrast is not None else "N/A"
                    
                    # Display the contrast metric with a tooltip
                    metric_with_tooltip("Contrast", contrast_text,
                                    tooltip="Standard deviation of pixel values",
                                    help_text="Measures the difference between light and dark areas; higher values indicate higher contrast")
                    
                    # Get the current visibility score and format it
                    visibility_score = camera_data.get('visibility_score', 0)
                    visibility_text = f"{visibility_score:.1f}%" if visibility_score is not None else "N/A"
                    
                    # Display the visibility score metric with a tooltip
                    metric_with_tooltip("Visibility Score", visibility_text,
                                    tooltip="Overall visibility quality score",
                                    help_text="Combined score based on brightness, contrast, edges, and color stability")
                    
                    # Get noise level value
                    noise_level = camera_data.get('noise_level', 0)
                    noise_level_text = f"{noise_level:.1f}%" if noise_level is not None else "N/A"
                    
                    # Display noise level metric with tooltip
                    metric_with_tooltip("Noise Level", noise_level_text,
                                    tooltip="Estimated image noise",
                                    help_text="Lower values indicate cleaner images with less noise/grain")
                
                with col3:
                    # Get the current sharpness value and format it
                    sharpness = camera_data.get('sharpness', 0)
                    sharpness_text = f"{sharpness:.1f}" if sharpness is not None else "N/A"
                    
                    # Display the sharpness metric with a tooltip
                    metric_with_tooltip("Sharpness", sharpness_text,
                                    tooltip="Image detail/focus measure",
                                    help_text="Higher values indicate sharper, more detailed images")
                    
                    # Get the current visibility distance and format it
                    visibility_distance = None
                    if 'visibility_history' in camera_data and camera_data['visibility_history']:
                        latest_entry = camera_data['visibility_history'][-1]
                        if 'visibility_distance' in latest_entry:
                            visibility_distance = latest_entry['visibility_distance']
                    
                    visibility_distance_text = f"{visibility_distance:.1f}m" if visibility_distance is not None else "N/A"
                    
                    # Display the visibility distance metric with a tooltip
                    metric_with_tooltip("Estimated Visibility Distance", visibility_distance_text,
                                    tooltip="Estimated clear visibility distance",
                                    help_text="Maximum distance at which objects can be clearly seen based on current conditions")
                    
                    # Get the current avg color delta and format it
                    color_delta = camera_data.get('color_delta_avg', 0)
                    color_delta_text = f"{color_delta:.1f}" if color_delta is not None else "N/A"
                    
                    # Display the color delta metric with a tooltip
                    metric_with_tooltip("Color Delta", color_delta_text,
                                    tooltip="Average color change in ROIs",
                                    help_text="Measures how much colors have changed from reference; higher values indicate more change")
            except Exception as e:
                st.error(f"Error retrieving camera data: {str(e)}")
                logger.error(f"Error in analytics tab: {str(e)}")
            
            # Visibility score explanation
            st.subheader("Visibility Score Explanation")
            st.info("""
            The visibility score is calculated based on multiple factors:
            - **Brightness (25%)**: Optimal values are between 40-200 (out of 255)
            - **Contrast (20%)**: Higher contrast (up to a point) improves visibility
            - **Edge Detection (25%)**: More edges indicate more visible details
            - **Color Stability (30%)**: Lower color changes in regions of interest indicate better visibility
            
            A score above 70% indicates good visibility conditions.
            """)
            
            # Analytics settings and refresh options
            st.subheader("Analytics Configuration")
            col_refresh1, col_refresh2 = st.columns([1, 1])
            
            with col_refresh1:
                if st.button("Update Metrics Now", key="update_analytics_now_btn"):
                    with st.spinner("Updating metrics..."):
                        success = camera_manager._update_analytics()
                        if success:
                            st.success("Analytics updated successfully")
                            time.sleep(1)  # Brief pause to show success message
                            st.experimental_rerun()
                        else:
                            st.error("Failed to update analytics")
            
            with col_refresh2:
                refresh_interval = getattr(camera_manager, 'analytics_refresh_interval', 5)
                analytics_enabled = getattr(camera_manager, 'analytics_enabled', True)
                last_update = getattr(camera_manager, 'last_analytics_update', 0)
                
                if last_update > 0:
                    time_since_update = time.time() - last_update
                    st.info(f"""
                    **Analytics Settings:**
                    - Auto-update: {'Enabled' if analytics_enabled else 'Disabled'}
                    - Refresh interval: {refresh_interval} seconds
                    - Last update: {int(time_since_update)} seconds ago
                    """)
                else:
                    st.info(f"""
                    **Analytics Settings:**
                    - Auto-update: {'Enabled' if analytics_enabled else 'Disabled'}
                    - Refresh interval: {refresh_interval} seconds
                    - Last update: Never
                    """)
            
            # Camera performance and status
            st.subheader("Camera Status")
            status_col1, status_col2 = st.columns(2)
            
            with status_col1:
                # Display connection time
                if hasattr(camera_manager, 'connection_time') and camera_manager.connection_time > 0:
                    uptime_seconds = time.time() - camera_manager.connection_time
                    days, remainder = divmod(uptime_seconds, 86400)
                    hours, remainder = divmod(remainder, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    if days > 0:
                        uptime_str = f"{int(days)}d {int(hours)}h {int(minutes)}m"
                    elif hours > 0:
                        uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                    else:
                        uptime_str = f"{int(minutes)}m {int(seconds)}s"
                    
                    st.metric("Connection Time", uptime_str)
                else:
                    st.metric("Connection Time", "Not connected")
                
                # Display visibility status
                visibility_status = camera_data.get('visibility_status', 'Unknown')
                visibility_status_color = {
                    'Good': 'green',
                    'Moderate': 'orange',
                    'Poor': 'red',
                    'Unknown': 'gray'
                }.get(visibility_status, 'gray')
                
                st.markdown(f"<h3 style='color: {visibility_status_color};'>Status: {visibility_status}</h3>", unsafe_allow_html=True)
            
            with status_col2:
                # Display frames processed
                if hasattr(camera_manager, 'frames_processed'):
                    st.metric("Frames Processed", f"{camera_manager.frames_processed:,}")
                else:
                    st.metric("Frames Processed", "N/A")
                
                # Display processing time
                if hasattr(camera_manager, 'avg_processing_time') and camera_manager.avg_processing_time > 0:
                    st.metric("Avg Processing Time", f"{camera_manager.avg_processing_time:.1f} ms")
                else:
                    st.metric("Avg Processing Time", "N/A")
            
            # Historical data section
            st.subheader("Historical Data")
            
            # Timeline selection
            time_options = {
                "Last Hour": 60*60,
                "Last 24 Hours": 24*60*60,
                "Last 7 Days": 7*24*60*60,
                "All Data": None
            }
            
            selected_time = st.selectbox("Select Time Range", list(time_options.keys()))
            time_filter = time_options[selected_time]
            
            # Get historical data with time filter
            visibility_history = camera_data.get('visibility_history', [])
            if time_filter and visibility_history:
                current_time = time.time()
                visibility_history = [entry for entry in visibility_history if current_time - entry.get('timestamp', 0) <= time_filter]
            
            # Create historical charts if we have data
            if visibility_history:
                # Convert data for charting
                chart_data = {
                    "timestamp": [],
                    "visibility_score": [],
                    "brightness": [],
                    "contrast": [],
                    "edge_score": [],
                    "visibility_distance": []
                }
                
                for entry in visibility_history:
                    # Convert timestamp to datetime for better x-axis display
                    if 'timestamp' in entry:
                        chart_data["timestamp"].append(datetime.fromtimestamp(entry['timestamp']))
                    else:
                        continue  # Skip entries without timestamp
                        
                    chart_data["visibility_score"].append(entry.get('visibility_score', 0))
                    chart_data["brightness"].append(entry.get('brightness', 0))
                    chart_data["contrast"].append(entry.get('contrast', 0))
                    chart_data["edge_score"].append(entry.get('edge_score', 0))
                    chart_data["visibility_distance"].append(entry.get('visibility_distance', 0))
                
                # Create pandas DataFrame for charting
                df = pd.DataFrame(chart_data)
                
                # Chart for visibility score over time
                st.subheader("Visibility Score Over Time")
                visibility_chart = px.line(df, x="timestamp", y="visibility_score", 
                                           title="Visibility Score Trend",
                                           labels={"timestamp": "Time", "visibility_score": "Visibility Score (%)"},
                                           template="plotly_white")
                visibility_chart.update_layout(height=300)
                st.plotly_chart(visibility_chart, use_container_width=True)
                
                # Chart for key metrics over time
                st.subheader("Key Metrics Over Time")
                metric_columns = st.columns(2)
                
                with metric_columns[0]:
                    # Chart for brightness and contrast
                    bc_chart = px.line(df, x="timestamp", y=["brightness", "contrast"], 
                                      title="Brightness & Contrast Trends",
                                      labels={"timestamp": "Time", "value": "Value", "variable": "Metric"},
                                      template="plotly_white")
                    bc_chart.update_layout(height=300)
                    st.plotly_chart(bc_chart, use_container_width=True)
                
                with metric_columns[1]:
                    # Chart for edge score and visibility distance
                    edge_chart = px.line(df, x="timestamp", y=["edge_score", "visibility_distance"], 
                                        title="Edge Score & Visibility Distance Trends",
                                        labels={"timestamp": "Time", "value": "Value", "variable": "Metric"},
                                        template="plotly_white")
                    edge_chart.update_layout(height=300)
                    st.plotly_chart(edge_chart, use_container_width=True)
            else:
                st.info("No historical data available yet. Historical metrics will appear here once data is collected.")
            
            return
        except Exception as e:
            st.error(f"Error in analytics tab: {str(e)}")
            logger.error(f"Error in analytics tab: {str(e)}")
    
    @staticmethod
    def create_weather_tab(weather_data):
        """Create weather dashboard tab"""
        st.markdown("<h2 class='sub-header'>🌦️ Weather Insights</h2>", unsafe_allow_html=True)
            
        if weather_data:
            try:
                # Create two columns for weather data
                col1, col2 = st.columns(2)
                
                with col1:
                    # Left column - Current weather metrics
                    st.subheader("Current Weather Conditions")
                    
                    # Display weather metrics with appropriate icons
                    st.metric("Temperature", f"{weather_data['temperature']}°C")
                    st.metric("Humidity", f"{weather_data['humidity']}%")
                    st.metric("Wind Speed", f"{weather_data['wind_speed']} km/h")
                    st.metric("Visibility", f"{weather_data['visibility']} km")
                    
                    # Display last updated time
                    if 'last_updated' in weather_data:
                        st.caption(f"Last updated: {weather_data['last_updated']}")
                
                with col2:
                    # Right column - Weather condition and forecast
                    st.subheader("Weather Condition")
                    
                    # Weather icon and condition
                    if 'icon_url' in weather_data:
                        st.image(weather_data['icon_url'], width=100)
                    
                    st.info(f"Condition: {weather_data['condition']}")
                    
                    # Visibility assessment
                    visibility_km = float(weather_data['visibility'])
                    if visibility_km < 1.0:
                        st.error("⚠️ Very poor visibility conditions")
                    elif visibility_km < 2.0:
                        st.warning("⚠️ Poor visibility conditions")
                    elif visibility_km < 5.0:
                        st.info("ℹ️ Moderate visibility conditions")
                    else:
                        st.success("✓ Good visibility conditions")
                
                # Create expander for weather data details
                with st.expander("Weather Data Details", expanded=False):
                    # Convert weather data to a DataFrame for display
                    import pandas as pd
                    
                    # Create a safer version of the data for arrow conversion
                    display_data = {}
                    for k, v in weather_data.items():
                        if k != 'icon_url':
                            # Convert all values to strings to avoid Arrow conversion issues
                            display_data[k] = [str(v)]
                    
                    df = pd.DataFrame.from_dict(display_data)
                    st.dataframe(df.T, use_container_width=True)
                
                # Manual refresh button
                if st.button("Refresh Weather Data", key="refresh_weather_btn"):
                    try:
                        if 'weather_manager' in st.session_state and 'last_weather_fetch' in st.session_state:
                            city = weather_data.get('location', 'Manila').split(',')[0].strip()
                            if city in st.session_state.last_weather_fetch:
                                # Set last fetch time to force a refresh
                                del st.session_state.last_weather_fetch[city]
                                
                                st.success(f"Weather data for {city} will be refreshed on next page reload")
                                # Set flag in session state instead of direct rerun
                                st.session_state.weather_refresh_requested = True
                    except Exception as e:
                        st.error(f"Error refreshing weather data: {str(e)}")
                
                # Handle refresh request
                if 'weather_refresh_requested' in st.session_state and st.session_state.weather_refresh_requested:
                    st.session_state.weather_refresh_requested = False
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Error retrieving weather settings: {str(e)}")
                logger.error(f"Error in weather tab: {str(e)}")
        else:
            st.warning("Weather data not available")
    
    @staticmethod
    def create_recordings_tab(camera_manager):
        """Creates the recordings and highlights tab"""
        st.subheader("Recordings & Highlights")
        
        if camera_manager is None:
            st.info("Select a camera from the sidebar to view recordings.")
            return
        
        # Create tabs for recordings and highlights
        rec_tab1, rec_tab2 = st.tabs(["Recordings", "Highlights"])
        
        with rec_tab1:
            st.subheader("Camera Recordings")
            
            # Get recordings directory for this camera
            recordings_dir = camera_manager.recordings_dir
            
            if not recordings_dir.exists():
                st.info(f"No recordings directory found for camera {camera_manager.camera_id}")
                return
            
            # Get list of recordings
            recordings = list(recordings_dir.glob("*.mp4"))
            
            if not recordings:
                st.info("No recordings found. Start recording from the sidebar to create recordings.")
            else:
                # Sort by modification time (newest first)
                recordings.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                
                # Display recordings in a table
                st.markdown("### Available Recordings")
                
                # Create a table for recordings
                data = []
                for recording in recordings:
                    # Get file stats
                    stats = recording.stat()
                    
                    # Format size
                    size_mb = stats.st_size / (1024 * 1024)
                    
                    # Format date
                    date = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Add to data
                    data.append({
                        "Filename": recording.name,
                        "Date": date,
                        "Size (MB)": f"{size_mb:.2f}",
                        "Path": str(recording)
                    })
                
                # Convert to dataframe for display
                df = pd.DataFrame(data)
                
                # Display the table
                st.dataframe(df[["Filename", "Date", "Size (MB)"]], use_container_width=True)
                
                # Add download links
                st.markdown("### Download Recordings")
                
                # Show the latest 5 recordings with download links
                for recording in recordings[:5]:
                    with open(recording, "rb") as file:
                        st.download_button(
                            label=f"Download {recording.name}",
                            data=file,
                            file_name=recording.name,
                            mime="video/mp4"
                        )
        
        with rec_tab2:
            st.subheader("Visibility Highlights")
            
            # Get highlights directory for this camera
            highlights_dir = camera_manager.highlights_dir
            
            if not highlights_dir.exists():
                st.info(f"No highlights directory found for camera {camera_manager.camera_id}")
                return
            
            # Get list of highlights
            highlights = list(highlights_dir.glob("highlight_*.mp4"))
            highlight_markers = list(highlights_dir.glob("highlight_*.txt"))
            
            if not highlights and not highlight_markers:
                st.info("No visibility highlights found. Highlights are automatically created when poor visibility is detected during recording.")
            else:
                # Sort by modification time (newest first)
                highlight_markers.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                
                # Display highlight markers in an expandable section
                st.markdown("### Visibility Events")
                
                for marker in highlight_markers:
                    # Extract timestamp from filename
                    try:
                        filename = marker.name
                        date_str = filename.split("_")[1] + "_" + filename.split("_")[2].split(".")[0]
                        date = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                        date_formatted = date.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        date_formatted = "Unknown date"
                    
                    # Read marker file to get info
                    try:
                        with open(marker, "r") as f:
                            marker_info = f.read()
                    except Exception:
                        marker_info = "Could not read highlight info"
                    
                    # Create expandable section
                    with st.expander(f"Highlight: {date_formatted}"):
                        st.text(marker_info)
                        
                        # Check if corresponding video exists
                        video_file = marker.with_suffix('.mp4')
                        if video_file.exists():
                            st.video(str(video_file))
        
        return
    
    @staticmethod
    def create_highlights_tab(camera_manager):
        """Create highlights tab showing visibility events"""
        st.header("Visibility Highlights")
        
        if camera_manager is None:
            st.info("Select a camera to view highlights.")
            return
            
        try:
            # Get the highlights directory for this camera
            highlights_dir = camera_manager.highlights_dir
            camera_id = camera_manager.camera_id
            
            # Check if directory exists
            if not highlights_dir.exists():
                highlights_dir.mkdir(parents=True, exist_ok=True)
                st.info("No highlights recorded yet. Highlights will be automatically created when poor visibility is detected while recording.")
                return
                
            # Find all highlight files
            highlight_files = list(highlights_dir.glob("highlight_*.mp4"))
            
            if not highlight_files:
                st.info("No highlights recorded yet. Highlights will be automatically created when poor visibility is detected while recording.")
                return
                
            # Sort by modification time (newest first)
            highlight_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Group by date
            highlights_by_date = {}
            for file in highlight_files:
                try:
                    # Extract date from filename
                    date_str = file.stem.split('_')[1]  # Format: highlight_YYYYMMDD_HHMMSS
                    date_obj = datetime.strptime(date_str, "%Y%m%d")
                    date_key = date_obj.strftime("%Y-%m-%d")
                    
                    if date_key not in highlights_by_date:
                        highlights_by_date[date_key] = []
                        
                    highlights_by_date[date_key].append(file)
                except Exception as e:
                    logger.error(f"Error processing highlight file {file}: {str(e)}")
            
            # Display highlights by date
            for date, files in highlights_by_date.items():
                with st.expander(f"Highlights for {date} ({len(files)} events)"):
                    # Display each highlight for this date
                    for i, file in enumerate(files):
                        try:
                            # Extract time from filename
                            time_str = file.stem.split('_')[2]  # Format: highlight_YYYYMMDD_HHMMSS
                            time_obj = datetime.strptime(time_str, "%H%M%S")
                            time_key = time_obj.strftime("%H:%M:%S")
                            
                            st.subheader(f"Event at {time_key}")
                            
                            # Check if there's a metadata text file
                            metadata_file = file.with_suffix('.txt')
                            if metadata_file.exists():
                                try:
                                    with open(metadata_file, 'r') as f:
                                        metadata = f.read()
                                    st.text(metadata)
                                except Exception:
                                    st.text("Error reading metadata file")
                            
                            # Display the highlight video
                            st.video(str(file))
                            
                            # Add download button
                            with open(file, "rb") as f:
                                st.download_button(
                                    label=f"Download highlight",
                                    data=f,
                                    file_name=file.name,
                                    mime="video/mp4"
                                )
                            
                            # Add separator between highlights
                            if i < len(files) - 1:
                                st.markdown("---")
                        except Exception as e:
                            st.error(f"Error displaying highlight {file.name}: {str(e)}")
        except Exception as e:
            st.error(f"Error loading highlights: {str(e)}")
            logger.error(f"Error in highlights tab: {str(e)}")
            
        return
    
    @staticmethod
    def create_historical_tab(camera_manager):
        """Create historical data visualization tab"""
        st.header("Historical Visibility Data")
        
        if camera_manager is None:
            st.info("Select a camera to view historical data")
            return
            
        camera_id = camera_manager.camera_id
        
        try:
            # Time range selector
            st.subheader("Select Time Range")
            
            time_options = {
                "Last Hour": 60*60,
                "Last 24 Hours": 24*60*60,
                "Last 7 Days": 7*24*60*60,
                "Last 30 Days": 30*24*60*60,
                "All Time": None
            }
            
            selected_range = st.selectbox(
                "Time Period",
                options=list(time_options.keys()),
                index=1  # Default to 24 hours
            )
            
            time_filter = time_options[selected_range]
            
            # Try to get historical data from the camera manager
            history = []
            if hasattr(camera_manager, 'visibility_history'):
                history = camera_manager.visibility_history
            
            if not history:
                st.info("No historical data available for this camera yet. Data will appear here once collected.")
                return
                
            # Filter by time range if specified
            if time_filter is not None:
                current_time = time.time()
                history = [entry for entry in history if current_time - entry.get('timestamp', 0) <= time_filter]
            
            if not history:
                st.info(f"No data available for the selected time range ({selected_range})")
                return
                
            # Create dataframe for charting
            df_data = {
                "timestamp": [],
                "visibility_score": [],
                "brightness": [],
                "contrast": [],
                "edge_score": [],
                "visibility_status": []
            }
            
            for entry in history:
                # Add each data point to our dataframe
                df_data["timestamp"].append(datetime.fromtimestamp(entry.get('timestamp', 0)))
                df_data["visibility_score"].append(entry.get('visibility_score', 0))
                df_data["brightness"].append(entry.get('brightness', 0))
                df_data["contrast"].append(entry.get('contrast', 0))
                df_data["edge_score"].append(entry.get('edge_score', 0))
                df_data["visibility_status"].append(entry.get('visibility_status', 'Unknown'))
            
            # Create dataframe
            df = pd.DataFrame(df_data)
            
            # Display overall statistics
            st.subheader("Statistics")
            col1, col2, col3 = st.columns(3)
            
            # Calculate stats
            avg_visibility = df["visibility_score"].mean()
            min_visibility = df["visibility_score"].min()
            max_visibility = df["visibility_score"].max()
            
            with col1:
                st.metric("Average Visibility", f"{avg_visibility:.1f}%")
            with col2:
                st.metric("Minimum Visibility", f"{min_visibility:.1f}%")
            with col3:
                st.metric("Maximum Visibility", f"{max_visibility:.1f}%")
            
            # Create visibility score chart
            st.subheader("Visibility Score Trend")
            
            visibility_chart = px.line(
                df, 
                x="timestamp", 
                y="visibility_score",
                title="Visibility Score Over Time",
                labels={"visibility_score": "Visibility Score (%)", "timestamp": "Time"},
                template="plotly_white"
            )
            
            # Add threshold lines
            if hasattr(camera_manager, 'visibility_threshold'):
                visibility_chart.add_hline(
                    y=camera_manager.visibility_threshold,
                    line_dash="dash", 
                    line_color="red",
                    annotation_text="Poor Visibility Threshold",
                    annotation_position="bottom right"
                )
                
            if hasattr(camera_manager, 'recovery_threshold'):
                visibility_chart.add_hline(
                    y=camera_manager.recovery_threshold,
                    line_dash="dash", 
                    line_color="green",
                    annotation_text="Recovery Threshold",
                    annotation_position="bottom right"
                )
            
            st.plotly_chart(visibility_chart, use_container_width=True)
            
            # Create component charts
            st.subheader("Visibility Components")
            
            metric_cols = st.columns(2)
            
            with metric_cols[0]:
                # Brightness chart
                brightness_chart = px.line(
                    df, 
                    x="timestamp", 
                    y="brightness",
                    title="Brightness Over Time",
                    labels={"brightness": "Brightness (0-255)", "timestamp": "Time"},
                    template="plotly_white"
                )
                st.plotly_chart(brightness_chart, use_container_width=True)
                
            with metric_cols[1]:
                # Contrast chart
                contrast_chart = px.line(
                    df, 
                    x="timestamp", 
                    y="contrast",
                    title="Contrast Over Time",
                    labels={"contrast": "Contrast", "timestamp": "Time"},
                    template="plotly_white"
                )
                st.plotly_chart(contrast_chart, use_container_width=True)
            
            # Add a download button for CSV data export
            st.subheader("Export Data")
            
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download Historical Data as CSV",
                data=csv,
                file_name=f"visibility_history_{camera_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"Error displaying historical data: {str(e)}")
            logger.error(f"Error in historical tab: {str(e)}")
            
        return
    
    @staticmethod
    def _create_roi_config_tab(camera_config, camera_manager):
        """Create the ROI configuration tab"""
        
        st.subheader("Region of Interest (ROI) Configuration")
        
        # Initialize session state variables if they don't exist
        if 'roi_editing' not in st.session_state:
            st.session_state.roi_editing = False
        if 'roi_regions' not in st.session_state:
            st.session_state.roi_regions = camera_config.get('roi_regions', [])
        if 'roi_name_temp' not in st.session_state:
            st.session_state.roi_name_temp = ""
        if 'roi_x_temp' not in st.session_state:
            st.session_state.roi_x_temp = 0.1
        if 'roi_y_temp' not in st.session_state:
            st.session_state.roi_y_temp = 0.1
        if 'roi_width_temp' not in st.session_state:
            st.session_state.roi_width_temp = 0.2
        if 'roi_height_temp' not in st.session_state:
            st.session_state.roi_height_temp = 0.2
        if 'roi_distance_temp' not in st.session_state:
            st.session_state.roi_distance_temp = 100
        if 'selected_roi_index' not in st.session_state:
            st.session_state.selected_roi_index = None
        if 'save_roi_button_clicked' not in st.session_state:
            st.session_state.save_roi_button_clicked = False
        if 'roi_action_requested' not in st.session_state:
            st.session_state.roi_action_requested = None
        
        # Handle pending actions first
        if 'roi_action_requested' in st.session_state and st.session_state.roi_action_requested:
            action = st.session_state.roi_action_requested
            st.session_state.roi_action_requested = None  # Clear the flag
            st.rerun()
        
        # Toggle ROI editing mode
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Toggle ROI Editing Mode", use_container_width=True):
                st.session_state.roi_editing = not st.session_state.roi_editing
                st.session_state.selected_roi_index = None  # Reset selection when toggling mode
                st.session_state.roi_action_requested = "toggle_edit_mode"
        
        if st.session_state.roi_editing:
            st.success("ROI Editing Mode is ON. Draw or edit ROIs and save your configuration.")
            
            # Get the last frame from the camera for preview
            preview_frame = None
            preview_success = False
            if camera_manager and camera_manager.is_connected():
                try:
                    preview_frame = camera_manager.read_frame()
                    if preview_frame is not None:
                        preview_success = True
                except Exception as e:
                    st.error(f"Failed to get camera frame: {str(e)}")
            
            # Create tabs for ROI management
            roi_tabs = st.tabs(["Add ROI", "List ROIs", "Edit ROI"])
            
            # Define ROI update callback
            def update_roi_temp(field_name):
                """Update the ROI temp value based on form input"""
                if field_name == 'name':
                    st.session_state.roi_name_temp = st.session_state.add_roi_name
            
            # Add ROI tab
            with roi_tabs[0]:
                st.subheader("Add New ROI")
                
                # Add ROI form fields
                st.text_input("ROI Name", value="", key="add_roi_name", 
                              placeholder="Enter a name for the ROI", 
                              on_change=update_roi_temp, args=('name',))
                
                st.session_state.roi_x_temp = st.number_input("X Position (0-1)", 
                                                             min_value=0.0, max_value=1.0, 
                                                             value=st.session_state.roi_x_temp, 
                                                             step=0.05, format="%.2f", key="add_roi_x")
                
                st.session_state.roi_y_temp = st.number_input("Y Position (0-1)", 
                                                             min_value=0.0, max_value=1.0, 
                                                             value=st.session_state.roi_y_temp, 
                                                             step=0.05, format="%.2f", key="add_roi_y")
                
                st.session_state.roi_width_temp = st.number_input("Width (0-1)", 
                                                                 min_value=0.05, max_value=1.0, 
                                                                 value=st.session_state.roi_width_temp, 
                                                                 step=0.05, format="%.2f", key="add_roi_width")
                
                st.session_state.roi_height_temp = st.number_input("Height (0-1)", 
                                                                  min_value=0.05, max_value=1.0, 
                                                                  value=st.session_state.roi_height_temp, 
                                                                  step=0.05, format="%.2f", key="add_roi_height")
                
                st.session_state.roi_distance_temp = st.number_input("Distance (meters)", 
                                                                    min_value=1, max_value=10000, 
                                                                    value=st.session_state.roi_distance_temp, 
                                                                    step=10, key="add_roi_distance")
                
                # Add ROI button
                if st.button("Add ROI", use_container_width=True):
                    if st.session_state.roi_name_temp:
                        new_roi = {
                            "name": st.session_state.roi_name_temp,
                            "x": st.session_state.roi_x_temp,
                            "y": st.session_state.roi_y_temp,
                            "width": st.session_state.roi_width_temp,
                            "height": st.session_state.roi_height_temp,
                            "distance": st.session_state.roi_distance_temp
                        }
                        st.session_state.roi_regions.append(new_roi)
                        
                        # Update camera manager with the changes immediately
                        if camera_manager and camera_manager.is_connected():
                            camera_manager.set_roi_regions(st.session_state.roi_regions, normalized=True)
                            
                        st.success(f"Added ROI: {st.session_state.roi_name_temp}")
                        
                        # Reset temp values for next ROI
                        st.session_state.roi_name_temp = ""
                        st.session_state.roi_x_temp = 0.1
                        st.session_state.roi_y_temp = 0.1
                        st.session_state.roi_width_temp = 0.2
                        st.session_state.roi_height_temp = 0.2
                        # Don't reset distance to keep consecutive ROIs at the same distance if needed
                        # st.session_state.roi_distance_temp = 100
                        st.session_state.roi_action_requested = "roi_added"
            
            # List ROIs tab
            with roi_tabs[1]:
                st.subheader("Existing ROIs")
                if st.session_state.roi_regions:
                    # Format ROI information for display
                    def format_roi_info(i):
                        roi = st.session_state.roi_regions[i]
                        return f"{roi['name']} - Pos: ({roi['x']:.2f}, {roi['y']:.2f}) Size: {roi['width']:.2f}x{roi['height']:.2f} Dist: {roi['distance']}m"
                    
                    # ROI selection widget
                    selected_index = st.selectbox(
                        "Select ROI", 
                        options=list(range(len(st.session_state.roi_regions))),
                        format_func=format_roi_info,
                        key="roi_selector",
                        index=st.session_state.selected_roi_index if st.session_state.selected_roi_index is not None and st.session_state.selected_roi_index < len(st.session_state.roi_regions) else 0
                    )
                    
                    # Store selected index in session state
                    st.session_state.selected_roi_index = selected_index
                    
                    # Delete selected ROI button
                    if st.button("Delete Selected ROI", use_container_width=True):
                        if st.session_state.selected_roi_index is not None:
                            try:
                                deleted_roi = st.session_state.roi_regions.pop(st.session_state.selected_roi_index)
                                
                                # Update camera manager with the changes immediately
                                if camera_manager and camera_manager.is_connected():
                                    camera_manager.set_roi_regions(st.session_state.roi_regions, normalized=True)
                                    
                                st.success(f"Deleted ROI: {deleted_roi['name']}")
                                st.session_state.selected_roi_index = None
                                st.session_state.roi_action_requested = "roi_deleted"
                            except Exception as e:
                                st.error(f"Error deleting ROI: {str(e)}")
                else:
                    st.info("No ROIs defined yet. Add ROIs in the 'Add ROI' tab.")
                    
            # Edit ROI tab
            with roi_tabs[2]:
                st.subheader("Edit Selected ROI")
                if st.session_state.selected_roi_index is not None and 0 <= st.session_state.selected_roi_index < len(st.session_state.roi_regions):
                    roi = st.session_state.roi_regions[st.session_state.selected_roi_index]
                    
                    # Edit ROI fields
                    edited_name = st.text_input("Edit ROI Name", value=roi["name"], key="edit_roi_name")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        edited_x = st.number_input("Edit X Position", min_value=0.0, max_value=1.0, 
                                                value=float(roi["x"]), step=0.05, format="%.2f", key="edit_roi_x")
                        edited_width = st.number_input("Edit Width", min_value=0.0, max_value=1.0, 
                                                    value=float(roi["width"]), step=0.05, format="%.2f", key="edit_roi_width")
                    with col2:
                        edited_y = st.number_input("Edit Y Position", min_value=0.0, max_value=1.0, 
                                                value=float(roi["y"]), step=0.05, format="%.2f", key="edit_roi_y")
                        edited_height = st.number_input("Edit Height", min_value=0.0, max_value=1.0, 
                                                    value=float(roi["height"]), step=0.05, format="%.2f", key="edit_roi_height")
                    
                    edited_distance = st.number_input("Edit Distance (meters)", min_value=1, max_value=10000, 
                                                  value=int(roi.get("distance", 100)), step=10, key="edit_roi_distance")
                    
                    # Update ROI button
                    if st.button("Update ROI", use_container_width=True):
                        try:
                            # Update the existing ROI with edited values
                            st.session_state.roi_regions[st.session_state.selected_roi_index] = {
                                "name": edited_name,
                                "x": edited_x,
                                "y": edited_y,
                                "width": edited_width,
                                "height": edited_height,
                                "distance": edited_distance
                            }
                            st.success(f"Updated ROI: {edited_name}")
                            
                            # Update camera manager with the changes immediately to show the updated ROI
                            if camera_manager and camera_manager.is_connected():
                                camera_manager.set_roi_regions(st.session_state.roi_regions, normalized=True)
                            
                            st.session_state.roi_action_requested = "roi_updated"
                        except Exception as e:
                            st.error(f"Error updating ROI: {str(e)}")
                else:
                    st.info("No ROI selected. Please select an ROI from the 'List ROIs' tab.")
            
            # Display preview frame with ROIs
            if preview_success and preview_frame is not None:
                st.subheader("Camera Preview with ROIs")
                
                # Draw ROIs on preview frame
                h, w = preview_frame.shape[:2]
                preview_with_rois = preview_frame.copy()
                
                # Draw existing ROIs
                for i, roi in enumerate(st.session_state.roi_regions):
                    # Calculate pixel coordinates
                    x = int(roi["x"] * w)
                    y = int(roi["y"] * h)
                    width = int(roi["width"] * w)
                    height = int(roi["height"] * h)
                    
                    # Draw with different color for selected ROI
                    color = (0, 255, 0)  # Green for regular ROIs
                    thickness = 2
                    
                    if st.session_state.selected_roi_index == i:
                        color = (0, 0, 255)  # Red for selected ROI
                        thickness = 3
                    
                    # Draw rectangle
                    cv2.rectangle(preview_with_rois, (x, y), (x + width, y + height), color, thickness)
                    
                    # Add ROI name and distance
                    cv2.putText(preview_with_rois, f"{roi['name']} ({roi.get('distance', 0)}m)", 
                              (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
                # If adding a new ROI, show that as well
                if st.session_state.roi_name_temp:
                    x = int(st.session_state.roi_x_temp * w)
                    y = int(st.session_state.roi_y_temp * h)
                    width = int(st.session_state.roi_width_temp * w)
                    height = int(st.session_state.roi_height_temp * h)
                    
                    # Draw with different color for new ROI
                    cv2.rectangle(preview_with_rois, (x, y), (x + width, y + height), (255, 0, 0), 3)  # Blue with thicker line
                    cv2.putText(preview_with_rois, f"NEW: {st.session_state.roi_name_temp} ({st.session_state.roi_distance_temp}m)", 
                              (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                
                # Display the preview
                st.image(preview_with_rois, channels="BGR", use_column_width=True)
            else:
                st.subheader("ROI Preview (No camera frame available)")
                # Create a placeholder grid background
                grid_img = np.ones((480, 640, 3), dtype=np.uint8) * 40  # Dark gray
                
                # Draw grid lines
                for x in range(0, 641, 64):  # Every 10% horizontally
                    cv2.line(grid_img, (x, 0), (x, 480), (100, 100, 100), 1)
                for y in range(0, 481, 48):  # Every 10% vertically
                    cv2.line(grid_img, (0, y), (640, y), (100, 100, 100), 1)
                
                # Add percentage indicators
                for i in range(0, 11):
                    # Horizontal percentages
                    x = int(i * 64)
                    cv2.putText(grid_img, f"{i*10}%", (x, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                    # Vertical percentages
                    y = int(i * 48)
                    if y < 481:
                        cv2.putText(grid_img, f"{i*10}%", (5, y+15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                
                # Draw ROIs on grid image
                for i, roi in enumerate(st.session_state.roi_regions):
                    # Calculate pixel coordinates (scaled to our grid)
                    x = int(roi["x"] * 640)
                    y = int(roi["y"] * 480)
                    width = int(roi["width"] * 640)
                    height = int(roi["height"] * 480)
                    
                    # Draw with different color for selected ROI
                    color = (0, 255, 0)  # Green for regular ROIs
                    thickness = 2
                    
                    if st.session_state.selected_roi_index == i:
                        color = (0, 0, 255)  # Red for selected ROI
                        thickness = 3
                    
                    # Draw rectangle
                    cv2.rectangle(grid_img, (x, y), (x + width, y + height), color, thickness)
                    
                    # Add ROI name and distance
                    cv2.putText(grid_img, f"{roi['name']} ({roi.get('distance', 0)}m)", 
                              (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
                # If adding a new ROI, show that as well
                if st.session_state.roi_name_temp:
                    x = int(st.session_state.roi_x_temp * 640)
                    y = int(st.session_state.roi_y_temp * 480)
                    width = int(st.session_state.roi_width_temp * 640)
                    height = int(st.session_state.roi_height_temp * 480)
                    
                    # Draw with different color for new ROI
                    cv2.rectangle(grid_img, (x, y), (x + width, y + height), (255, 0, 0), 3)  # Blue with thicker line
                    cv2.putText(grid_img, f"NEW: {st.session_state.roi_name_temp} ({st.session_state.roi_distance_temp}m)", 
                              (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                
                # Display the grid
                st.image(grid_img, channels="BGR", use_column_width=True)
            
            # Save button at the bottom of all sections
            st.markdown("---")
            if st.button("Save ROI Configuration", use_container_width=True):
                st.session_state.save_roi_button_clicked = True
                if camera_manager:
                    camera_manager.set_roi_regions(st.session_state.roi_regions, normalized=True)
                st.session_state.roi_editing = False
                st.success("ROI configuration will be saved.")
                st.session_state.roi_action_requested = "save_config"
        else:
            # Display current ROI configuration
            if st.session_state.roi_regions:
                st.info(f"There are {len(st.session_state.roi_regions)} ROIs configured. Click 'Toggle ROI Editing Mode' to edit them.")
                
                # Display ROI list in table format
                roi_data = []
                for roi in st.session_state.roi_regions:
                    roi_data.append({
                        "Name": roi["name"],
                        "X": f"{roi['x']:.2f}",
                        "Y": f"{roi['y']:.2f}",
                        "Width": f"{roi['width']:.2f}",
                        "Height": f"{roi['height']:.2f}",
                        "Distance": f"{roi.get('distance', 0)}m"
                    })
                
                if roi_data:
                    st.table(roi_data)
            else:
                st.warning("No ROIs configured. Click 'Toggle ROI Editing Mode' to add ROIs.")
        
        # Visibility threshold settings
        st.markdown("---")
        st.subheader("Visibility Thresholds")
        
        col1, col2 = st.columns(2)
        with col1:
            visibility_threshold = st.slider(
                "Visibility Threshold (%)", 
                min_value=0, 
                max_value=100, 
                value=camera_config.get('visibility_threshold', 40),
                help="Threshold below which visibility is considered poor"
            )
        with col2:
            recovery_threshold = st.slider(
                "Recovery Threshold (%)", 
                min_value=0, 
                max_value=100, 
                value=camera_config.get('recovery_threshold', 60),
                help="Threshold above which visibility is considered good"
            )
            
        # Color delta threshold
        color_delta_threshold = st.slider(
            "Color Change Detection Threshold (ΔE)", 
            min_value=0.0, 
            max_value=50.0, 
            value=camera_config.get('color_delta_threshold', 10.0),
            step=0.5,
            help="Threshold for detecting significant color changes in LAB space"
        )
        
        # Save thresholds button
        if st.button("Save Threshold Settings", use_container_width=True):
            if camera_manager:
                camera_manager.visibility_threshold = visibility_threshold
                camera_manager.recovery_threshold = recovery_threshold
                camera_manager.color_delta_threshold = color_delta_threshold
            
            st.success("Threshold settings saved!")
            # Set a flag in session state to indicate threshold settings changed
            st.session_state.thresholds_saved = True
            return {
                'visibility_threshold': visibility_threshold,
                'recovery_threshold': recovery_threshold,
                'color_delta_threshold': color_delta_threshold
            }
            
        return None

    @staticmethod
    def _create_stream_settings_section():
        """Create the stream settings section in the sidebar"""
        st.sidebar.subheader("Stream Settings")
        
        # Get current camera config
        camera_id = st.session_state.selected_camera
        camera_config = st.session_state.cameras[camera_id]
        stream_settings = camera_config.get('stream_settings', {})
        
        # Stream settings
        with st.sidebar.expander("Stream Configuration", expanded=False):
            width = st.number_input("Width", min_value=640, max_value=1920, value=stream_settings.get('width', 1280))
            height = st.number_input("Height", min_value=480, max_value=1080, value=stream_settings.get('height', 720))
            fps = st.number_input("FPS", min_value=1, max_value=30, value=stream_settings.get('fps', 15))
            buffer_size = st.number_input("Buffer Size", min_value=1, max_value=60, value=stream_settings.get('buffer_size', 30))
            rtsp_transport = st.selectbox("RTSP Transport", ["tcp", "udp"], 
                                         index=0 if stream_settings.get('rtsp_transport', "tcp") == "tcp" else 1)
            
            # Apply stream settings
            if st.button("Apply Stream Settings", key="apply_stream_settings"):
                # Update camera config
                if 'stream_settings' not in st.session_state.cameras[camera_id]:
                    st.session_state.cameras[camera_id]['stream_settings'] = {}
                
                st.session_state.cameras[camera_id]['stream_settings']['width'] = width
                st.session_state.cameras[camera_id]['stream_settings']['height'] = height
                st.session_state.cameras[camera_id]['stream_settings']['fps'] = fps
                st.session_state.cameras[camera_id]['stream_settings']['buffer_size'] = buffer_size
                st.session_state.cameras[camera_id]['stream_settings']['rtsp_transport'] = rtsp_transport
                
                st.success("Stream settings updated. Reconnect camera to apply changes.")
    
    @staticmethod
    def _create_display_settings_section():
        """Create the display settings section in the sidebar"""
        st.sidebar.subheader("Display Settings")
        
        # Display settings
        with st.sidebar.expander("Display Configuration", expanded=False):
            if 'refresh_rate' not in st.session_state:
                st.session_state.refresh_rate = 0.1
            st.session_state.refresh_rate = st.slider("Refresh Rate (seconds)", 0.1, 5.0, st.session_state.refresh_rate, 0.1)
            
            if 'auto_refresh' not in st.session_state:
                st.session_state.auto_refresh = True
            st.session_state.auto_refresh = st.checkbox("Auto Refresh", st.session_state.auto_refresh)
            
            if 'show_fps' not in st.session_state:
                st.session_state.show_fps = True
            st.session_state.show_fps = st.checkbox("Show FPS", st.session_state.show_fps)
            
            if 'show_roi' not in st.session_state:
                st.session_state.show_roi = True
            st.session_state.show_roi = st.checkbox("Show ROI Overlay", st.session_state.show_roi)
            
            if 'show_overlay' not in st.session_state:
                st.session_state.show_overlay = True
            st.session_state.show_overlay = st.checkbox("Show Visibility Overlay", st.session_state.show_overlay)
    
    @staticmethod
    def _create_weather_settings_section():
        """Create weather settings section in sidebar"""
        st.sidebar.subheader("Weather Settings")
        
        if 'weather_manager' in st.session_state:
            weather_manager = st.session_state.weather_manager
            
            # Get current camera location and weather refresh settings
            try:
                city = "Manila"  # Default city
                if 'cameras' in st.session_state and 'selected_camera' in st.session_state:
                    camera_id = st.session_state.selected_camera
                    if camera_id in st.session_state.cameras:
                        camera_config = st.session_state.cameras[camera_id]
                        city = camera_config.get('weather_city', camera_config.get('location', 'Manila'))
                
                # Get the current refresh interval
                refresh_interval = 30  # Default 30 minutes
                if hasattr(weather_manager, 'get_refresh_interval'):
                    refresh_interval = weather_manager.get_refresh_interval(city)
                
                # Create a session state variable for the refresh interval
                if 'weather_refresh_interval' not in st.session_state:
                    st.session_state.weather_refresh_interval = refresh_interval
                
                # Weather refresh settings
                st.sidebar.write(f"Configure weather refresh interval for {city}")
                new_refresh_interval = st.sidebar.slider(
                    "Refresh interval (minutes)", 
                    min_value=5, 
                    max_value=180, 
                    value=st.session_state.weather_refresh_interval,
                    step=5,
                    key="weather_refresh_interval_slider"
                )
                st.session_state.weather_refresh_interval = new_refresh_interval
                
                # Apply button for setting the interval
                if st.sidebar.button("Apply Weather Interval", key="apply_weather_interval"):
                    try:
                        # Update the weather manager with the new interval
                        weather_manager.set_refresh_interval(city, st.session_state.weather_refresh_interval)
                        
                        # Force an immediate refresh by setting the last fetch time to the past
                        if 'last_weather_fetch' in st.session_state and city in st.session_state.last_weather_fetch:
                            current_time = time.time()
                            # Set last fetch time to current time minus the new interval in seconds
                            # This will trigger a refresh on the next weather data access
                            new_interval = st.session_state.weather_refresh_interval * 60  # convert to seconds
                            st.session_state.last_weather_fetch[city] = current_time - new_interval
                        
                        st.sidebar.success(f"Weather refresh interval for {city} set to {st.session_state.weather_refresh_interval} minutes")
                    except Exception as e:
                        st.sidebar.error(f"Error setting weather interval: {str(e)}")
                
                # Show current refresh interval
                st.sidebar.info(f"Current refresh interval for {city}: {refresh_interval} minutes")
                
                # Add manual refresh button
                if st.sidebar.button("Refresh Weather Data Now", key="refresh_weather_now"):
                    try:
                        if 'last_weather_fetch' in st.session_state and city in st.session_state.last_weather_fetch:
                            # Force a refresh by setting the last fetch time to the past
                            st.session_state.last_weather_fetch[city] = 0
                        st.sidebar.success(f"Weather data for {city} will be refreshed on the next cycle")
                    except Exception as e:
                        st.sidebar.error(f"Error setting weather refresh: {str(e)}")
            except Exception as e:
                st.sidebar.error(f"Error retrieving weather settings: {str(e)}")
                logging.error(f"Error in weather settings: {str(e)}")

    @staticmethod
    def _create_analytics_settings_section():
        """Create analytics settings section in sidebar"""
        st.sidebar.subheader("Analytics Settings")
        
        # Get current camera config
        if 'selected_camera' not in st.session_state or st.session_state.selected_camera not in st.session_state.cameras:
            st.sidebar.warning("No camera selected")
            return
            
        camera_id = st.session_state.selected_camera
        camera_config = st.session_state.cameras[camera_id]
        
        # Initialize analytics refresh interval if not in config
        if 'analytics_refresh_interval' not in camera_config:
            camera_config['analytics_refresh_interval'] = 5  # Default 5 seconds
            
        # Create a session state variable for the refresh interval
        if 'analytics_refresh_interval' not in st.session_state:
            st.session_state.analytics_refresh_interval = camera_config['analytics_refresh_interval']
            
        # Analytics refresh settings
        with st.sidebar.expander("Analytics Configuration", expanded=False):
            # Configure refresh interval
            new_refresh_interval = st.slider(
                "Analytics refresh interval (seconds)", 
                min_value=1, 
                max_value=60, 
                value=st.session_state.analytics_refresh_interval,
                step=1,
                key="analytics_refresh_interval_slider"
            )
            st.session_state.analytics_refresh_interval = new_refresh_interval
            
            # Enable/disable analytics
            analytics_enabled = st.checkbox(
                "Enable analytics processing", 
                value=camera_config.get('analytics_enabled', True),
                key="analytics_enabled_checkbox"
            )
            
            # Apply button for settings
            if st.button("Apply Analytics Settings", key="apply_analytics_settings"):
                try:
                    # Update the camera config
                    camera_config['analytics_refresh_interval'] = st.session_state.analytics_refresh_interval
                    camera_config['analytics_enabled'] = analytics_enabled
                    
                    # If we have a camera manager, update its settings directly
                    if 'camera_managers' in st.session_state and camera_id in st.session_state.camera_managers:
                        camera_manager = st.session_state.camera_managers[camera_id]
                        if hasattr(camera_manager, 'analytics_refresh_interval'):
                            camera_manager.analytics_refresh_interval = st.session_state.analytics_refresh_interval
                        if hasattr(camera_manager, 'analytics_enabled'):
                            camera_manager.analytics_enabled = analytics_enabled
                        
                        # Force immediate update
                        if hasattr(camera_manager, '_update_analytics') and analytics_enabled:
                            camera_manager._update_analytics()
                    
                    st.success("Analytics settings updated")
                except Exception as e:
                    st.error(f"Error updating analytics settings: {str(e)}")
                    logger.error(f"Error in analytics settings: {str(e)}")
            
            # Show current settings
            st.info(f"Current refresh interval: {camera_config.get('analytics_refresh_interval', 5)} seconds")
            
            # Add manual update button
            if st.button("Update Analytics Now", key="update_analytics_now"):
                if 'camera_managers' in st.session_state and camera_id in st.session_state.camera_managers:
                    camera_manager = st.session_state.camera_managers[camera_id]
                    if hasattr(camera_manager, '_update_analytics'):
                        success = camera_manager._update_analytics()
                        if success:
                            st.success("Analytics updated successfully")
                        else:
                            st.error("Failed to update analytics")
                    else:
                        st.error("Camera manager doesn't support analytics updates")
                else:
                    st.error("Camera manager not found")

    @staticmethod
    def create_camera_grid_tab():
        """Create a grid view of all cameras"""
        st.header("Camera Grid View")
        
        if 'camera_managers' not in st.session_state or not st.session_state.camera_managers:
            st.info("No cameras configured. Please add cameras to see them in the grid view.")
            return
        
        st.write("This tab shows a grid view of all configured cameras for easy monitoring.")
        
        # Settings for grid view
        with st.expander("Grid View Settings", expanded=False):
            # Number of columns in the grid
            cols_in_grid = st.slider("Columns in grid", 1, 4, 2)
            
            # Auto-refresh settings
            auto_refresh = st.checkbox("Auto-refresh grid", value=True)
            refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 10)
            
            # Image quality settings
            image_width = st.slider("Image width (%)", 50, 100, 100)
            
            # Connection timeout setting
            connection_timeout = st.slider("Connection timeout (seconds)", 1, 15, 5, 
                                         help="Maximum time to wait when connecting to a camera")
            
            # Manual refresh button - use session state instead of direct rerun
            if st.button("Refresh All Cameras Now"):
                # Set a last refresh time in the past to force refresh next time
                st.session_state.last_grid_refresh = 0
                # Set our flag to indicate we want a refresh 
                st.session_state.grid_refresh_requested = True
            
            # Auto-connect setting
            auto_connect = st.checkbox("Auto-connect all cameras", value=True)
                
        # Handle auto refresh or manual refresh
        refresh_needed = False
        
        # Initialize last_grid_refresh if not exists
        if 'last_grid_refresh' not in st.session_state:
            st.session_state.last_grid_refresh = time.time()
        
        # Check auto-refresh
        current_time = time.time()
        if auto_refresh and current_time - st.session_state.last_grid_refresh > refresh_interval:
            st.session_state.last_grid_refresh = current_time
            refresh_needed = True
            
        # Initialize camera loading states if they don't exist
        if 'camera_loading_states' not in st.session_state:
            st.session_state.camera_loading_states = {}
            
        # Create grid of cameras
        camera_managers = st.session_state.camera_managers
        total_cameras = len(camera_managers)
        
        # Ensure frame cache is initialized for each camera
        for camera_id in camera_managers:
            frame_cache_key = f"frame_cache_{camera_id}"
            if frame_cache_key not in st.session_state:
                st.session_state[frame_cache_key] = None
        
        # Auto-connect cameras if enabled
        if 'auto_connect_attempted' not in st.session_state:
            st.session_state.auto_connect_attempted = {}
            
        # Get current time for auto-connect attempts (retry every 30 seconds)
        current_time = time.time()
        
        # Create rows based on number of columns
        for i in range(0, total_cameras, cols_in_grid):
            cols = st.columns(cols_in_grid)
            
            for j in range(cols_in_grid):
                idx = i + j
                if idx < total_cameras:
                    camera_id = list(camera_managers.keys())[idx]
                    camera_manager = camera_managers[camera_id]
                    camera_config = st.session_state.cameras[camera_id]
                    
                    with cols[j]:
                        st.subheader(camera_config.get('name', camera_id))
                        
                        # Display connection status
                        if camera_manager.is_connected():
                            st.success("Connected")
                            
                            # Set loading state for this camera
                            loading_key = f"loading_{camera_id}"
                            if loading_key not in st.session_state.camera_loading_states:
                                st.session_state.camera_loading_states[loading_key] = True
                            
                            # Initialize frame cache if needed
                            frame_cache_key = f"frame_cache_{camera_id}"
                            
                            # Show loading spinner only on initial load
                            if st.session_state.camera_loading_states[loading_key]:
                                with st.spinner("Loading camera feed..."):
                                    # Get current frame
                                    frame = camera_manager.read_frame()
                                    if frame is not None and frame.size > 0:
                                        # Display the frame
                                        st.image(frame, channels="BGR", use_container_width=True)
                                        # Cache the frame
                                        st.session_state[frame_cache_key] = frame
                                        # Update loading state
                                        st.session_state.camera_loading_states[loading_key] = False
                                    else:
                                        # Still loading or failed
                                        st.warning("Waiting for video stream...")
                                        
                                        # Check if it's taking too long (more than the configured timeout)
                                        if 'loading_start_time' not in st.session_state:
                                            st.session_state.loading_start_time = {}
                                        
                                        if camera_id not in st.session_state.loading_start_time:
                                            st.session_state.loading_start_time[camera_id] = time.time()
                                        
                                        loading_time = time.time() - st.session_state.loading_start_time[camera_id]
                                        if loading_time > connection_timeout:
                                            st.error(f"Timeout after {int(loading_time)}s. Stream may be unavailable.")
                                            # Reset loading state to try again next refresh
                                            st.session_state.camera_loading_states[loading_key] = False
                            else:
                                # Not in loading state, try to get a new frame if refresh needed
                                if refresh_needed:
                                    try:
                                        frame = camera_manager.read_frame()
                                        if frame is not None and frame.size > 0:
                                            # Cache the new frame
                                            st.session_state[frame_cache_key] = frame
                                    except Exception as e:
                                        st.error(f"Error refreshing frame: {str(e)}")
                                
                                # Display the cached frame (or latest if just refreshed)
                                cached_frame = st.session_state[frame_cache_key]
                                if cached_frame is not None:
                                    # Display the frame
                                    st.image(cached_frame, channels="BGR", use_container_width=True)
                                    
                                    # Update last successful frame time
                                    if 'last_successful_frame' not in st.session_state:
                                        st.session_state.last_successful_frame = {}
                                    st.session_state.last_successful_frame[camera_id] = time.time()
                                    
                                    # Get visibility status from camera data
                                    if camera_id in st.session_state.cameras_data:
                                        camera_data = st.session_state.cameras_data[camera_id]
                                        visibility_status = camera_data.get('visibility_status', 'Unknown')
                                        if visibility_status == 'Poor':
                                            st.warning(f"Visibility: {visibility_status}")
                                        elif visibility_status == 'Good':
                                            st.success(f"Visibility: {visibility_status}")
                                        else:
                                            st.info(f"Visibility: {visibility_status}")
                                    
                                    # Show last frame time
                                    last_frame_time = time.time() - st.session_state.last_successful_frame.get(camera_id, 0)
                                    if last_frame_time < 60:  # If last frame was under a minute ago
                                        st.caption(f"Last frame: {int(last_frame_time)}s ago")
                                else:
                                    st.error("No frame available - manually refresh or wait for auto-refresh")
                        else:
                            st.error("Disconnected")
                            
                            # Implement auto-connect logic
                            if ('auto_connect_attempted' not in st.session_state or 
                                camera_id not in st.session_state.auto_connect_attempted or
                                current_time - st.session_state.auto_connect_attempted.get(camera_id, 0) > 30):
                                
                                # Only try to auto-connect if enabled
                                if auto_connect:
                                    progress_text = f"Connecting to {camera_id}..."
                                    connection_bar = st.progress(0, text=progress_text)
                                    
                                    # Connect with progress visualization
                                    connect_success = False
                                    for percent_complete in range(0, 101, 10):
                                        if percent_complete == 0:
                                            # Start connecting in the first step
                                            connect_success = camera_manager.connect()
                                        
                                        # Update progress bar
                                        connection_bar.progress(percent_complete, text=progress_text)
                                        if percent_complete < 100:
                                            time.sleep(0.05)  # Small delay for visual effect
                                    
                                    # Record the attempt time
                                    st.session_state.auto_connect_attempted[camera_id] = current_time
                                    
                                    if connect_success:
                                        # Set loading state for frame fetching
                                        loading_key = f"loading_{camera_id}"
                                        st.session_state.camera_loading_states[loading_key] = True
                                        if 'loading_start_time' not in st.session_state:
                                            st.session_state.loading_start_time = {}
                                        st.session_state.loading_start_time[camera_id] = time.time()
                                        
                                        st.success(f"Connected to {camera_id}")
                                    else:
                                        st.error(f"Failed to connect to {camera_id}")
                            else:
                                # Show when we'll retry connecting
                                retry_in = 30 - int(current_time - st.session_state.auto_connect_attempted.get(camera_id, 0))
                                if retry_in > 0:
                                    st.info(f"Will retry connecting in {retry_in} seconds")
        
        # Show overall status message at the bottom
        st.markdown("---")
        
        # Determine overall system status
        connected_cameras = sum(1 for cm in camera_managers.values() if cm.is_connected())
        if connected_cameras == total_cameras:
            st.success(f"All cameras operational with good visibility")
        elif connected_cameras > 0:
            st.warning(f"{connected_cameras} of {total_cameras} cameras connected")
        else:
            st.error("No cameras connected - check network connections")
            
        # Update the last grid refresh time
        st.session_state.last_grid_refresh = current_time

    @staticmethod
    def create_dashboard_overview():
        """Create a dashboard overview that summarizes the status of all cameras and systems"""
        st.header("📋 System Overview")
        
        # System info section
        st.subheader("System Information")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            # Current datetime
            now = datetime.now()
            st.metric("Current Date", now.strftime("%Y-%m-%d"))
            st.metric("Current Time", now.strftime("%H:%M:%S"))
            
        with col2:
            # Camera stats
            if 'camera_managers' in st.session_state:
                total_cameras = len(st.session_state.camera_managers)
                connected_cameras = sum(1 for cm in st.session_state.camera_managers.values() if cm.is_connected())
                st.metric("Total Cameras", str(total_cameras))
                st.metric("Connected Cameras", f"{connected_cameras}/{total_cameras}")
                
        with col3:
            # Weather info
            if 'weather_data' in st.session_state and st.session_state.weather_data:
                for city, data in st.session_state.weather_data.items():
                    st.metric(f"Weather in {city}", data.get('condition', 'Unknown'))
                    st.metric(f"Temperature", f"{data.get('temperature', 'N/A')}°C")
        
        # Active alerts section
        st.subheader("Active Alerts")
        
        # Check for cameras with poor visibility
        cameras_with_issues = []
        if 'camera_managers' in st.session_state and 'cameras_data' in st.session_state:
            for camera_id, camera_data in st.session_state.cameras_data.items():
                camera_manager = st.session_state.camera_managers.get(camera_id)
                
                # Check if camera is connected
                if camera_manager and not camera_manager.is_connected():
                    cameras_with_issues.append((camera_id, "Disconnected", "error"))
                
                # Check visibility status
                if 'visibility_status' in camera_data:
                    status = camera_data.get('visibility_status')
                    if status == 'Poor':
                        cameras_with_issues.append((camera_id, f"Poor Visibility ({camera_data.get('visibility_score', 0):.1f}%)", "warning"))
        
        if cameras_with_issues:
            for camera_id, issue, level in cameras_with_issues:
                if level == "error":
                    st.error(f"🚨 {camera_id}: {issue}")
                else:
                    st.warning(f"⚠️ {camera_id}: {issue}")
        else:
            st.success("✅ All systems operational")
            
        # System health metrics
        st.subheader("System Health")
        
        # Camera visibility summary chart
        if 'cameras_data' in st.session_state and st.session_state.cameras_data:
            # Create data for visibility chart
            chart_data = []
            for camera_id, camera_data in st.session_state.cameras_data.items():
                if 'visibility_score' in camera_data:
                    chart_data.append({
                        'Camera': camera_id,
                        'Visibility Score': camera_data.get('visibility_score', 0)
                    })
                    
            if chart_data:
                import pandas as pd
                df = pd.DataFrame(chart_data)
                st.bar_chart(df.set_index('Camera'), use_container_width=True)
                
        # Quick actions
        st.subheader("Quick Actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Refresh All Cameras", use_container_width=True):
                if 'camera_managers' in st.session_state:
                    for camera_id, camera_manager in st.session_state.camera_managers.items():
                        if not camera_manager.is_connected():
                            camera_manager.connect()
                    st.success("Initiated reconnection for all cameras")
                    st.rerun()
                    
        with col2:
            if st.button("Refresh Weather Data", use_container_width=True):
                if 'last_weather_fetch' in st.session_state:
                    st.session_state.last_weather_fetch = {}
                    st.success("Weather data will be refreshed on next reload")
                    st.rerun()
                    
        with col3:
            if st.button("View Camera Grid", use_container_width=True):
                # We'll use this button to navigate to the camera grid tab
                # since we can't directly switch tabs, we'll set a flag and handle it in JS
                st.session_state.open_camera_grid = True
                st.markdown("""
                <script>
                    setTimeout(function() {
                        window.parent.document.querySelectorAll('button[data-baseweb="tab"]')[7].click();
                    }, 10);
                </script>
                """, unsafe_allow_html=True) 

    @staticmethod
    def create_live_feed_tab(camera_manager):
        """Creates the live feed tab with camera stream and controls"""
        st.subheader("Live Camera Feed")
        
        if camera_manager is None:
            st.info("Select a camera from the sidebar to view the live feed.")
            return
        
        if not camera_manager.is_connected():
            st.warning("Camera is not connected. Click 'Connect Camera' in the sidebar to connect.")
            return
        
        # Display camera info
        st.markdown(f"**Camera:** {camera_manager.camera_id}")
        
        # Add refresh rate control
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Auto-refresh toggle
            auto_refresh = st.checkbox("Auto-refresh", value=True, key="auto_refresh_live")
        
        with col2:
            # Refresh interval in seconds
            refresh_rate = st.selectbox(
                "Refresh rate",
                options=[0.5, 1.0, 2.0, 5.0, 10.0],
                index=1,
                key="refresh_rate_live"
            )
        
        # Manual refresh button
        if not auto_refresh:
            if st.button("Refresh Frame"):
                st.rerun()
        
        # Get a frame from the camera
        frame = camera_manager.read_frame()
        
        # Display the frame if available
        if frame is not None:
            # Get camera status
            status = camera_manager.get_status()
            visibility_status = status.get('visibility_status', 'Unknown')
            
            # Add status information
            st.markdown(
                f"**Visibility Status:** "
                f"<span style='color: {'green' if visibility_status == 'Good' else 'orange' if visibility_status == 'Moderate' else 'red'};"
                f"font-weight: bold;'>{visibility_status}</span>",
                unsafe_allow_html=True
            )
            
            # Convert the frame from BGR to RGB (for display in Streamlit)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Display the frame
            st.image(rgb_frame, caption=f"Camera: {camera_manager.camera_id}", use_column_width=True)
            
            # Add recording info if recording
            if camera_manager.recording:
                recording_time = time.time() - camera_manager.recording_start_time if camera_manager.recording_start_time else 0
                minutes, seconds = divmod(int(recording_time), 60)
                hours, minutes = divmod(minutes, 60)
                
                st.info(f"🔴 Recording in progress: {hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            st.error("Failed to read frame from camera. Check connection and try again.")
        
        # Auto-refresh if enabled
        if auto_refresh:
            time.sleep(refresh_rate)
            st.rerun()
            
        return

    @staticmethod
    def create_roi_config_tab(camera_manager):
        """Creates the ROI configuration tab"""
        st.subheader("Region of Interest (ROI) Configuration")
        
        if camera_manager is None:
            st.info("Select a camera from the sidebar to configure ROIs.")
            return
            
        # Create two columns for the ROI configuration
        col1, col2 = st.columns([1, 1])
        
        # List existing ROIs in the first column
        with col1:
            st.subheader("Existing ROIs")
            
            # Get current ROIs
            roi_regions = camera_manager.get_roi_regions()
            
            if not roi_regions:
                st.info("No ROIs defined for this camera. Add a new ROI to start.")
            else:
                # Create a selection widget for ROIs
                st.write("Select an ROI to edit or delete:")
                
                # Format ROI display with more information
                def format_func(roi):
                    name = roi.get("name", "Unnamed ROI")
                    x = roi.get("x", 0)
                    y = roi.get("y", 0)
                    width = roi.get("width", 0)
                    height = roi.get("height", 0)
                    distance = roi.get("distance", 100)
                    return f"{name} (Position: {x:.2f}, {y:.2f} - Size: {width:.2f}x{height:.2f} - Distance: {distance}m)"
                
                # Create a selection box for ROIs
                selected_roi_index = st.selectbox(
                    "Select ROI",
                    options=list(range(len(roi_regions))),
                    format_func=lambda i: format_func(roi_regions[i])
                )
                
                # Show selected ROI details and provide delete button
                selected_roi = roi_regions[selected_roi_index]
                
                # Display details of selected ROI in a neat box
                st.markdown("**Selected ROI Details:**")
                details_col1, details_col2 = st.columns(2)
                
                with details_col1:
                    st.markdown(f"**Name:** {selected_roi.get('name', 'Unnamed')}")
                    st.markdown(f"**Position X:** {selected_roi.get('x', 0):.2f}")
                    st.markdown(f"**Position Y:** {selected_roi.get('y', 0):.2f}")
                
                with details_col2:
                    st.markdown(f"**Width:** {selected_roi.get('width', 0):.2f}")
                    st.markdown(f"**Height:** {selected_roi.get('height', 0):.2f}")
                    st.markdown(f"**Distance:** {selected_roi.get('distance', 100)} meters")
                
                # Delete button for selected ROI
                if st.button("Delete Selected ROI"):
                    roi_regions.pop(selected_roi_index)
                    
                    # Update camera with modified ROI list
                    camera_manager.set_roi_regions(roi_regions)
                    
                    st.success(f"Deleted ROI: {selected_roi.get('name', 'Unnamed')}")
                    st.rerun()
        
        # Add/edit ROI in the second column
        with col2:
            st.subheader("Add/Edit ROI")
            
            # Provide fields for ROI configuration
            with st.form("roi_form"):
                # ROI Name
                roi_name = st.text_input("ROI Name", value=selected_roi.get("name", "") if 'selected_roi' in locals() else "")
                
                # ROI coordinates (relative to frame dimensions)
                x = st.slider("Position X", min_value=0.0, max_value=1.0, value=selected_roi.get("x", 0.1) if 'selected_roi' in locals() else 0.1, step=0.01,
                             help="Horizontal position relative to frame width (0-1)")
                y = st.slider("Position Y", min_value=0.0, max_value=1.0, value=selected_roi.get("y", 0.1) if 'selected_roi' in locals() else 0.1, step=0.01,
                             help="Vertical position relative to frame height (0-1)")
                
                # ROI size (relative to frame dimensions)
                width = st.slider("Width", min_value=0.05, max_value=1.0, value=selected_roi.get("width", 0.2) if 'selected_roi' in locals() else 0.2, step=0.01,
                                 help="Width relative to frame width (0-1)")
                height = st.slider("Height", min_value=0.05, max_value=1.0, value=selected_roi.get("height", 0.2) if 'selected_roi' in locals() else 0.2, step=0.01,
                                  help="Height relative to frame height (0-1)")
                
                # Distance parameter for visibility calculation
                distance = st.number_input("Distance (meters)", min_value=1, max_value=1000, value=selected_roi.get("distance", 100) if 'selected_roi' in locals() else 100,
                                         help="Estimated distance to this region in meters")
                
                # Form submission buttons
                col1, col2 = st.columns(2)
                
                with col1:
                    submit_add = st.form_submit_button("Add as New ROI")
                
                with col2:
                    submit_update = st.form_submit_button("Update Selected ROI")
            
            # Handle form submission for adding a new ROI
            if submit_add:
                # Create new ROI definition
                new_roi = {
                    "name": roi_name if roi_name else f"ROI_{len(roi_regions)}",
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "distance": distance
                }
                
                # Add to existing ROIs
                roi_regions.append(new_roi)
                
                # Update camera with modified ROI list
                camera_manager.set_roi_regions(roi_regions)
                
                st.success(f"Added new ROI: {new_roi['name']}")
                st.rerun()
            
            # Handle form submission for updating an existing ROI
            if submit_update and 'selected_roi' in locals():
                # Update existing ROI
                roi_regions[selected_roi_index] = {
                    "name": roi_name if roi_name else selected_roi.get("name", f"ROI_{selected_roi_index}"),
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "distance": distance
                }
                
                # Update camera with modified ROI list
                camera_manager.set_roi_regions(roi_regions)
                
                st.success(f"Updated ROI: {roi_regions[selected_roi_index]['name']}")
                st.rerun()
        
        # Add a preview of ROIs if a frame is available
        st.subheader("ROI Preview")
        
        if camera_manager.is_connected():
            # Get current frame
            frame = camera_manager.read_frame()
            
            if frame is not None:
                # Convert from BGR to RGB for display
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Display the frame with ROIs
                st.image(rgb_frame, caption="Current ROI Configuration", use_column_width=True)
                
                # Add explanation
                st.info("""
                The colored rectangles show the Regions of Interest (ROIs) used for visibility analysis.
                Each ROI is monitored for color changes that might indicate poor visibility.
                
                - Green rectangles: ROIs with good visibility
                - Orange/Red rectangles: ROIs with reduced visibility
                """)
            else:
                st.warning("Could not get a frame from the camera to preview ROIs.")
        else:
            st.warning("Camera is not connected. Connect to see a preview of ROIs.")
        
        return