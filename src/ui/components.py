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
import json
from plotly.subplots import make_subplots
import random

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
        UIComponents._create_analytics_settings_section()
        st.sidebar.markdown("---")
        UIComponents._create_weather_settings_section()
        st.sidebar.markdown("---")
        # Add performance monitoring settings
        if 'system_monitor' in st.session_state and st.session_state.system_monitor:
            UIComponents._create_performance_monitoring_settings_section()
        
        return selected
    
    @staticmethod
    def create_main_content(camera_config, camera_status, weather_data, feed_container):
        """Create the main content with tabs"""
        # Create tabs for different sections
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
            "📡 Live Monitoring",
            "📊 Analytics",
            "🌦️ Weather Insights",
            "🔍 ROI Configuration",
            "📼 Recordings",
            "🔍 Highlights",
            "📆 Historical Data",
            "📹 Camera Grid",
            "📋 Dashboard Overview",
            "⚙️ Performance"
        ])
        
        # Check if camera status is available
        camera_connected = camera_status.get('connected', False) if camera_status else False
        
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
            
            # Display camera feed placeholder or error message
            st.markdown("### Live Feed")
            if camera_connected:
                feed_container
            else:
                st.error("Camera is not connected. Please check your camera connection or settings.")
                if st.button("Try Reconnect", key="try_reconnect_btn"):
                    st.session_state.camera_connected = False
                    st.rerun()

            # Display weather metrics if available
            if weather_data:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Temperature", f"{weather_data.get('temperature', 'N/A')}°C")
                    st.metric("Humidity", f"{weather_data.get('humidity', 'N/A')}%")
                with col2:
                    st.metric("Visibility", f"{weather_data.get('visibility', 'N/A')} km")
                    st.metric("Condition", weather_data.get('condition', 'N/A'))
            else:
                st.warning("Weather data is not available. Please check your weather API settings.")
        
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
            
        # Performance tab
        with tab10:
            if 'system_monitor' in st.session_state and st.session_state.system_monitor:
                UIComponents.create_performance_monitoring_tab(st.session_state.system_monitor)
            else:
                st.info("System performance monitoring is not available. Please check your installation.")
            
        return (tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10)

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
            
            # If not connected and we don't have valid data, show a warning but don't block the UI
            if not camera_manager.is_connected() and not has_valid_data:
                st.warning("Camera is not connected or has not processed any frames yet. Limited analytics are available.")
                
                # Add a reconnect button
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Reconnect Camera", key="reconnect_analytics_btn"):
                        with st.spinner("Reconnecting to camera..."):
                            success = camera_manager.reconnect()
                            if success:
                                st.success("Successfully reconnected!")
                                time.sleep(1)  # Give time for user to see message
                                st.experimental_rerun()
                            else:
                                st.error("Failed to reconnect. Please check camera settings and try again.")
                with col2:
                    if st.button("Generate Test Metrics", key="generate_test_metrics_btn"):
                        with st.spinner("Generating test data..."):
                            camera_manager.force_update_metrics()
                            st.success("Test metrics generated!")
                            time.sleep(1)
                            st.experimental_rerun()
            
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
            
            # Create three columns for metrics - show these even if camera is disconnected
            # as long as we have some data
            if has_valid_data or camera_manager.is_connected():
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
                    edge_score_text = f"{edge_score:.1f}" if edge_score is not None else "N/A"
                    
                    # Display the edge score metric with a tooltip
                    metric_with_tooltip("Edge Score", edge_score_text,
                                    tooltip="Edge detection score (0-100)",
                                    help_text="Measure of image detail/clarity based on edge detection")
                
                with col2:
                    # Get the current contrast value and format it
                    contrast = camera_data.get('contrast', 0)
                    contrast_text = f"{contrast:.1f}" if contrast is not None else "N/A"
                    
                    # Display the contrast metric with a tooltip
                    metric_with_tooltip("Contrast", contrast_text,
                                    tooltip="Image contrast level (0-100)",
                                    help_text="Difference between light and dark areas; higher values indicate more contrast")
                    
                    # Get the current color delta average and format it
                    color_delta = camera_data.get('color_delta_avg', 0)
                    color_delta_text = f"{color_delta:.1f}" if color_delta is not None else "N/A"
                    
                    # Display the color delta metric with a tooltip
                    metric_with_tooltip("Color Delta", color_delta_text,
                                    tooltip="Average color difference (0-100)",
                                    help_text="Measure of color variation between regions; lower values indicate better visibility")
                
                with col3:
                    # Get the current visibility score and format it
                    visibility_score = camera_data.get('visibility_score', 0)
                    visibility_score_text = f"{visibility_score:.1f}%" if visibility_score is not None else "N/A"
                    
                    # Determine delta color based on visibility status
                    visibility_status = camera_data.get('visibility_status', 'Unknown')
                    delta_color = "normal" if visibility_status == "Good" else "inverse"
                    
                    # Display the visibility score metric with a tooltip
                    metric_with_tooltip("Visibility Score", visibility_score_text,
                                    tooltip=f"Current visibility status: {visibility_status}",
                                    help_text="Overall visibility score based on brightness, contrast, and other factors")
                    
                    # Get the current visibility status and format it
                    status_color = "green" if visibility_status == "Good" else "orange" if visibility_status == "Fair" else "red"
                    
                    # Display the visibility status metric with a tooltip
                    st.markdown(f"<p style='color: {status_color}; font-weight: bold;'>Status: {visibility_status}</p>", unsafe_allow_html=True)
            else:
                st.info("No analytics data available yet. This section will update once data is collected.")
                
            # Add visualization of analytics over time
            st.subheader("Visibility Analytics")
            
            # Create placeholder data for visualization
            # In a real app, this would come from the camera manager
            timestamps = pd.date_range(start="2023-04-01", periods=24, freq="H")
            vis_data = {
                "timestamp": timestamps,
                "visibility_score": [random.randint(50, 100) for _ in range(24)],
                "brightness": [random.randint(100, 200) for _ in range(24)],
                "contrast": [random.randint(30, 90) for _ in range(24)],
                "edge_score": [random.randint(40, 80) for _ in range(24)]
            }
            
            df = pd.DataFrame(vis_data)
            
            # Create visualization
            st.line_chart(df.set_index("timestamp")[["visibility_score"]])
            
            # Show more detailed view in expander
            with st.expander("Detailed Metrics", expanded=False):
                # Create multiple line chart with all metrics
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                # Add visibility score trace
                fig.add_trace(
                    go.Scatter(x=df["timestamp"], y=df["visibility_score"], name="Visibility Score"),
                    secondary_y=False,
                )
                
                # Add brightness trace
                fig.add_trace(
                    go.Scatter(x=df["timestamp"], y=df["brightness"], name="Brightness"),
                    secondary_y=True,
                )
                
                # Add contrast trace
                fig.add_trace(
                    go.Scatter(x=df["timestamp"], y=df["contrast"], name="Contrast"),
                    secondary_y=False,
                )
                
                # Add edge score trace
                fig.add_trace(
                    go.Scatter(x=df["timestamp"], y=df["edge_score"], name="Edge Score"),
                    secondary_y=False,
                )
                
                # Set titles and labels
                fig.update_layout(
                    title_text="Detailed Visibility Metrics",
                    height=500
                )
                fig.update_xaxes(title_text="Time")
                fig.update_yaxes(title_text="Score (0-100)", secondary_y=False)
                fig.update_yaxes(title_text="Brightness (0-255)", secondary_y=True)
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Show data table
                st.dataframe(df)
                
        except Exception as e:
            st.error(f"Error displaying analytics: {str(e)}")
            
        return

    @staticmethod
    def _create_roi_config_tab(camera_config, camera_manager):
        """Create the ROI configuration tab"""
        st.subheader("Region of Interest (ROI) Configuration")
        
        # Initialize ROI preview in session state if not exists
        if 'roi_preview' not in st.session_state:
            st.session_state.roi_preview = {
                "name": "New ROI",
                "x": 0.1,
                "y": 0.1,
                "width": 0.2,
                "height": 0.2,
                "distance": 100
            }
        
        # Initialize roi_preview_frame in session state
        if 'roi_preview_frame' not in st.session_state:
            st.session_state.roi_preview_frame = None
            try:
                # Try to get a frame from the camera
                if camera_manager and camera_manager.is_connected():
                    frame = camera_manager.read_frame()
                    st.session_state.roi_preview_frame = frame
            except Exception as e:
                st.warning(f"Could not get camera frame for preview: {str(e)}")
        
        # Threshold settings
        st.subheader("Visibility Thresholds")
        
        # Create columns for threshold settings
        threshold_col1, threshold_col2 = st.columns(2)
        
        with threshold_col1:
            # Brightness threshold
            brightness_threshold = st.slider(
                "Brightness Threshold",
                min_value=0,
                max_value=255,
                value=camera_config.get('brightness_threshold', 50),
                help="Minimum brightness level to consider good visibility"
            )
            
            # Contrast threshold
            contrast_threshold = st.slider(
                "Contrast Threshold",
                min_value=0,
                max_value=100,
                value=camera_config.get('contrast_threshold', 30),
                help="Minimum contrast level to consider good visibility"
            )
        
        with threshold_col2:
            # Edge score threshold
            edge_threshold = st.slider(
                "Edge Detection Threshold",
                min_value=0,
                max_value=100,
                value=camera_config.get('edge_threshold', 20),
                help="Minimum edge score to consider good visibility"
            )
            
            # Overall visibility threshold
            visibility_threshold = st.slider(
                "Overall Visibility Threshold",
                min_value=0,
                max_value=100,
                value=camera_config.get('visibility_threshold', 70),
                help="Minimum overall score to consider good visibility"
            )
        
        # Check if thresholds changed
        threshold_changes = {}
        
        if camera_config.get('brightness_threshold', 50) != brightness_threshold:
            threshold_changes['brightness_threshold'] = brightness_threshold
            
        if camera_config.get('contrast_threshold', 30) != contrast_threshold:
            threshold_changes['contrast_threshold'] = contrast_threshold
            
        if camera_config.get('edge_threshold', 20) != edge_threshold:
            threshold_changes['edge_threshold'] = edge_threshold
            
        if camera_config.get('visibility_threshold', 70) != visibility_threshold:
            threshold_changes['visibility_threshold'] = visibility_threshold
        
        # Show apply button if thresholds changed
        if threshold_changes and st.button("Apply Threshold Changes", key="apply_threshold_btn"):
            st.success("Visibility thresholds updated")
        
        # Create two columns for the ROI configuration
        col1, col2 = st.columns([1, 1])
        
        # List existing ROIs in the first column
        with col1:
            st.subheader("Existing ROIs")
            
            # Get current ROIs
            roi_regions = camera_manager.get_roi_regions()
            
            if not roi_regions:
                st.info("No ROIs defined for this camera. Add a new ROI to start.")
                selected_roi_index = None
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
                
                # Update preview with selected ROI
                st.session_state.roi_preview = selected_roi.copy()
                
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
                if st.button("Delete Selected ROI", key="delete_roi_btn"):
                    roi_regions.pop(selected_roi_index)
                    
                    # Update camera with modified ROI list
                    camera_manager.set_roi_regions(roi_regions)
                    
                    st.success(f"Deleted ROI: {selected_roi.get('name', 'Unnamed')}")
                    st.rerun()
                    
            # Display live preview with current ROIs
            st.subheader("Live Preview")
            if 'roi_preview_frame' not in st.session_state:
                st.session_state.roi_preview_frame = None
                try:
                    # Try to get a frame from the camera
                    if camera_manager and camera_manager.is_connected():
                        frame = camera_manager.read_frame()
                        st.session_state.roi_preview_frame = frame
                except Exception as e:
                    st.warning(f"Could not get camera frame for preview: {str(e)}")
                    
            if st.session_state.roi_preview_frame is not None:
                # Clone the frame to avoid modifying the original
                preview_img = st.session_state.roi_preview_frame.copy()
                h, w = preview_img.shape[:2]
                
                # Draw existing ROIs
                for i, roi in enumerate(roi_regions):
                    x = int(roi["x"] * w)
                    y = int(roi["y"] * h)
                    width = int(roi["width"] * w)
                    height = int(roi["height"] * h)
                    
                    # Draw rectangle with different colors
                    color = (0, 255, 0)  # Default green color
                    if i == selected_roi_index:
                        color = (0, 0, 255)  # Red for selected ROI
                        
                    # Draw ROI rectangle
                    cv2.rectangle(preview_img, (x, y), (x + width, y + height), color, 2)
                    
                    # Add ROI name
                    cv2.putText(preview_img, roi["name"], (x+5, y+20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # Convert to RGB for display
                preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
                st.image(preview_rgb, caption="Current ROIs", use_column_width=True)
            else:
                st.warning("No camera frame available for preview.")
        
        # Add/edit ROI in the second column
        with col2:
            st.subheader("Add/Edit ROI")
            
                # ROI Name
            roi_name = st.text_input("ROI Name", 
                               value=st.session_state.roi_preview.get("name", ""))
            
            # When we update ROI settings, update the preview immediately
            def update_preview():
                if 'roi_preview_frame' not in st.session_state:
                    st.session_state.roi_preview_frame = None
                    try:
                        # Try to get a frame from the camera
                        if camera_manager and camera_manager.is_connected():
                            frame = camera_manager.read_frame()
                            st.session_state.roi_preview_frame = frame
                    except Exception as e:
                        st.warning(f"Could not get camera frame for preview: {str(e)}")
                        return None
                
                if st.session_state.roi_preview_frame is not None:
                    preview_img = st.session_state.roi_preview_frame.copy()
                    h, w = preview_img.shape[:2]
                    
                    # Draw existing ROIs first in green
                    for roi in camera_manager.get_roi_regions():
                        x = int(roi["x"] * w)
                        y = int(roi["y"] * h)
                        width = int(roi["width"] * w)
                        height = int(roi["height"] * h)
                        cv2.rectangle(preview_img, (x, y), (x + width, y + height), (0, 255, 0), 2)
                        cv2.putText(preview_img, roi["name"], (x+5, y+20), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    
                    # Draw preview ROI in blue
                    x = int(st.session_state.x_slider * w)
                    y = int(st.session_state.y_slider * h)
                    width = int(st.session_state.width_slider * w)
                    height = int(st.session_state.height_slider * h)
                    
                    cv2.rectangle(preview_img, (x, y), (x + width, y + height), (255, 0, 0), 2)
                    cv2.putText(preview_img, roi_name if roi_name else "New ROI", (x+5, y+20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                    
                    # Display preview
                    preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
                    return preview_rgb
                return None
            
            # ROI coordinates with real-time preview
            x = st.slider("Position X", min_value=0.0, max_value=1.0, 
                        value=st.session_state.roi_preview.get("x", 0.1), step=0.01,
                        key="x_slider",
                             help="Horizontal position relative to frame width (0-1)")
            
            y = st.slider("Position Y", min_value=0.0, max_value=1.0, 
                        value=st.session_state.roi_preview.get("y", 0.1), step=0.01,
                        key="y_slider",
                             help="Vertical position relative to frame height (0-1)")
                
            # ROI size
            width = st.slider("Width", min_value=0.05, max_value=1.0, 
                           value=st.session_state.roi_preview.get("width", 0.2), step=0.01,
                           key="width_slider",
                                 help="Width relative to frame width (0-1)")
            
            height = st.slider("Height", min_value=0.05, max_value=1.0, 
                            value=st.session_state.roi_preview.get("height", 0.2), step=0.01,
                            key="height_slider",
                                  help="Height relative to frame height (0-1)")
                
            # Distance parameter
            distance = st.number_input("Distance (meters)", min_value=1, max_value=1000, 
                                    value=st.session_state.roi_preview.get("distance", 100),
                                         help="Estimated distance to this region in meters")
                
            # Update preview
            preview_img = update_preview()
            if preview_img is not None:
                st.image(preview_img, caption="ROI Preview", use_column_width=True)
            
            # ROI action buttons
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Add as New ROI", use_container_width=True, key="add_new_roi_btn"):
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
            
            with col2:
                if st.button("Update Selected ROI", use_container_width=True, disabled=selected_roi_index is None, key="update_roi_btn"):
                    if selected_roi_index is not None:
                        # Update existing ROI
                        roi_regions[selected_roi_index] = {
                            "name": roi_name if roi_name else st.session_state.roi_preview.get("name", f"ROI_{selected_roi_index}"),
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
        
            # Explanation of ROI settings
            with st.expander("ROI Help"):
                st.markdown("""
                **Region of Interest (ROI) Configuration**
                
                ROIs are areas of the camera frame that are analyzed for visibility changes:
                
                - **Position (X,Y)**: The top-left corner of the ROI relative to the frame (0-1)
                - **Width/Height**: Size of the ROI relative to the frame size (0-1)
                - **Distance**: Estimated distance in meters to the ROI area, used for visibility distance estimation
                
                Each ROI is analyzed separately, and the system detects visibility changes in each region.
                Place ROIs at different distances to help estimate visibility range.
                """)
        
        return threshold_changes

    @staticmethod
    def _create_stream_settings_section():
        """Create stream settings section in the sidebar"""
        st.sidebar.subheader("Stream Settings")
        
        # Stream refresh rate
        refresh_rate = st.sidebar.slider(
            "Refresh Rate (seconds)",
            min_value=0.1,
            max_value=5.0,
            value=st.session_state.get('refresh_rate', 0.5),
            step=0.1,
            help="How often to refresh the stream (lower values give smoother video but use more CPU)"
        )
        
        # Update session state if changed
        if 'refresh_rate' not in st.session_state or st.session_state.refresh_rate != refresh_rate:
            st.session_state.refresh_rate = refresh_rate
        
        # Auto-reconnect settings
        auto_reconnect = st.sidebar.checkbox(
            "Auto-Reconnect",
            value=st.session_state.get('auto_reconnect', True),
            help="Automatically try to reconnect if connection is lost"
        )
        
        # Update session state if changed
        if 'auto_reconnect' not in st.session_state or st.session_state.auto_reconnect != auto_reconnect:
            st.session_state.auto_reconnect = auto_reconnect
        
        # Maximum reconnection attempts
        max_attempts = st.sidebar.number_input(
            "Max Reconnection Attempts",
            min_value=1,
            max_value=100,
            value=st.session_state.get('max_reconnect_attempts', 5),
            help="Maximum number of times to try reconnecting before giving up"
        )
        
        # Update session state if changed
        if 'max_reconnect_attempts' not in st.session_state or st.session_state.max_reconnect_attempts != max_attempts:
            st.session_state.max_reconnect_attempts = max_attempts

    @staticmethod
    def _create_display_settings_section():
        """Create display settings section in the sidebar"""
        st.sidebar.subheader("Display Settings")
        
        # Get current display settings from session state or use defaults
        if 'display_settings' not in st.session_state:
            from ..config.settings import DEFAULT_DISPLAY_SETTINGS
            st.session_state.display_settings = DEFAULT_DISPLAY_SETTINGS.copy()
        
        display_settings = st.session_state.display_settings
        
        # Theme selection
        theme = st.sidebar.selectbox(
            "Theme",
            options=["Light", "Dark", "Auto"],
            index=["Light", "Dark", "Auto"].index(display_settings.get('theme', 'Auto')),
            help="UI color theme"
        )
        
        # Update session state if changed
        if display_settings.get('theme') != theme:
            display_settings['theme'] = theme
        
        # Show/hide elements
        show_timestamps = st.sidebar.checkbox(
            "Show Timestamps",
            value=display_settings.get('show_timestamps', True),
            help="Show timestamp on camera feed"
        )
        
        # Update session state if changed
        if display_settings.get('show_timestamps') != show_timestamps:
            display_settings['show_timestamps'] = show_timestamps
        
        # Show/hide metrics
        show_metrics = st.sidebar.checkbox(
            "Show Live Metrics",
            value=display_settings.get('show_metrics', True),
            help="Show live metrics on camera feed"
        )
        
        # Update session state if changed
        if display_settings.get('show_metrics') != show_metrics:
            display_settings['show_metrics'] = show_metrics
        
        # Overlay ROIs on camera feed
        show_roi = st.sidebar.checkbox(
            "Show ROIs",
            value=display_settings.get('show_roi', True),
            help="Show regions of interest on camera feed"
        )
        
        # Update session state if changed
        if display_settings.get('show_roi') != show_roi:
            display_settings['show_roi'] = show_roi

    @staticmethod
    def _create_analytics_settings_section():
        """Create analytics settings section in the sidebar"""
        st.sidebar.subheader("Analytics Settings")
        
        # Get current analytics settings from session state or create default
        if 'analytics_settings' not in st.session_state:
            st.session_state.analytics_settings = {
                'enabled': True,
                'update_interval': 5,
                'detection_threshold': 70,
                'notify_on_events': True,
                'save_events': True
            }
        
        analytics_settings = st.session_state.analytics_settings
        
        # Enable/disable analytics
        enabled = st.sidebar.checkbox(
            "Enable Analytics", 
            value=analytics_settings.get('enabled', True),
            help="Enable visibility analytics processing"
        )
        
        # Update session state if changed
        if analytics_settings.get('enabled') != enabled:
            analytics_settings['enabled'] = enabled
        
        # Only show settings if analytics are enabled
        if enabled:
            # Analytics update interval
            update_interval = st.sidebar.slider(
                "Update Interval (seconds)",
                min_value=1,
                max_value=30,
                value=analytics_settings.get('update_interval', 5),
                step=1,
                help="How often to update analytics (higher values use less CPU)"
            )
            
            # Update session state if changed
            if analytics_settings.get('update_interval') != update_interval:
                analytics_settings['update_interval'] = update_interval
            
            # Detection threshold
            detection_threshold = st.sidebar.slider(
                "Visibility Detection Threshold",
                min_value=0,
                max_value=100,
                value=analytics_settings.get('detection_threshold', 70),
                help="Threshold for detecting visibility issues (lower values are more sensitive)"
            )
            
            # Update session state if changed
            if analytics_settings.get('detection_threshold') != detection_threshold:
                analytics_settings['detection_threshold'] = detection_threshold
            
            # Notification settings
            notify_on_events = st.sidebar.checkbox(
                "Notify on Events",
                value=analytics_settings.get('notify_on_events', True),
                help="Show notifications when visibility changes are detected"
            )
            
            # Update session state if changed
            if analytics_settings.get('notify_on_events') != notify_on_events:
                analytics_settings['notify_on_events'] = notify_on_events
            
            # Save events
            save_events = st.sidebar.checkbox(
                "Save Events",
                value=analytics_settings.get('save_events', True),
                help="Save visibility events to database"
            )
            
            # Update session state if changed
            if analytics_settings.get('save_events') != save_events:
                analytics_settings['save_events'] = save_events

    @staticmethod
    def _create_weather_settings_section():
        """Create weather settings section in the sidebar"""
        st.sidebar.subheader("Weather Settings")
        
        # Get current weather settings from session state or create default
        if 'weather_settings' not in st.session_state:
            st.session_state.weather_settings = {
                'enabled': True,
                'refresh_interval': 15,  # minutes
                'display_unit': 'Metric',
                'api_key': None
            }
        
        weather_settings = st.session_state.weather_settings
        
        # Enable/disable weather data
        enabled = st.sidebar.checkbox(
            "Enable Weather Data", 
            value=weather_settings.get('enabled', True),
            help="Fetch and display weather data"
        )
        
        # Update session state if changed
        if weather_settings.get('enabled') != enabled:
            weather_settings['enabled'] = enabled
        
        # Only show settings if weather data is enabled
        if enabled:
            # Weather refresh interval
            refresh_interval = st.sidebar.slider(
                "Refresh Interval (minutes)",
                min_value=5,
                max_value=60,
                value=weather_settings.get('refresh_interval', 15),
                step=5,
                help="How often to update weather data (longer intervals reduce API calls)"
            )
            
            # Update session state if changed
            if weather_settings.get('refresh_interval') != refresh_interval:
                weather_settings['refresh_interval'] = refresh_interval
            
            # Temperature unit
            display_unit = st.sidebar.radio(
                "Display Units",
                options=["Metric", "Imperial"],
                index=0 if weather_settings.get('display_unit', 'Metric') == 'Metric' else 1,
                horizontal=True,
                help="Temperature and distance units"
            )
            
            # Update session state if changed
            if weather_settings.get('display_unit') != display_unit:
                weather_settings['display_unit'] = display_unit
            
            # Show weather location
            if 'selected_camera' in st.session_state and st.session_state.selected_camera:
                if 'cameras' in st.session_state and st.session_state.selected_camera in st.session_state.cameras:
                    camera_config = st.session_state.cameras[st.session_state.selected_camera]
                    location = camera_config.get('weather_city', camera_config.get('location', 'Not Set'))
                    st.sidebar.info(f"Current location: {location}")
                else:
                    st.sidebar.warning("No camera selected")
                
            # API settings in expander
            with st.sidebar.expander("API Settings", expanded=False):
                # Weather API provider - this would be extended in real app
                provider = st.selectbox(
                    "Weather API Provider",
                    options=["OpenWeatherMap", "WeatherAPI", "AccuWeather"],
                    index=0,
                    help="Select weather data provider"
                )
                
                # API key input (not stored in this example)
                api_key = st.text_input(
                    "API Key", 
                    value="••••••••••••••••",
                    type="password",
                    help="Enter API key for the selected weather provider"
                )
                
                # Test API connection button
                if st.button("Test API Connection"):
                    # This would actually test the API in a real app
                    st.success("API connection successful!")
        else:
            st.sidebar.info("Weather data is disabled")
            
        return weather_settings

    @staticmethod
    def _create_performance_settings_section():
        """Create performance settings section for optimizing on different hardware"""
        st.subheader("Performance Settings")
        
        # Hardware capabilities section
        st.markdown("### Hardware Optimization")
        
        # Hardware profile selection
        hardware_profile = st.radio(
            "Select Hardware Profile",
            options=["Auto-detect", "High-end PC", "Mid-range PC", "Low-end PC/Raspberry Pi", "Server (headless)"],
            horizontal=True,
            help="Choose a profile that matches your system for optimal performance"
        )
        
        # CPU and Memory settings
        col1, col2 = st.columns(2)
        with col1:
            cpu_usage = st.slider(
                "CPU Usage Limit", 
                min_value=10, 
                max_value=100, 
                value=80, 
                step=5,
                help="Limit CPU usage to prevent system slowdowns"
            )
            
            st.checkbox(
                "Enable multithreading", 
                value=True,
                help="Enable parallel processing for faster analysis (uses more CPU)"
            )
        
        with col2:
            memory_limit = st.slider(
                "Memory Usage Limit (MB)", 
                min_value=100, 
                max_value=2000, 
                value=500, 
                step=100,
                help="Limit memory usage to prevent system slowdowns"
            )
            
            st.checkbox(
                "Enable frame buffer", 
                value=True,
                help="Buffer frames for smoother playback (uses more memory)"
            )
        
        # Network optimization
        st.markdown("### Network Optimization")
        
        # Network profile
        network_profile = st.radio(
            "Network Connection Type",
            options=["Auto-detect", "High-speed LAN", "Wi-Fi", "Cellular/Limited"],
            horizontal=True,
            help="Select your network type for optimal streaming settings"
        )
        
        # Stream quality settings
        stream_quality = st.select_slider(
            "Stream Quality",
            options=["Low (faster)", "Medium", "High (better quality)"],
            value="Medium",
            help="Lower quality requires less bandwidth and processing power"
        )
        
        # Frame rate and resolution
        col1, col2 = st.columns(2)
        with col1:
            frame_rate = st.slider(
                "Maximum Frame Rate", 
                min_value=1, 
                max_value=30, 
                value=15, 
                step=1,
                help="Higher values provide smoother video but use more resources"
            )
        
        with col2:
            resolution_options = ["320x240 (QVGA)", "640x480 (VGA)", "800x600 (SVGA)", 
                                  "1280x720 (HD)", "1920x1080 (Full HD)"]
            resolution = st.selectbox(
                "Maximum Resolution",
                options=resolution_options,
                index=3,  # Default to HD
                help="Higher resolution provides more detail but uses more resources"
            )
        
        # Advanced performance settings
        with st.expander("Advanced Performance Settings"):
            st.markdown("#### Processing Optimization")
            
            # Analytics processing interval
            analytics_interval = st.slider(
                "Analytics Processing Interval (seconds)", 
                min_value=1, 
                max_value=30, 
                value=5, 
                step=1,
                help="Longer intervals reduce CPU usage but update metrics less frequently"
            )
            
            # ROI processing settings
            roi_processing = st.radio(
                "ROI Processing Mode",
                options=["Process all frames", "Process every 2nd frame", "Process every 5th frame"],
                help="Reducing ROI processing frequency saves CPU but may miss short visibility events"
            )
            
            # Frame Processing Mode
            st.selectbox(
                "Frame Processing Mode",
                options=["Full frame", "Downsampled (faster)", "Adaptive"],
                help="Downsampling reduces CPU usage but may affect accuracy"
            )
            
            # Buffer sizes
            st.slider(
                "Frame Buffer Size", 
                min_value=1, 
                max_value=60, 
                value=10, 
                step=1,
                help="Larger buffer provides smoother playback but uses more memory"
            )
            
            # Enable/disable features
            col1, col2 = st.columns(2)
            with col1:
                st.checkbox("Enable motion detection", value=False)
                st.checkbox("Enable edge detection", value=True)
                st.checkbox("Enable color analysis", value=True)
            
            with col2:
                st.checkbox("Enable highlights generation", value=True)
                st.checkbox("Enable data logging", value=True)
                st.checkbox("Enable recording", value=True)
            
        # Apply settings button
        if st.button("Apply Performance Settings", use_container_width=True):
            st.success("Performance settings applied! System will adjust accordingly.")
            # Here we would actually apply these settings
        
        return {
            "hardware_profile": hardware_profile,
            "cpu_usage": cpu_usage,
            "memory_limit": memory_limit,
            "network_profile": network_profile,
            "stream_quality": stream_quality,
            "frame_rate": frame_rate,
            "resolution": resolution,
            "analytics_interval": analytics_interval
        }

    @staticmethod
    def create_performance_monitoring_tab(system_monitor):
        """Creates a tab for system performance monitoring"""
        st.header("⚙️ System Performance Monitoring")
        
        # Get current metrics
        current_metrics = system_monitor.get_current_metrics()
        
        # Current metrics display
        st.subheader("Current System Metrics")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "CPU Usage", 
                f"{current_metrics['cpu_usage']:.1f}%",
                delta=None,
                delta_color="inverse"
            )
            
            st.metric(
                "Active Cameras", 
                f"{current_metrics['camera_count']}",
                delta=None
            )
            
            st.metric(
                "Errors (24h)", 
                f"{current_metrics['error_count']}",
                delta=None,
                delta_color="inverse"
            )
            
        with col2:
            # Convert memory usage to GB for display
            memory_gb = current_metrics['memory_usage'] / 1024
            st.metric(
                "Memory Usage", 
                f"{memory_gb:.2f} GB",
                delta=None,
                delta_color="inverse"
            )
            
            st.metric(
                "Active ROIs", 
                f"{current_metrics['active_rois']}",
                delta=None
            )
            
            st.metric(
                "Connection Failures (24h)", 
                f"{current_metrics['connection_failures']}",
                delta=None,
                delta_color="inverse"
            )
            
        with col3:
            st.metric(
                "Disk Usage", 
                f"{current_metrics['disk_usage']:.1f}%",
                delta=None,
                delta_color="inverse"
            )
            
            st.metric(
                "Processing Time", 
                f"{current_metrics['processing_time']:.2f} ms",
                delta=None,
                delta_color="inverse"
            )
            
            st.metric(
                "Network Speed", 
                f"{current_metrics['network_speed']:.2f} Mbps",
                delta=None
            )
        
        # Display system info
        try:
            system_info = json.loads(current_metrics['system_info'])
            with st.expander("System Information"):
                info_cols = st.columns(2)
                
                with info_cols[0]:
                    st.markdown("**Hardware:**")
                    st.markdown(f"- CPU Cores: {system_info.get('cpu_count', 'N/A')}")
                    st.markdown(f"- Total Memory: {system_info.get('total_memory', 0):.2f} GB")
                    st.markdown(f"- Total Disk Space: {system_info.get('total_disk', 0):.2f} GB")
                    
                with info_cols[1]:
                    st.markdown("**Software:**")
                    st.markdown(f"- Hostname: {system_info.get('hostname', 'N/A')}")
                    st.markdown(f"- Platform: {system_info.get('platform', 'N/A')}")
                    st.markdown(f"- Python Version: {system_info.get('python_version', 'N/A')}")
                    
                    # Convert uptime to days, hours, minutes
                    uptime_seconds = system_info.get('uptime', 0)
                    days, remainder = divmod(uptime_seconds, 86400)
                    hours, remainder = divmod(remainder, 3600)
                    minutes, _ = divmod(remainder, 60)
                    st.markdown(f"- System Uptime: {int(days)}d {int(hours)}h {int(minutes)}m")
        except Exception as e:
            st.warning(f"Could not parse system information: {str(e)}")
        
        # Historical metrics
        st.subheader("Performance History")
        
        # Time period selection
        time_options = {
            "Last 6 Hours": 6,
            "Last 12 Hours": 12,
            "Last 24 Hours": 24,
            "Last 3 Days": 72,
            "Last 7 Days": 168
        }
        
        selected_period = st.selectbox(
            "Select Time Period",
            options=list(time_options.keys()),
            index=2  # Default to 24 hours
        )
        
        hours = time_options[selected_period]
        metrics_history = system_monitor.get_metrics_history(hours=hours)
        
        if not metrics_history:
            st.info("No performance history data available for the selected period.")
        else:
            # Convert to pandas DataFrame for easier plotting
            import pandas as pd
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            # Convert list of dictionaries to DataFrame
            df = pd.DataFrame(metrics_history)
            
            # Convert timestamp strings to datetime objects if needed
            if 'timestamp' in df.columns and isinstance(df['timestamp'][0], str):
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Create subplots
            fig = make_subplots(
                rows=3, cols=1,
                subplot_titles=("CPU & Memory Usage", "Processing Performance", "System Status"),
                shared_xaxes=True,
                vertical_spacing=0.1
            )
            
            # Plot CPU and Memory usage
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['cpu_usage'],
                    mode='lines',
                    name='CPU Usage (%)',
                    line=dict(color='#1f77b4')
                ),
                row=1, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['memory_usage'] / 1024,  # Convert to GB
                    mode='lines',
                    name='Memory Usage (GB)',
                    line=dict(color='#ff7f0e'),
                    yaxis='y2'
                ),
                row=1, col=1
            )
            
            # Processing performance
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['frames_processed'],
                    mode='lines+markers',
                    name='Frames Processed',
                    line=dict(color='#2ca02c')
                ),
                row=2, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['processing_time'],
                    mode='lines',
                    name='Processing Time (ms)',
                    line=dict(color='#d62728'),
                    yaxis='y3'
                ),
                row=2, col=1
            )
            
            # System status
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['camera_count'],
                    mode='lines+markers',
                    name='Active Cameras',
                    line=dict(color='#9467bd')
                ),
                row=3, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['error_count'],
                    mode='lines+markers',
                    name='Errors',
                    line=dict(color='#e377c2'),
                    yaxis='y4'
                ),
                row=3, col=1
            )
            
            # Update layout
            fig.update_layout(
                height=800,
                title_text="System Performance Metrics",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                yaxis=dict(title="CPU Usage (%)"),
                yaxis2=dict(
                    title="Memory (GB)",
                    overlaying="y",
                    side="right"
                ),
                yaxis3=dict(
                    title="Processing Time (ms)",
                    overlaying="y",
                    side="right"
                ),
                yaxis4=dict(
                    title="Error Count",
                    overlaying="y",
                    side="right"
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Raw data table
            with st.expander("View Raw Performance Data"):
                st.dataframe(df)

    @staticmethod
    def _create_database_settings_section(db_manager):
        """Create a section for database settings in the UI"""
        st.subheader("Database Settings")
        
        # Database info
        st.markdown("### Database Information")
        
        # Display database path
        st.markdown(f"**Database Path:** `{db_manager.db_path}`")
        
        # Database maintenance options
        st.markdown("### Database Maintenance")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Backup database
            if st.button("Create Database Backup", key="create_db_backup"):
                with st.spinner("Creating database backup..."):
                    success = db_manager.backup_database()
                    if success:
                        st.success("Database backup created successfully")
                    else:
                        st.error("Failed to create database backup")
        
        with col2:
            # Clean up old data
            retention_days = st.number_input(
                "Data Retention (days)", 
                min_value=1, 
                max_value=365, 
                value=30,
                help="Number of days to keep performance metrics data"
            )
            
            if st.button("Clean Up Old Data", key="cleanup_old_data"):
                with st.spinner("Cleaning up old data..."):
                    success = db_manager.cleanup_old_metrics(days_to_keep=retention_days)
                    if success:
                        st.success(f"Successfully cleaned up data older than {retention_days} days")
                    else:
                        st.error("Failed to clean up old data")
        
        # Database optimization
        st.markdown("### Database Optimization")
        
        # Connection pool settings
        pool_size = st.slider(
            "Connection Pool Size", 
            min_value=2, 
            max_value=20, 
            value=db_manager.max_connections,
            help="Maximum number of database connections to keep in the pool"
        )
        
        if st.button("Apply Database Settings", key="apply_db_settings"):
            # Update connection pool size
            if pool_size != db_manager.max_connections:
                db_manager.max_connections = pool_size
                st.success(f"Connection pool size updated to {pool_size}")
            
            # Run VACUUM to optimize database
            with st.spinner("Optimizing database..."):
                try:
                    conn = db_manager.get_connection()
                    conn.execute("VACUUM")
                    db_manager.release_connection(conn)
                    st.success("Database optimized successfully")
                except Exception as e:
                    st.error(f"Database optimization failed: {str(e)}")
        
        # Database statistics
        with st.expander("Database Statistics", expanded=False):
            try:
                conn = db_manager.get_connection()
                cursor = conn.cursor()
                
                # Get table statistics
                tables = ["visibility_metrics", "daily_stats", "weather_data", "events", "performance_metrics"]
                table_stats = {}
                
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    table_stats[table] = count
                
                # Display stats
                st.markdown("#### Table Row Counts")
                for table, count in table_stats.items():
                    st.markdown(f"- **{table}:** {count:,} rows")
                
                # Get database size
                cursor.execute("PRAGMA page_count")
                page_count = cursor.fetchone()[0]
                
                cursor.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]
                
                db_size_bytes = page_count * page_size
                db_size_mb = db_size_bytes / (1024 * 1024)
                
                st.markdown(f"**Database Size:** {db_size_mb:.2f} MB")
                
                # Get index information
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
                indexes = cursor.fetchall()
                
                st.markdown(f"**Number of Indexes:** {len(indexes)}")
                
                db_manager.release_connection(conn)
                
            except Exception as e:
                st.error(f"Failed to retrieve database statistics: {str(e)}")
                
        # Dangerous operations
        with st.expander("Dangerous Operations", expanded=False):
            st.warning("These operations can cause data loss. Use with caution!")
            
            if st.button("Reset Database", key="reset_database"):
                # Create an additional confirmation step
                st.warning("⚠️ This will delete all data in the database. Are you sure?")
                confirm_cols = st.columns([3, 1, 1])
                with confirm_cols[1]:
                    if st.button("Yes, Reset Database", key="confirm_reset"):
                        try:
                            # Close all connections
                            db_manager.cleanup()
                            
                            # Delete the database file
                            import os
                            if os.path.exists(db_manager.db_path):
                                os.remove(db_manager.db_path)
                                
                            # Recreate database schema
                            db_manager.setup_database()
                            
                            st.success("Database has been reset successfully")
                            st.info("Please restart the application for changes to take effect")
                        except Exception as e:
                            st.error(f"Failed to reset database: {str(e)}")
                with confirm_cols[2]:
                    if st.button("Cancel", key="cancel_reset"):
                        st.info("Database reset cancelled")

    @staticmethod
    def _create_performance_monitoring_settings_section():
        """Create performance monitoring settings section in the sidebar"""
        st.sidebar.subheader("Performance Settings")
        
        # Check if system monitor is initialized
        if 'system_monitor' not in st.session_state or st.session_state.system_monitor is None:
            st.sidebar.warning("System monitoring is not available")
            return
            
        # Enable/disable monitoring
        monitor_enabled = st.sidebar.checkbox(
            "Enable Performance Monitoring", 
            value=st.session_state.system_monitor.enabled,
            key="performance_monitoring_enabled"
        )
        
        # Update the system monitor if setting changed
        if monitor_enabled != st.session_state.system_monitor.enabled:
            st.session_state.system_monitor.enabled = monitor_enabled
            if monitor_enabled:
                st.session_state.system_monitor.start()
            else:
                st.session_state.system_monitor.stop()
                
        # Only show settings if monitoring is enabled
        if monitor_enabled:
            # Metrics collection interval
            metrics_interval = st.sidebar.slider(
                "Metrics Collection Interval (seconds)",
                min_value=10,
                max_value=300,
                value=st.session_state.system_monitor.metrics_interval,
                step=10,
                key="metrics_interval"
            )
            
            # Update interval if changed
            if metrics_interval != st.session_state.system_monitor.metrics_interval:
                st.session_state.system_monitor.metrics_interval = metrics_interval
                
            # Data retention period
            retention_period = st.sidebar.slider(
                "Data Retention Period (days)",
                min_value=1,
                max_value=30,
                value=st.session_state.system_monitor.retention_period,
                step=1,
                key="retention_period"
            )
            
            # Update retention period if changed
            if retention_period != st.session_state.system_monitor.retention_period:
                st.session_state.system_monitor.retention_period = retention_period

    @staticmethod
    def create_weather_tab(weather_data):
        """Create the weather insights tab"""
        st.header("🌦️ Weather Insights")
        
        if not weather_data:
            st.warning("No weather data available. Please check your weather API settings.")
            return
        
        # Display current weather conditions
        st.subheader("Current Weather Conditions")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            # Temperature
            st.metric(
                "Temperature", 
                f"{weather_data.get('temperature', 'N/A')}°C", 
                delta=weather_data.get('temp_change', None)
            )
            
            # Humidity
            st.metric(
                "Humidity", 
                f"{weather_data.get('humidity', 'N/A')}%"
            )
            
            # Pressure
            st.metric(
                "Pressure", 
                f"{weather_data.get('pressure', 'N/A')} hPa"
            )
        
        with col2:
            # Visibility
            st.metric(
                "Visibility", 
                f"{weather_data.get('visibility', 'N/A')} km"
            )
            
            # Wind speed
            st.metric(
                "Wind Speed", 
                f"{weather_data.get('wind_speed', 'N/A')} km/h",
                delta=weather_data.get('wind_change', None)
            )
            
            # Cloud coverage
            st.metric(
                "Cloud Coverage", 
                f"{weather_data.get('cloud_coverage', 'N/A')}%"
            )
        
        with col3:
            # Condition description
            st.markdown(f"**Condition:** {weather_data.get('condition', 'N/A')}")
            
            # Display weather icon if available
            icon_url = weather_data.get('icon_url')
            if icon_url:
                try:
                    # Use st.image with the URL directly
                    st.image(icon_url, width=100)
                except Exception as e:
                    st.markdown("### " + {
                        "Clear": "☀️",
                        "Clouds": "☁️",
                        "Rain": "🌧️",
                        "Snow": "❄️",
                        "Mist": "🌫️",
                        "Fog": "🌫️",
                        "Thunderstorm": "⛈️"
                    }.get(weather_data.get('condition', 'Unknown').split()[0], "🌤️"))
            else:
                # Placeholder icon using emoji
                st.markdown("### " + {
                    "Clear": "☀️",
                    "Clouds": "☁️",
                    "Rain": "🌧️",
                    "Drizzle": "🌦️",
                    "Thunderstorm": "⛈️",
                    "Snow": "❄️",
                    "Mist": "🌫️",
                    "Fog": "🌫️"
                }.get(weather_data.get('condition', ''), "🌡️"))
            
            # Last updated info
            st.caption(f"Last updated: {weather_data.get('last_updated', 'N/A')}")
            
            # Sunrise and sunset if available
            if 'sunrise' in weather_data and 'sunset' in weather_data:
                st.markdown(f"**Sunrise:** {weather_data['sunrise']} | **Sunset:** {weather_data['sunset']}")
        
        # Display historical weather data if available
        if 'historical' in weather_data and weather_data['historical']:
            st.subheader("Weather History")
            
            # Convert to DataFrame for chart
            hist_data = pd.DataFrame(weather_data['historical'])
            
            # Plot temperature history
            st.line_chart(hist_data.set_index('timestamp')['temperature'])
            
            # Show weather history table
            with st.expander("View Weather History Data"):
                st.dataframe(hist_data)
        
        # Weather and visibility correlation
        st.subheader("Weather Impact on Visibility")
        
        # This would be populated with actual data in the real app
        impact_data = {
            'Temperature': 'Medium impact - High temperatures can create heat haze',
            'Humidity': 'High impact - Higher humidity generally reduces visibility',
            'Precipitation': 'Very high impact - Rain and snow drastically reduce visibility',
            'Wind': 'Variable impact - Can clear fog but also bring dust and particles',
            'Fog/Mist': 'Extreme impact - Fog is the primary visibility reducer'
        }
        
        # Create a simple table to display impact
        for factor, impact in impact_data.items():
            st.markdown(f"**{factor}:** {impact}")
        
        # Weather-based recommendations
        st.subheader("Visibility Recommendations")
        
        condition = weather_data.get('condition', '').lower()
        
        if 'rain' in condition or 'drizzle' in condition:
            st.info("⚠️ Rain detected - Visibility may be reduced. Consider adjusting camera exposure settings.")
        elif 'fog' in condition or 'mist' in condition:
            st.warning("⚠️ Fog/Mist detected - Significant visibility reduction expected. IR mode may improve detection.")
        elif 'snow' in condition:
            st.warning("⚠️ Snow detected - Visibility and contrast may be affected. Verify camera enclosure is clear of snow.")
        elif 'clear' in condition:
            st.success("✅ Clear conditions - Optimal visibility expected.")
        
        # Future weather forecast
        if 'forecast' in weather_data and weather_data['forecast']:
            st.subheader("Weather Forecast")
            
            # Simple display of forecast data
            forecast_data = weather_data['forecast']
            
            # Display forecast as cards
            cols = st.columns(min(5, len(forecast_data)))
            
            for i, (col, forecast) in enumerate(zip(cols, forecast_data)):
                with col:
                    st.markdown(f"**{forecast.get('date', 'N/A')}**")
                    st.markdown(forecast.get('condition', 'N/A'))
                    st.markdown(f"{forecast.get('temp_min', 'N/A')}°C - {forecast.get('temp_max', 'N/A')}°C")
                    st.markdown(f"💧 {forecast.get('precipitation_chance', 'N/A')}%")
        
        # Allow user to customize location
        with st.expander("Change Weather Location"):
            # This would actually update the location in a real app
            location = st.text_input("Location", value=weather_data.get('city', 'Manila'))
            if st.button("Update Location", key="update_weather_location_btn"):
                st.success(f"Weather location updated to {location}")
                st.info("Please reload the page to see updated weather data")
                
        return

    @staticmethod
    def create_camera_grid_tab():
        """Create the camera grid tab for multi-camera view"""
        st.header("📹 Camera Grid")
        
        # Check if we have any cameras
        if 'camera_managers' not in st.session_state or not st.session_state.camera_managers:
            st.warning("No cameras available. Please add cameras in the settings.")
            return
        
        # Get available cameras
        cameras = list(st.session_state.camera_managers.keys())
        
        # Grid layout options
        st.subheader("Grid Layout")
        layout_options = ["Auto", "1x1", "2x2", "3x3", "4x4"]
        layout = st.selectbox(
            "Select Grid Layout",
            options=layout_options,
            index=0,
            help="Choose grid layout for camera views"
        )
        
        # Determine grid dimensions based on layout and camera count
        if layout == "Auto":
            cam_count = len(cameras)
            if cam_count <= 1:
                rows, cols = 1, 1
            elif cam_count <= 4:
                rows, cols = 2, 2
            elif cam_count <= 9:
                rows, cols = 3, 3
            else:
                rows, cols = 4, 4
        else:
            rows, cols = map(int, layout.split('x'))
        
        # Create grid of cameras
        st.subheader("Live Camera Grid")
        
        for r in range(rows):
            row_cols = st.columns(cols)
            for c in range(cols):
                idx = r * cols + c
                with row_cols[c]:
                    if idx < len(cameras):
                        cam_name = cameras[idx]
                        st.markdown(f"**{cam_name}**")
                        
                        # Get camera status info
                        camera_manager = st.session_state.camera_managers[cam_name]
                        status = camera_manager.get_status() if hasattr(camera_manager, 'get_status') else {}
                        
                        # Show status indicator
                        if status.get('connected', False):
                            st.success("Connected")
                            
                            # Display placeholder image or frame
                            # In an actual app, this would show a real camera frame
                            placeholder = st.empty()
                            placeholder.image(
                                "https://via.placeholder.com/640x480.png?text=Camera+Feed",
                                caption=f"Camera: {cam_name}",
                                use_column_width=True
                            )
                            
                            # Show summary metrics
                            metrics_col1, metrics_col2 = st.columns(2)
                            with metrics_col1:
                                st.metric("Visibility", f"{status.get('visibility_score', 'N/A')}%")
                            with metrics_col2:
                                st.metric("Status", status.get('visibility_status', 'Unknown'))
                        else:
                            st.error("Disconnected")
                            st.image(
                                "https://via.placeholder.com/640x480.png?text=Camera+Disconnected",
                                caption=f"Camera: {cam_name}",
                                use_column_width=True
                            )
                    else:
                        st.markdown("*Empty slot*")
        
        # Grid controls
        st.subheader("Grid Controls")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Refresh All", use_container_width=True, key="grid_refresh_all_btn"):
                st.rerun()
        
        with col2:
            if st.button("Reconnect All", use_container_width=True, key="grid_reconnect_all_btn"):
                # In a real app, this would try to reconnect all cameras
                st.info("Attempting to reconnect all cameras...")
                
        with col3:
            # Capture snapshot from all cameras
            if st.button("Capture Snapshots", use_container_width=True, key="grid_capture_all_btn"):
                # In a real app, this would capture snapshots from all cameras
                st.info("Capturing snapshots from all cameras...")
                
        # Allow saving grid layout as a preset
        with st.expander("Save Grid Layout"):
            preset_name = st.text_input("Preset Name", "Default Grid")
            
            if st.button("Save Preset", key="save_grid_preset_btn"):
                # In a real app, this would save the grid layout to a preset
                st.success(f"Grid layout saved as '{preset_name}'")
    
    @staticmethod
    def create_dashboard_overview():
        """Create the dashboard overview tab with overall system status"""
        st.header("📋 Dashboard Overview")
        
        # Check if we have system monitor data
        if 'system_monitor' not in st.session_state or not st.session_state.system_monitor:
            st.warning("System monitoring is not available. Please check your configuration.")
            return
        
        # Get system metrics
        system_metrics = st.session_state.system_monitor.get_current_metrics()
        
        # System status card
        st.subheader("System Status")
        
        # Health status based on metrics
        system_health = "Good"
        system_health_color = "green"
        
        if system_metrics.get('cpu_usage', 0) > 80 or system_metrics.get('memory_usage', 0) > 80:
            system_health = "Warning"
            system_health_color = "orange"
            
        if system_metrics.get('error_count', 0) > 10 or system_metrics.get('connection_failures', 0) > 5:
            system_health = "Critical"
            system_health_color = "red"
        
        # Display health status
        st.markdown(f"<h3 style='color: {system_health_color};'>Health: {system_health}</h3>", unsafe_allow_html=True)
        
        # System metrics summary
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("CPU Usage", f"{system_metrics.get('cpu_usage', 0):.1f}%")
            st.metric("Memory Usage", f"{system_metrics.get('memory_usage', 0) / 1024:.2f} GB")
            
        with col2:
            st.metric("Active Cameras", f"{system_metrics.get('camera_count', 0)}")
            st.metric("Active ROIs", f"{system_metrics.get('active_rois', 0)}")
            
        with col3:
            st.metric("Disk Usage", f"{system_metrics.get('disk_usage', 0):.1f}%")
            st.metric("Uptime", system_metrics.get('uptime_str', 'N/A'))
        
        # Camera status summary
        st.subheader("Camera Status Summary")
        
        if 'camera_managers' in st.session_state and st.session_state.camera_managers:
            # Create status dataframe
            camera_data = []
            
            for cam_name, manager in st.session_state.camera_managers.items():
                status = manager.get_status() if hasattr(manager, 'get_status') else {}
                camera_data.append({
                    'Camera': cam_name,
                    'Status': 'Connected' if status.get('connected', False) else 'Disconnected',
                    'Visibility': f"{status.get('visibility_score', 0):.1f}%",
                    'Condition': status.get('visibility_status', 'Unknown'),
                    'Last Updated': status.get('last_update', 'N/A')
                })
            
            # Display as dataframe
            if camera_data:
                df = pd.DataFrame(camera_data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No camera data available")
        else:
            st.info("No cameras configured")
            
        # Recent events
        st.subheader("Recent Events")
        
        # Placeholder for recent events - in a real app would be fetched from database
        events = [
            {"timestamp": "2023-04-30 14:23:45", "camera": "Front Gate", "type": "Visibility Decrease", "details": "Visibility dropped to 45%"},
            {"timestamp": "2023-04-30 12:15:30", "camera": "Back Yard", "type": "Camera Disconnected", "details": "Connection lost"},
            {"timestamp": "2023-04-30 10:05:12", "camera": "Driveway", "type": "Visibility Increase", "details": "Visibility improved to 92%"},
            {"timestamp": "2023-04-30 08:45:22", "camera": "Front Gate", "type": "Weather Change", "details": "Rain detected"}
        ]
        
        if events:
            # Display events as dataframe
            events_df = pd.DataFrame(events)
            st.dataframe(events_df, use_container_width=True)
        else:
            st.info("No recent events")
        
        # Quick actions
        st.subheader("Quick Actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 Download Report", use_container_width=True, key="download_report_btn"):
                # In a real app, this would generate and download a system report
                st.success("Generating system report...")
                
        with col2:
            if st.button("🔁 Restart Services", use_container_width=True, key="restart_services_btn"):
                # In a real app, this would restart system services
                st.info("Restarting system services...")
                
        with col3:
            if st.button("🧹 Clear Alerts", use_container_width=True, key="clear_alerts_btn"):
                # In a real app, this would clear system alerts
                st.success("All alerts cleared")
        
        # System alerts
        st.subheader("Active Alerts")
        
        # Placeholder for system alerts - in a real app would be fetched from database
        alerts = [
            {"severity": "High", "message": "Camera 'Back Yard' disconnected for more than 30 minutes", "time": "14:45:22"},
            {"severity": "Medium", "message": "Disk usage above 70%", "time": "13:30:15"}
        ]
        
        if alerts:
            for alert in alerts:
                if alert["severity"] == "High":
                    st.error(f"{alert['time']} - {alert['message']}")
                elif alert["severity"] == "Medium":
                    st.warning(f"{alert['time']} - {alert['message']}")
                else:
                    st.info(f"{alert['time']} - {alert['message']}")
        else:
            st.success("No active alerts")
        
        # Allow refreshing the dashboard
        if st.button("Refresh Dashboard", key="refresh_dashboard_btn"):
            st.rerun()

    @staticmethod
    def create_recordings_tab(camera_manager):
        """Create the recordings tab for viewing and managing recordings"""
        st.header("📼 Camera Recordings")
        
        # Check if camera manager is available
        if camera_manager is None:
            st.warning("No camera is currently selected. Please select a camera to view recordings.")
            return
        
        # Get recordings path - in real app would come from the camera manager
        # Use camera ID as fallback if get_name is not available
        camera_name = camera_manager.camera_id if hasattr(camera_manager, 'camera_id') else "camera"
        try:
            if hasattr(camera_manager, 'get_name'):
                camera_name = camera_manager.get_name()
        except Exception as e:
            st.warning(f"Could not get camera name: {str(e)}")
            
        recordings_path = os.path.join(RECORDINGS_DIR, camera_name)
        
        # Create directory if not exists
        os.makedirs(recordings_path, exist_ok=True)
        
        # Recording settings
        st.subheader("Recording Settings")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Enable/disable recording
            recording_enabled = st.checkbox(
                "Enable Recording",
                value=getattr(camera_manager, 'recording_enabled', True),
                help="Enable automatic recording"
            )
            
            # Update camera manager if changed
            if hasattr(camera_manager, 'recording_enabled') and recording_enabled != camera_manager.recording_enabled:
                camera_manager.recording_enabled = recording_enabled
                
            # Recording format
            recording_format = st.selectbox(
                "Recording Format",
                options=["MP4", "AVI", "MKV"],
                index=0,
                help="Video format for recordings"
            )
        
        with col2:
            # Recording quality
            recording_quality = st.select_slider(
                "Recording Quality",
                options=["Low", "Medium", "High"],
                value="Medium",
                help="Higher quality uses more disk space"
            )
            
            # Recording duration
            recording_duration = st.slider(
                "Max Recording Duration (minutes)",
                min_value=1,
                max_value=60,
                value=10,
                help="Maximum duration for each recording file"
            )
        
        # Manual recording controls
        st.subheader("Manual Recording Controls")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Start Recording", use_container_width=True, key="rec_start_btn"):
                # In a real app, this would start recording
                st.success("Recording started")
        
        with col2:
            if st.button("Stop Recording", use_container_width=True, key="rec_stop_btn"):
                # In a real app, this would stop recording
                st.info("Recording stopped")
        
        with col3:
            if st.button("Take Snapshot", use_container_width=True, key="rec_snapshot_btn"):
                # In a real app, this would capture a screenshot
                st.success("Snapshot saved")
        
        # List recordings
        st.subheader("Recorded Videos")
        
        # Get list of recordings (in real app would come from camera manager)
        recordings = []
        
        # Check if directory exists and list files
        if os.path.exists(recordings_path):
            for file in os.listdir(recordings_path):
                if file.endswith(('.mp4', '.avi', '.mkv')):
                    file_path = os.path.join(recordings_path, file)
                    # Get file stats
                    stats = os.stat(file_path)
                    # Create recording entry
                    recordings.append({
                        'filename': file,
                        'path': file_path,
                        'date': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'size': f"{stats.st_size / (1024 * 1024):.2f} MB",
                        'duration': '10:00'  # In a real app, this would be extracted from the video
                    })
        
        # Sort recordings by date (newest first)
        recordings.sort(key=lambda x: x['date'], reverse=True)
        
        if recordings:
            # Create a table of recordings
            recordings_df = pd.DataFrame(recordings)
            st.dataframe(recordings_df[['filename', 'date', 'size', 'duration']], use_container_width=True)
            
            # Select recording to play
            selected_recording = st.selectbox(
                "Select Recording to Play",
                options=[rec['filename'] for rec in recordings],
                index=0
            )
            
            # Get selected recording details
            selected_rec = next((rec for rec in recordings if rec['filename'] == selected_recording), None)
            
            if selected_rec:
                # Recording details
                st.markdown(f"**Date:** {selected_rec['date']} | **Size:** {selected_rec['size']} | **Duration:** {selected_rec['duration']}")
                
                # In real app, this would play the video
                st.video(selected_rec['path'])
                
                # Recording actions
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("Download Recording", key="rec_download_btn"):
                        # In real app, this would download the video
                        st.success(f"Downloading {selected_rec['filename']}...")
                
                with col2:
                    if st.button("Delete Recording", key="rec_delete_btn"):
                        # In real app, this would delete the video
                        st.error(f"Deleted {selected_rec['filename']}")
        else:
            st.info("No recordings found for this camera")
    
    @staticmethod
    def create_highlights_tab(camera_manager):
        """Create the highlights tab for viewing important events"""
        st.header("🔍 Highlights & Events")
        
        # Check if camera manager is available
        if camera_manager is None:
            st.warning("No camera is currently selected. Please select a camera to view highlights.")
            return
        
        # Get highlights path - in real app would come from the camera manager
        # Use camera ID as fallback if get_name is not available
        camera_name = camera_manager.camera_id if hasattr(camera_manager, 'camera_id') else "camera"
        try:
            if hasattr(camera_manager, 'get_name'):
                camera_name = camera_manager.get_name()
        except Exception as e:
            st.warning(f"Could not get camera name: {str(e)}")
            
        highlights_path = os.path.join(HIGHLIGHTS_DIR, camera_name)
        
        # Create directory if not exists
        os.makedirs(highlights_path, exist_ok=True)
        
        # Highlight settings
        st.subheader("Highlight Settings")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Enable/disable highlights
            highlights_enabled = st.checkbox(
                "Enable Automatic Highlights",
                value=getattr(camera_manager, 'highlights_enabled', True),
                help="Automatically save events when visibility changes significantly"
            )
            
            # Update camera manager if changed
            if hasattr(camera_manager, 'highlights_enabled') and highlights_enabled != camera_manager.highlights_enabled:
                camera_manager.highlights_enabled = highlights_enabled
                
            # Highlight sensitivity
            highlight_sensitivity = st.slider(
                "Highlight Sensitivity",
                min_value=1,
                max_value=10,
                value=5,
                help="Higher sensitivity creates more highlights"
            )
        
        with col2:
            # Visibility threshold for highlights
            visibility_threshold = st.slider(
                "Visibility Change Threshold (%)",
                min_value=5,
                max_value=50,
                value=20,
                help="Minimum visibility change to create a highlight"
            )
            
            # Retention period
            retention_period = st.slider(
                "Retention Period (days)",
                min_value=1,
                max_value=90,
                value=30,
                help="How long to keep highlights before auto-deletion"
            )
        
        # Filter options
        st.subheader("Filter Highlights")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Date range filter
            start_date = st.date_input(
                "Start Date",
                value=datetime.now().date() - timedelta(days=7),
                key="highlights_start_date"  # Add unique key
            )
        
        with col2:
            end_date = st.date_input(
                "End Date",
                value=datetime.now().date(),
                key="highlights_end_date"  # Add unique key
            )
        
        with col3:
            # Event type filter
            event_type = st.selectbox(
                "Event Type",
                options=["All Events", "Visibility Decrease", "Visibility Increase", "Weather Change"]
            )
        
        # List highlights
        st.subheader("Highlight Events")
        
        # In a real app, these would be loaded from storage or database
        # Mock data for demonstration
        highlights = [
            {
                'id': '1',
                'date': '2023-04-30 14:23:45',
                'type': 'Visibility Decrease',
                'description': 'Visibility dropped from 85% to 45%',
                'duration': '00:30',
                'thumbnail': 'https://via.placeholder.com/320x240.png?text=Visibility+Decrease',
                'video_path': ''
            },
            {
                'id': '2',
                'date': '2023-04-29 12:15:30',
                'type': 'Weather Change',
                'description': 'Rain detected, visibility affected',
                'duration': '00:45',
                'thumbnail': 'https://via.placeholder.com/320x240.png?text=Weather+Change',
                'video_path': ''
            },
            {
                'id': '3',
                'date': '2023-04-28 10:05:12',
                'type': 'Visibility Increase',
                'description': 'Visibility improved from 40% to 92%',
                'duration': '00:20',
                'thumbnail': 'https://via.placeholder.com/320x240.png?text=Visibility+Increase',
                'video_path': ''
            }
        ]
        
        # Apply filters
        if event_type != "All Events":
            highlights = [h for h in highlights if h['type'] == event_type]
            
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        highlights = [h for h in highlights if start_datetime <= datetime.strptime(h['date'], '%Y-%m-%d %H:%M:%S') <= end_datetime]
        
        if highlights:
            # Display highlights as a grid
            for i in range(0, len(highlights), 3):
                row_highlights = highlights[i:i+3]
                cols = st.columns(len(row_highlights))
                
                for j, (col, highlight) in enumerate(zip(cols, row_highlights)):
                    with col:
                        st.image(highlight['thumbnail'], use_column_width=True)
                        st.markdown(f"**{highlight['type']}**")
                        st.caption(highlight['date'])
                        st.markdown(highlight['description'])
                        
                        # In a real app, this would play the video
                        if st.button("View", key=f"view_{highlight['id']}"):
                            st.session_state.selected_highlight = highlight
            
            # Display selected highlight details
            if 'selected_highlight' in st.session_state and st.session_state.selected_highlight:
                highlight = st.session_state.selected_highlight
                
                st.subheader(f"Highlight: {highlight['type']}")
                st.markdown(f"**Date:** {highlight['date']} | **Duration:** {highlight['duration']}")
                st.markdown(highlight['description'])
                
                # In a real app, this would play the video
                # Using image placeholder for demo
                st.image(highlight['thumbnail'], use_column_width=True)
                
                # Actions
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("Download Highlight", key="highlight_download_btn"):
                        # In a real app, this would download the video
                        st.success(f"Downloading highlight from {highlight['date']}...")
                
                with col2:
                    if st.button("Delete Highlight", key="highlight_delete_btn"):
                        # In a real app, this would delete the highlight
                        st.error(f"Deleted highlight from {highlight['date']}")
                        if 'selected_highlight' in st.session_state:
                            del st.session_state.selected_highlight
        else:
            st.info("No highlights found matching the current filters")

    @staticmethod
    def create_historical_tab(camera_manager):
        """Create the historical data tab for viewing past metrics"""
        st.header("📆 Historical Data Analysis")
        
        # Check if camera manager is available
        if camera_manager is None:
            st.warning("No camera is currently selected. Please select a camera to view historical data.")
            return
        
        # Time period selection
        st.subheader("Select Time Period")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Date range
            start_date = st.date_input(
                "Start Date",
                value=datetime.now().date() - timedelta(days=7),
                key="historical_start_date"  # Add unique key
            )
        
        with col2:
            end_date = st.date_input(
                "End Date",
                value=datetime.now().date(),
                key="historical_end_date"  # Add unique key
            )
        
        with col3:
            # Aggregation interval
            interval = st.selectbox(
                "Interval",
                options=["Hourly", "Daily", "Weekly"],
                index=1
            )
        
        # Metric selection
        st.subheader("Select Metrics")
        
        metric_options = ["Visibility Score", "Brightness", "Contrast", "Edge Score", "Weather Correlation"]
        selected_metrics = st.multiselect(
            "Metrics to Display",
            options=metric_options,
            default=["Visibility Score"]
        )
        
        # Generate mock historical data
        # In a real app, this would come from the database
        
        # Generate date range
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            if interval == "Hourly":
                for hour in range(0, 24, 2):  # Every 2 hours
                    date_range.append(datetime.combine(current_date, datetime.min.time()) + timedelta(hours=hour))
            elif interval == "Daily":
                date_range.append(datetime.combine(current_date, datetime.min.time()))
            elif interval == "Weekly":
                if current_date.weekday() == 0:  # Monday
                    date_range.append(datetime.combine(current_date, datetime.min.time()))
            current_date += timedelta(days=1)
        
        # Generate data
        import random
        data = []
        
        base_visibility = 80
        base_brightness = 150
        base_contrast = 60
        base_edge = 70
        
        for date in date_range:
            # Add some randomness and trends
            time_factor = (date - datetime.combine(start_date, datetime.min.time())).total_seconds() / (24 * 3600)
            daily_cycle = np.sin(time_factor * np.pi / 12) * 20  # Daily cycle
            
            # Create some events
            if random.random() < 0.1:  # 10% chance of event
                event_impact = -40 if random.random() < 0.7 else 20  # More likely to be negative events
            else:
                event_impact = 0
                
            visibility = max(0, min(100, base_visibility + daily_cycle + event_impact + random.uniform(-10, 10)))
            brightness = max(0, min(255, base_brightness + daily_cycle + event_impact + random.uniform(-20, 20)))
            contrast = max(0, min(100, base_contrast + daily_cycle/3 + event_impact/2 + random.uniform(-5, 5)))
            edge = max(0, min(100, base_edge + daily_cycle/3 + event_impact/2 + random.uniform(-10, 10)))
            
            # Weather correlation is stronger during events
            weather_corr = abs(event_impact) / 20 + random.uniform(0, 0.7)
            
            data.append({
                'timestamp': date,
                'visibility': visibility,
                'brightness': brightness,
                'contrast': contrast,
                'edge': edge,
                'weather_correlation': min(1.0, weather_corr)
            })
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Display data
        if not df.empty and selected_metrics:
            st.subheader("Historical Trends")
            
            # Mapping of selected metrics to DataFrame columns
            metric_map = {
                "Visibility Score": "visibility",
                "Brightness": "brightness",
                "Contrast": "contrast",
                "Edge Score": "edge",
                "Weather Correlation": "weather_correlation"
            }
            
            # Create plot
            fig = go.Figure()
            
            for metric in selected_metrics:
                if metric in metric_map:
                    column = metric_map[metric]
                    fig.add_trace(go.Scatter(
                        x=df['timestamp'],
                        y=df[column],
                        mode='lines+markers',
                        name=metric
                    ))
            
            # Update layout
            fig.update_layout(
                title="Historical Metrics",
                xaxis_title="Date",
                yaxis_title="Value",
                height=500,
                hovermode="x unified"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Summary statistics
            st.subheader("Summary Statistics")
            
            summary_data = []
            for metric in selected_metrics:
                if metric in metric_map:
                    column = metric_map[metric]
                    summary_data.append({
                        'Metric': metric,
                        'Average': f"{df[column].mean():.2f}",
                        'Minimum': f"{df[column].min():.2f}",
                        'Maximum': f"{df[column].max():.2f}",
                        'Standard Deviation': f"{df[column].std():.2f}"
                    })
            
            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df, use_container_width=True)
            
            # Raw data view
            with st.expander("View Raw Data"):
                display_df = df.copy()
                display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                
                # Select only requested columns
                display_columns = ['timestamp'] + [metric_map[m] for m in selected_metrics if m in metric_map]
                st.dataframe(display_df[display_columns], use_container_width=True)
            
            # Export options
            st.subheader("Export Data")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Export to CSV", key="historical_export_csv_btn"):
                    # In a real app, this would download a CSV file
                    st.success("Exporting data to CSV...")
            
            with col2:
                if st.button("Generate Report", key="historical_generate_report_btn"):
                    # In a real app, this would generate a PDF report
                    st.success("Generating comprehensive report...")
        else:
            st.info("Please select at least one metric to display")