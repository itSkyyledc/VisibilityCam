import cv2
import time
import numpy as np
import streamlit as st
import requests
import datetime
import os
import logging
from datetime import timedelta
import plotly.graph_objects as go
import pandas as pd
import json
import sqlite3
import traceback
import shutil
from pathlib import Path
from src.config import DEFAULT_CAMERA_CONFIG, DEFAULT_DISPLAY_SETTINGS

# Configure logging to console and file
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(f"logs/camdashboard_{datetime.datetime.now().strftime('%Y-%m-%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CamDashboard")

# Page configuration
st.set_page_config(
    page_title="Camera Surveillance Dashboard",
    page_icon="📹",
    layout="wide"
)

# Initialize theme in session state
if 'theme' not in st.session_state:
    st.session_state.theme = "light"

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        margin-bottom: 1rem;
        color: #1E88E5;
        text-align: center;
    }
    .sub-header {
        font-size: 1.5rem;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        color: #0D47A1;
    }
    .card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 20px;
    }
    .indicator {
        font-size: 1.2rem;
        font-weight: bold;
        display: inline-block;
        padding: 5px 10px;
        border-radius: 5px;
    }
    .good-visibility {
        background-color: #c8e6c9;
        color: #2e7d32;
    }
    .poor-visibility {
        background-color: #ffcdd2;
        color: #c62828;
    }
    .weather-icon {
        font-size: 2rem;
        margin-right: 10px;
    }
    .camera-selector {
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Apply theme-specific CSS based on current theme
if st.session_state.theme == "dark":
    st.markdown("""
    <style>
        .main-header { color: #64B5F6; }
        .sub-header { color: #90CAF9; }
        .card { 
            background-color: #263238; 
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        .stApp {
            background-color: #121212;
            color: #E0E0E0;
        }
        .stButton button {
            background-color: #1E88E5;
            color: white;
        }
        .stTextInput input, .stNumberInput input, .stSelectbox, .stMultiselect {
            background-color: #333;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
        .stApp {
            background-color: #FFFFFF;
            color: #212121;
        }
        .stButton button {
            background-color: #1E88E5;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

# Configuration variables
# JSON-based camera configuration for better scalability
CAMERAS = {
    "Manila_Observatory": {
        "name": "Manila Observatory",
        "rtsp_url": "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1",
        "location": "Manila Observatory",
        "weather_city": "Quezon City",
        "visibility_threshold": 80,
        "recovery_threshold": 100
    },
    "AIC": {
        "name": "AIC",
        "rtsp_url": "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1",  # Replace with actual URL
        "location": "AIC",
        "weather_city": "Baguio City",
        "visibility_threshold": 80,
        "recovery_threshold": 100
    },
    # Add more cameras as needed
}

FRAME_WIDTH, FRAME_HEIGHT = 1280, 720
DEFAULT_VISIBILITY_THRESHOLD = 80
DEFAULT_RECOVERY_THRESHOLD = 100

# File paths setup
os.makedirs("recordings", exist_ok=True)
os.makedirs("highlights", exist_ok=True)

# Create camera-specific directories
for camera_id in CAMERAS:
    os.makedirs(f"recordings/{camera_id}", exist_ok=True)
    os.makedirs(f"highlights/{camera_id}", exist_ok=True)

today_date = datetime.datetime.now().strftime("%Y-%m-%d")

# Load API key securely
try:
    with open('api_key.txt', 'r') as file:
        API_KEY = file.read().strip()
except FileNotFoundError:
    logger.warning("⚠️ API key file not found. Weather data will not be available.")
    API_KEY = None

# Session state initialization
if 'current_camera' not in st.session_state:
    st.session_state.current_camera = list(CAMERAS.keys())[0]  # Default to first camera

if 'cameras_data' not in st.session_state:
    # Initialize data structure for all cameras
    st.session_state.cameras_data = {}
    
    for camera_id in CAMERAS:
        st.session_state.cameras_data[camera_id] = {
            "brightness_history": [],
            "timestamps": [],
            "highlight_marker": [],
            "poor_visibility_start": None,
            "last_highlight_time": time.time() - 60,  # Initialize with timestamp 60 seconds ago
            "reconnect_count": 0,
            "corrupted_frames_count": 0,
            "visibility_threshold": CAMERAS[camera_id]["visibility_threshold"],
            "daily_stats": {
                "min_brightness": float('inf'),
                "max_brightness": 0,
                "avg_brightness": 0,
                "total_samples": 0,
                "visibility_duration": 0,  # Duration in seconds of poor visibility
                "max_visibility_duration": 0,  # Maximum continuous poor visibility
                "reconnect_count": 0,
                "corruption_count": 0,
                "uptime_percentage": 100.0,
                "additional_metrics": {
                    "motion_detected": False,
                    "motion_count": 0,
                    "bandwidth_usage": 0,
                    "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            },
            "weather_data": None,
            "last_weather_update": datetime.datetime.now() - datetime.timedelta(hours=1)  # Force initial update
        }

if 'data_update_counter' not in st.session_state:
    st.session_state.data_update_counter = 0
if 'last_plot_update_time' not in st.session_state:
    st.session_state.last_plot_update_time = datetime.datetime.now()
if 'plot_timeframe' not in st.session_state:
    st.session_state.plot_timeframe = "1 minute"
if 'plot_update_interval' not in st.session_state:
    st.session_state.plot_update_interval = 5  # Update plot every 5 data points
if 'last_session_save' not in st.session_state:
    st.session_state.last_session_save = datetime.datetime.now()
if 'last_frame_time' not in st.session_state:
    st.session_state.last_frame_time = datetime.datetime.now()
if 'frame_count' not in st.session_state:
    st.session_state.frame_count = 0
if 'camera_settings_changed' not in st.session_state:
    st.session_state.camera_settings_changed = False
if 'display_settings' not in st.session_state:
    st.session_state.display_settings = {
        'refresh_rate': 0.5,
        'auto_refresh': True,
        'display_mode': "Standard",
        'show_fps': True,
        'rtsp_transport': "tcp"
    }

def load_session_state():
    """Initialize session state variables"""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = False
    
    if not st.session_state.initialized:
        # Setup database
        setup_database()
        
        # Initialize camera selection
        if 'current_camera' not in st.session_state:
            st.session_state.current_camera = list(DEFAULT_CAMERA_CONFIG.keys())[0]
        
        # Initialize display settings
        for key, value in DEFAULT_DISPLAY_SETTINGS.items():
            if key not in st.session_state:
                st.session_state[key] = value
        
        # Initialize UI components
        if 'visibility_status' not in st.session_state:
            st.session_state.visibility_status = "Good"
        if 'recording_status' not in st.session_state:
            st.session_state.recording_status = "Not Recording"
        if 'current_brightness' not in st.session_state:
            st.session_state.current_brightness = 0.0
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = ""
        if 'reconnect_counter' not in st.session_state:
            st.session_state.reconnect_counter = 0
        if 'show_debug_info' not in st.session_state:
            st.session_state.show_debug_info = False
        if 'brightness_chart' not in st.session_state:
            st.session_state.brightness_chart = None
        if 'alerts_container' not in st.session_state:
            st.session_state.alerts_container = []
        
        # Initialize camera data
        if 'cameras_data' not in st.session_state:
            st.session_state.cameras_data = {}
            for camera_id in DEFAULT_CAMERA_CONFIG:
                st.session_state.cameras_data[camera_id] = {
                    "brightness_history": [],
                    "timestamps": [],
                    "highlight_marker": [],
                    "poor_visibility_start": None,
                    "last_highlight_time": time.time() - 60,
                    "reconnect_count": 0,
                    "corrupted_frames_count": 0,
                    "visibility_threshold": DEFAULT_CAMERA_CONFIG[camera_id]["visibility_threshold"],
                    "daily_stats": {
                        "min_brightness": float('inf'),
                        "max_brightness": 0,
                        "avg_brightness": 0,
                        "total_samples": 0,
                        "visibility_duration": 0,
                        "max_visibility_duration": 0,
                        "reconnect_count": 0,
                        "corruption_count": 0,
                        "uptime_percentage": 100.0
                    }
                }
        
        # Initialize additional state variables
        if 'data_update_counter' not in st.session_state:
            st.session_state.data_update_counter = 0
        if 'last_plot_update_time' not in st.session_state:
            st.session_state.last_plot_update_time = time.time()
        if 'plot_timeframe' not in st.session_state:
            st.session_state.plot_timeframe = "1h"
        if 'plot_update_interval' not in st.session_state:
            st.session_state.plot_update_interval = 60
        if 'last_session_save' not in st.session_state:
            st.session_state.last_session_save = time.time()
        if 'last_frame_time' not in st.session_state:
            st.session_state.last_frame_time = time.time()
        if 'frame_count' not in st.session_state:
            st.session_state.frame_count = 0
        if 'camera_settings_changed' not in st.session_state:
            st.session_state.camera_settings_changed = False
        
        st.session_state.initialized = True

# Try to load saved session state
load_session_state()

def get_weather(city):
    """Fetch weather data from OpenWeatherMap API for a specific city and save to database."""
    if not API_KEY:
        return {
            "temperature": "N/A", 
            "humidity": "N/A", 
            "condition": "API key missing", 
            "icon": "❓",
            "wind_speed": "N/A",
            "pressure": "N/A",
            "visibility": "N/A",
            "sunrise": "N/A",
            "sunset": "N/A",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    try:
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
        response = requests.get(weather_url, timeout=5)
        data = response.json()
        
        # Map weather condition to emoji
        condition = data["weather"][0]["main"].lower()
        icon = "☀️"  # Default sunny
        if "cloud" in condition:
            icon = "☁️"
        elif "rain" in condition:
            icon = "🌧️"
        elif "snow" in condition:
            icon = "❄️"
        elif "fog" in condition or "mist" in condition:
            icon = "🌫️"
        elif "thunder" in condition:
            icon = "⛈️"
        
        weather = {
            "temperature": round(data["main"]["temp"], 1),
            "humidity": data["main"]["humidity"],
            "condition": data["weather"][0]["description"].capitalize(),
            "icon": icon,
            "wind_speed": round(data["wind"]["speed"], 1),
            "pressure": data["main"]["pressure"],
            "visibility": data.get("visibility", "N/A"),
            "sunrise": datetime.datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M"),
            "sunset": datetime.datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%H:%M"),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Save weather data to database (every 30 minutes to avoid too much data)
        current_hour = datetime.datetime.now().hour
        current_minute = datetime.datetime.now().minute
        if current_minute % 30 == 0:
            save_weather_data(city, weather)
            
    except Exception as e:
        logger.warning(f"Weather API error for {city}: {str(e)}")
        weather = {
            "temperature": "N/A", 
            "humidity": "N/A", 
            "condition": "Error fetching weather", 
            "icon": "❓",
            "wind_speed": "N/A",
            "pressure": "N/A",
            "visibility": "N/A",
            "sunrise": "N/A",
            "sunset": "N/A",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    return weather

def analyze_visibility(frame, std_threshold=10, hist_threshold=100):
    """Calculate the brightness of the frame and detect corruption."""
    # Check if frame is already grayscale
    if len(frame.shape) == 2:
        gray = frame
    else:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Calculate brightness
    brightness = np.mean(gray)
    
    # Detect corruption by analyzing frame quality
    # 1. Check for uniform areas (corrupted frames often have large uniform areas)
    std_dev = np.std(gray)
    
    # 2. Check for abnormal pixel distribution
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_std = np.std(hist)
    
    # Corrupted frames often have very low standard deviation or abnormal histogram
    is_corrupted = (std_dev < std_threshold) or (hist_std < hist_threshold)
    
    return brightness, is_corrupted

def create_highlight(camera_id, start_time, duration=10):
    """Create a highlight clip from the main recording for a specific camera."""
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    highlight_filename = f"highlights/{camera_id}/highlight_{today_date}_{datetime.datetime.now().strftime('%H-%M-%S')}.mp4"
    
    # Add to the camera's highlight markers
    st.session_state.cameras_data[camera_id]["highlight_marker"].append(datetime.datetime.now().strftime("%H:%M:%S"))
    
    # Log the highlight creation in the session state
    st.session_state.cameras_data[camera_id]["last_highlight_time"] = time.time()
    
    # Log highlight event to database
    log_highlight_event(camera_id, start_time, highlight_filename)
    
    return highlight_filename

def resample_brightness_data(camera_id, timeframe):
    """Resample brightness data based on selected timeframe for a specific camera."""
    camera_data = st.session_state.cameras_data[camera_id]
    
    if not camera_data["timestamps"] or not camera_data["brightness_history"]:
        return [], []
    
    # Create DataFrame from session state data
    df = pd.DataFrame({
        'timestamp': camera_data["timestamps"],
        'brightness': camera_data["brightness_history"]
    })
    
    # Set timestamp as index
    df.set_index('timestamp', inplace=True)
    
    # Determine resampling frequency based on timeframe
    if timeframe == "5 seconds":
        rule = '5s'
    elif timeframe == "1 minute":
        rule = '1Min'
    elif timeframe == "5 minutes":
        rule = '5Min'
    elif timeframe == "1 hour":
        rule = '1H'
    elif timeframe == "12 hours":
        rule = '12H'
    elif timeframe == "1 day":
        rule = '1D'
    elif timeframe == "1 week":
        rule = '1W'
    else:  # "1 month"
        rule = '1M'
    
    # Resample data
    resampled = df.resample(rule).mean().dropna()
    
    # Apply limit to number of points (prevent overloading the plot)
    max_points = 100
    if len(resampled) > max_points:
        resampled = resampled.iloc[-max_points:]
    
    # Return as lists
    return resampled.index.tolist(), resampled['brightness'].tolist()

# Sidebar for controls and settings
st.sidebar.markdown("<h2 style='text-align: center;'>Controls & Settings</h2>", unsafe_allow_html=True)

# Function to toggle between light and dark theme
def toggle_theme():
    """Toggle between light and dark theme"""
    if st.session_state.theme == "light":
        st.session_state.theme = "dark"
    else:
        st.session_state.theme = "light"

# Camera selection with better UI
st.sidebar.markdown("<div class='camera-selector'>", unsafe_allow_html=True)
st.sidebar.markdown("<h3 style='text-align: center;'>📷 Camera Selection</h3>", unsafe_allow_html=True)

# Check if camera has changed
prev_camera = st.session_state.current_camera
selected_camera = st.sidebar.selectbox(
    "Select Camera",
    list(CAMERAS.keys()),
    format_func=lambda x: CAMERAS[x]["name"],
    index=list(CAMERAS.keys()).index(st.session_state.current_camera) if st.session_state.current_camera in CAMERAS else 0
)

# Update current camera in session state if changed
if selected_camera != prev_camera:
    st.session_state.current_camera = selected_camera
    st.rerun()  # Refresh the app with the new camera

st.sidebar.markdown(f"<p style='text-align: center;'><b>Location:</b> {CAMERAS[selected_camera]['location']}</p>", unsafe_allow_html=True)
st.sidebar.markdown("</div>", unsafe_allow_html=True)

# Visibility threshold adjustment
visibility_threshold = st.sidebar.slider(
    "Visibility Threshold", 
    min_value=50, 
    max_value=150, 
    value=CAMERAS[selected_camera]["visibility_threshold"],
    help="Adjust the brightness threshold for visibility alerts"
)

# Advanced settings
advanced_settings = st.sidebar.expander("Advanced Settings", expanded=False)
with advanced_settings:
    corruption_std_threshold = st.slider(
        "Corruption Detection - Std Dev Threshold", 
        min_value=5, 
        max_value=30, 
        value=10,
        help="Lower values make corruption detection more sensitive"
    )
    
    corruption_hist_threshold = st.slider(
        "Corruption Detection - Histogram Threshold", 
        min_value=50, 
        max_value=300, 
        value=100,
        help="Lower values make corruption detection more sensitive"
    )
    
    max_corrupted_frames_setting = st.slider(
        "Max Consecutive Corrupted Frames", 
        min_value=2, 
        max_value=20, 
        value=5,
        help="Number of corrupted frames before reconnecting"
    )
    
    reliability_mode = st.checkbox(
        "Enable High Reliability Mode",
        value=False,
        help="Reduces quality but improves stream stability by using lower resolution and framerate"
    )
    
    use_frame_caching = st.checkbox(
        "Enable Frame Caching",
        value=True,
        help="Shows last good frame when corruption is detected"
    )
    
    rtsp_transport = st.radio(
        "RTSP Transport Protocol",
        ["tcp", "udp", "http", "https"],
        index=["tcp", "udp", "http", "https"].index(st.session_state.display_settings['rtsp_transport']),
        help="TCP is more reliable but higher latency. UDP is faster but less reliable."
    )
    
    # Update session state when the value changes
    if st.session_state.display_settings['rtsp_transport'] != rtsp_transport:
        st.session_state.display_settings['rtsp_transport'] = rtsp_transport
        st.session_state.camera_settings_changed = True

# Plot settings
plot_settings = st.sidebar.expander("Plot Settings", expanded=True)
with plot_settings:
    st.session_state.plot_timeframe = st.selectbox(
        "Time Range", 
        ["5 seconds", "1 minute", "5 minutes", "1 hour", "12 hours", "1 day", "1 week", "1 month"],
        index=1  # Default to 1 minute
    )
    
    update_options = {
        "Every 5 seconds": 5,
        "Every 10 seconds": 10,
        "Every 30 seconds": 30,
        "Every minute": 60,
        "Manual refresh only": -1
    }
    
    update_selection = st.selectbox(
        "Plot Update Frequency",
        list(update_options.keys()),
        index=0
    )
    st.session_state.plot_update_interval = update_options[update_selection]
    
    if st.session_state.plot_update_interval == -1:
        if st.button("Refresh Plot Now"):
            st.session_state.last_plot_update_time = datetime.datetime.now()

# Recording controls - now showing status only
recording_section = st.sidebar.expander("Recording Settings", expanded=True)
with recording_section:
    st.info("✅ Automatic recording is enabled")
    st.info("✅ Automatic highlight creation based on visibility threshold")
    
    # Additional settings
    MIN_HIGHLIGHT_GAP = st.slider(
        "Minimum time between highlights (seconds)", 
        min_value=10, 
        max_value=120, 
        value=30,
        help="Minimum time between automatic highlights"
    )

# Main content
st.markdown(f"<h1 class='main-header'>Multi-Camera Surveillance Dashboard</h1>", unsafe_allow_html=True)

# Add theme toggle button in the header
col1, col2, col3 = st.columns([3, 1, 3])
with col2:
    if st.button("🌓 Toggle Theme", on_click=toggle_theme):
        # The toggle_theme function will be called when the button is clicked
        pass

st.markdown(f"<h2 style='text-align: center;'>Currently Viewing: {CAMERAS[selected_camera]['location']}</h2>", unsafe_allow_html=True)

# Create tabs with all functionality
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📡 Live Monitoring", 
    "📊 Analytics", 
    "🌦️ Weather Insights", 
    "📼 Recordings", 
    "🔍 Highlights",
    "📆 Historical Data"
])

# --- 📡 Live Monitoring Tab ---
with tab1:
    # Create two columns for camera and info
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 class='sub-header'>📹 Live Feed</h2>", unsafe_allow_html=True)
        
        # Add auto-refresh controls
        col_controls1, col_controls2 = st.columns(2)
        with col_controls1:
            # Use session state to store the settings
            refresh_rate = st.slider("Frame Refresh Rate (seconds)", 
                                    min_value=0.1, max_value=5.0, 
                                    value=st.session_state.display_settings['refresh_rate'], 
                                    step=0.1,
                                    key='refresh_rate_slider')
            
            # Update session state when the value changes
            if st.session_state.display_settings['refresh_rate'] != refresh_rate:
                st.session_state.display_settings['refresh_rate'] = refresh_rate
                st.session_state.camera_settings_changed = True
            
            auto_refresh = st.checkbox("Enable Auto-Refresh", 
                                     value=st.session_state.display_settings['auto_refresh'],
                                     key='auto_refresh_checkbox')
            
            # Update session state when the value changes
            if st.session_state.display_settings['auto_refresh'] != auto_refresh:
                st.session_state.display_settings['auto_refresh'] = auto_refresh
                st.session_state.camera_settings_changed = True
                
        with col_controls2:
            display_mode = st.radio("Display Mode", 
                                   ["Standard", "High Performance"], 
                                   index=0 if st.session_state.display_settings['display_mode'] == "Standard" else 1,
                                   key='display_mode_radio',
                                   help="High Performance mode may reduce lag but show less detail")
            
            # Update session state when the value changes
            if st.session_state.display_settings['display_mode'] != display_mode:
                st.session_state.display_settings['display_mode'] = display_mode
                st.session_state.camera_settings_changed = True
                
            show_fps = st.checkbox("Show FPS", 
                                 value=st.session_state.display_settings['show_fps'],
                                 key='show_fps_checkbox')
            
            # Update session state when the value changes
            if st.session_state.display_settings['show_fps'] != show_fps:
                st.session_state.display_settings['show_fps'] = show_fps
        
        # Create a container for the camera feed
        camera_feed = st.empty()
        
        # Add a refresh button and timestamp indicator
        refresh_col1, refresh_col2, refresh_col3 = st.columns([1, 1, 2])
        with refresh_col1:
            if st.button("Manual Refresh"):
                # This will be handled by the main loop - just triggering a rerun
                st.rerun()
        with refresh_col2:
            if st.button("Reconnect Camera", type="primary"):
                st.session_state.camera_settings_changed = True
                st.rerun()
        with refresh_col3:
            last_update = st.empty()
        
        # Add a status indicator for camera connection status
        camera_status = st.empty()
        
        # JavaScript for auto-refresh
        if st.session_state.display_settings['auto_refresh']:
            refresh_rate_ms = int(st.session_state.display_settings['refresh_rate'] * 1000)
            st.markdown(f"""
            <script>
                // Auto-refresh logic
                function refreshFrame() {{
                    try {{
                        window.parent.postMessage({{type: 'streamlit:forceRefresh'}}, '*');
                    }} catch (error) {{
                        console.log('Auto-refresh error:', error);
                    }}
                }}
                
                // Set up auto-refresh interval
                var refreshIntervalId = setInterval(refreshFrame, {refresh_rate_ms});
                
                // Clear any existing interval when this script runs again
                window.addEventListener('beforeunload', function() {{
                    clearInterval(refreshIntervalId);
                }});
            </script>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        # Weather information card
        weather = get_weather(CAMERAS[selected_camera]["weather_city"])
        st.session_state.cameras_data[selected_camera]["weather_data"] = weather
        
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<h2 class='sub-header'>{weather['icon']} Weather</h2>", unsafe_allow_html=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Temperature", f"{weather['temperature']}°C")
        with col_b:
            st.metric("Humidity", f"{weather['humidity']}%")
        
        st.markdown(f"<p><b>Condition:</b> {weather['condition']}</p>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Wind Speed:</b> {weather['wind_speed']} m/s</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# --- 🔍 Highlights Tab (now separate) ---
with tab5:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"<h2 class='sub-header'>🔍 Highlight Clips - {CAMERAS[selected_camera]['name']}</h2>", unsafe_allow_html=True)
    
    # Get and display highlights for the selected camera
    try:
        # Create camera-specific highlights directory if it doesn't exist
        camera_highlights_dir = f"highlights/{selected_camera}"
        os.makedirs(camera_highlights_dir, exist_ok=True)
        
        # Get list of highlights for the selected camera
        highlights = []
        for item in os.listdir(camera_highlights_dir):
            item_path = os.path.join(camera_highlights_dir, item)
            # Only include files, not directories
            if os.path.isfile(item_path) and item.endswith(('.mp4', '.avi', '.mov')):
                highlights.append(item)
        
        # Sort highlights by date (newest first)
        highlights = sorted(highlights, reverse=True)
    except Exception as e:
        logger.error(f"Error accessing highlights directory for {selected_camera}: {str(e)}")
        highlights = []
    
    if not highlights:
        st.info(f"No highlights available yet for {CAMERAS[selected_camera]['name']}. Use the 'Mark Highlight' button to save important moments.")
    else:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            selected_highlight = st.selectbox(
                "Select a highlight:", 
                highlights
            )
            
            # Add highlight info
            if selected_highlight:
                # Extract timestamp from filename
                try:
                    highlight_date = selected_highlight.split("_")[1]
                    highlight_time = selected_highlight.split("_")[2].split(".")[0]
                    st.info(f"Captured on: {highlight_date} at {highlight_time.replace('-', ':')}")
                except:
                    st.info("Date information not available")
                
                # Get file size
                try:
                    file_path = os.path.join(camera_highlights_dir, selected_highlight)
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
                        st.info(f"File size: {file_size:.2f} MB")
                except Exception as e:
                    logger.error(f"Error getting file size: {str(e)}")
                    st.warning("File size information not available")
                
                # Add option to add a note to the highlight
                highlight_note = st.text_input("Add a note to this highlight")
                if st.button("Save Note"):
                    st.success("Note saved successfully!")
        
        with col2:
            if selected_highlight:
                try:
                    highlight_path = os.path.join(camera_highlights_dir, selected_highlight)
                    if os.path.exists(highlight_path) and os.path.isfile(highlight_path):
                        st.video(highlight_path)
                    else:
                        st.error(f"Highlight file not found: {highlight_path}")
                except Exception as e:
                    logger.error(f"Error displaying highlight: {str(e)}")
                    st.error("Could not display the selected highlight")
    
    st.markdown("</div>", unsafe_allow_html=True)

# --- 📆 Historical Data Tab ---
with tab6:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>📈 Historical Statistics</h2>", unsafe_allow_html=True)
    
    # Date range selection
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.datetime.now() - datetime.timedelta(days=7))
    with col2:
        end_date = st.date_input("End Date", value=datetime.datetime.now())
    
    # Query data from the database
    try:
        conn = sqlite3.connect('data/analytics.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Daily statistics
        cursor.execute('''
        SELECT * FROM daily_stats 
        WHERE camera_id = ? AND date BETWEEN ? AND ?
        ORDER BY date ASC
        ''', (
            selected_camera,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))
        
        daily_stats_results = [dict(row) for row in cursor.fetchall()]
        
        # Weather data
        cursor.execute('''
        SELECT * FROM weather_data 
        WHERE city = ? AND DATE(timestamp) BETWEEN ? AND ?
        ORDER BY timestamp ASC
        ''', (
            CAMERAS[selected_camera]["weather_city"],
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))
        
        weather_results = [dict(row) for row in cursor.fetchall()]
        
        # Events data
        cursor.execute('''
        SELECT * FROM events 
        WHERE camera_id = ? AND DATE(timestamp) BETWEEN ? AND ?
        ORDER BY timestamp ASC
        ''', (
            selected_camera,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))
        
        events_results = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching historical data: {str(e)}")
        daily_stats_results = []
        weather_results = []
        events_results = []
    
    # Display statistics
    if daily_stats_results:
        st.subheader("Daily Camera Statistics")
        
        # Extract dates and metrics for plotting
        dates = [row['date'] for row in daily_stats_results]
        brightness_values = {
            'Min': [row['min_brightness'] for row in daily_stats_results],
            'Avg': [row['avg_brightness'] for row in daily_stats_results],
            'Max': [row['max_brightness'] for row in daily_stats_results]
        }
        
        # Create a multi-line plot for brightness metrics
        fig1 = go.Figure()
        
        for metric_name, values in brightness_values.items():
            fig1.add_trace(go.Scatter(
                x=dates,
                y=values,
                mode='lines+markers',
                name=f'{metric_name} Brightness'
            ))
        
        fig1.update_layout(
            title="Brightness Trends Over Time",
            xaxis_title="Date",
            yaxis_title="Brightness Level",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig1, use_container_width=True)
        
        # Create a second graph for system metrics
        system_metrics = {
            'Uptime (%)': [row['uptime_percentage'] for row in daily_stats_results],
            'Reconnects': [row['reconnect_count'] for row in daily_stats_results],
            'Corruptions': [row['corruption_count'] for row in daily_stats_results]
        }
        
        fig2 = go.Figure()
        
        # Add traces for each metric
        fig2.add_trace(go.Bar(
            x=dates,
            y=system_metrics['Uptime (%)'],
            name='Uptime (%)',
            marker_color='green'
        ))
        
        # Create a secondary y-axis for the counts
        fig2.add_trace(go.Scatter(
            x=dates,
            y=system_metrics['Reconnects'],
            mode='lines+markers',
            name='Reconnects',
            marker_color='orange',
            yaxis='y2'
        ))
        
        fig2.add_trace(go.Scatter(
            x=dates,
            y=system_metrics['Corruptions'],
            mode='lines+markers',
            name='Corruptions',
            marker_color='red',
            yaxis='y2'
        ))
        
        fig2.update_layout(
            title="System Reliability Metrics",
            xaxis_title="Date",
            yaxis_title="Uptime Percentage",
            yaxis2=dict(
                title="Count",
                overlaying="y",
                side="right"
            ),
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig2, use_container_width=True)
        
        # Show the raw data in a table
        st.subheader("Daily Statistics Data")
        df_stats = pd.DataFrame(daily_stats_results)
        st.dataframe(df_stats)
    else:
        st.info("No historical data available for the selected date range. Data will be collected as the system runs.")
    
    # Data export section
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>📊 Data Export</h2>", unsafe_allow_html=True)
    
    export_type = st.radio("Select export format:", ["CSV", "JSON", "Excel"])
    
    if st.button("Export Data"):
        try:
            # Create export directory
            os.makedirs("exports", exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create a DataFrame from the query results
            df_export = pd.DataFrame(daily_stats_results)
            
            # Generate filename
            filename_base = f"exports/{selected_camera}_stats_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}_{timestamp}"
            
            # Export based on selected format
            if export_type == "CSV":
                filename = f"{filename_base}.csv"
                df_export.to_csv(filename, index=False)
            elif export_type == "JSON":
                filename = f"{filename_base}.json"
                df_export.to_json(filename, orient="records", indent=4)
            else:  # Excel
                filename = f"{filename_base}.xlsx"
                df_export.to_excel(filename, index=False)
            
            st.success(f"Data exported successfully to {filename}")
            
            # Provide download link
            with open(filename, "rb") as file:
                st.download_button(
                    label=f"Download {export_type} file",
                    data=file,
                    file_name=os.path.basename(filename),
                    mime="application/octet-stream"
                )
        except Exception as e:
            st.error(f"Error exporting data: {str(e)}")
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

# Main app logic for camera feed
try:
    # Configure resolution based on reliability mode
    if reliability_mode:
        STREAM_WIDTH, STREAM_HEIGHT = 1280, 720  # Lower resolution for reliability
        STREAM_FPS = 20  # Lower framerate for reliability
    else:
        STREAM_WIDTH, STREAM_HEIGHT = FRAME_WIDTH, FRAME_HEIGHT  # Original resolution
        STREAM_FPS = 20  # Original framerate
    
    # Frame caching for corrupted frames
    last_good_frame = None
    
    # Check if settings have changed, and reset the connection if needed
    if st.session_state.camera_settings_changed:
        camera_status.warning("Settings changed. Reconnecting camera...")
        if 'cap' in locals() and cap.isOpened():
            cap.release()
    
    # Use environment variables to configure FFmpeg for OpenCV
    rtsp_transport = st.session_state.display_settings['rtsp_transport']
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{rtsp_transport}|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
    
    # Open RTSP Stream with more robust options for HEVC decoding
    try:
        cap = cv2.VideoCapture(CAMERAS[selected_camera]["rtsp_url"], cv2.CAP_FFMPEG)
        
        # Apply additional capture properties to improve HEVC handling
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Smallest buffer for less delay
        
        # Set resolution and framerate
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
        
        if not cap.isOpened():
            camera_status.error("⚠️ Failed to connect to camera. Please check your URL and network settings.")
            logger.error("❌ Failed to connect to RTSP stream. Check your URL or network settings.")
        else:
            camera_status.success("✅ Camera connected successfully")
    except Exception as e:
        camera_status.error(f"⚠️ Camera connection error: {str(e)}")
        logger.error(f"Camera connection error: {str(e)}")
        cap = None
    
    # Setup video writer for recording - always active
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Same codec as Cam.py
    out = cv2.VideoWriter(f"recordings/{selected_camera}/{today_date}_{datetime.datetime.now().strftime('%H-%M-%S')}.mp4", fourcc, STREAM_FPS, (FRAME_WIDTH, FRAME_HEIGHT))
    if not out.isOpened():
        logger.error("❌ Failed to create video writer. Check your codec or file path.")
        out = None
    
    # Set up variables for automatic highlight detection
    poor_visibility_duration = 0
    normal_visibility_duration = 0
    visibility_poor = False
    consecutive_corrupted_frames = 0
    
    if not cap or not cap.isOpened():
        st.error("Camera connection failed. Please check your settings and try reconnecting.")
        if st.button("Reconnect Camera"):
            st.session_state.camera_settings_changed = True
            st.rerun()
    else:
        # Main processing loop
        while True:
            try:
                # Get current camera configuration
                camera_id = st.session_state.current_camera
                camera_config = DEFAULT_CAMERA_CONFIG[camera_id]
                
                # Handle camera connection
                if st.session_state.camera_settings_changed:
                    if 'cap' in st.session_state:
                        st.session_state.cap.release()
                    st.session_state.cap = create_camera_connection(
                        camera_id,
                        camera_config['rtsp_url'],
                        camera_config['stream_settings']
                    )
                    if st.session_state.cap is None:
                        st.error("Failed to connect to camera. Please check your settings.")
                        time.sleep(1)
                        continue
                    st.session_state.camera_settings_changed = False
                
                # Read frame
                ret, frame = st.session_state.cap.read()
                if not ret:
                    st.session_state.reconnect_counter += 1
                    if st.session_state.reconnect_counter >= 3:
                        logger.warning("Too many frame read errors. Attempting to reconnect...")
                        st.session_state.cap.release()
                        time.sleep(1)
                        st.session_state.cap = create_camera_connection(
                            camera_id,
                            camera_config['rtsp_url'],
                            camera_config['stream_settings']
                        )
                        st.session_state.reconnect_counter = 0
                    continue
                
                # Process frame
                frame = cv2.resize(frame, (camera_config['stream_settings']['width'],
                                         camera_config['stream_settings']['height']))
                
                # Analyze visibility
                brightness, is_corrupted = analyze_visibility(frame)
                
                # Update camera data
                camera_data = st.session_state.cameras_data[camera_id]
                camera_data["brightness_history"].append(brightness)
                camera_data["timestamps"].append(datetime.datetime.now())
                
                # Keep history size reasonable
                if len(camera_data["brightness_history"]) > 86400:  # 24 hours of data
                    camera_data["brightness_history"].pop(0)
                    camera_data["timestamps"].pop(0)
                
                # Update UI status
                st.session_state.current_brightness = brightness
                if brightness < camera_data["visibility_threshold"]:
                    st.session_state.visibility_status = "Poor"
                    if not st.session_state.recording_status == "Recording":
                        st.session_state.recording_status = "Recording"
                        start_recording(camera_id)
                    if brightness < camera_data["visibility_threshold"] * 0.8:
                        create_highlight(camera_id, time.time())
                elif brightness >= camera_data["recovery_threshold"]:
                    st.session_state.visibility_status = "Good"
                    if st.session_state.recording_status == "Recording":
                        st.session_state.recording_status = "Not Recording"
                        stop_recording()
                
                # Update debug info
                if st.session_state.show_debug_info:
                    st.session_state.debug_info = (
                        f"FPS: {1.0 / (time.time() - st.session_state.last_frame_time):.1f}\n"
                        f"Brightness: {brightness:.1f}\n"
                        f"Corrupted: {is_corrupted}\n"
                        f"Reconnect Count: {st.session_state.reconnect_counter}"
                    )
                
                # Update frame time
                st.session_state.last_frame_time = time.time()
                st.session_state.frame_count += 1
                
                # Update UI
                if st.session_state.auto_refresh:
                    time.sleep(st.session_state.refresh_rate)
                    st.rerun()
                
            except Exception as e:
                logger.error(f"Error in main processing loop: {str(e)}")
                time.sleep(1)
                continue

except Exception as e:
    logger.error(f"An error occurred: {str(e)}")
    # Ensure resources are released
    if 'cap' in locals() and cap.isOpened():
        cap.release()
    if 'out' in locals() and out is not None and out.isOpened():
        out.release()

# Database and configuration functions
def setup_database():
    """Initialize SQLite database for analytics storage"""
    try:
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        # Connect to SQLite database (will be created if it doesn't exist)
        conn = sqlite3.connect('data/analytics.db')
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        
        # Visibility metrics table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS visibility_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            brightness REAL,
            is_corrupted INTEGER,
            is_poor_visibility INTEGER,
            notes TEXT
        )
        ''')
        
        # Daily statistics table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            date DATE NOT NULL,
            min_brightness REAL,
            max_brightness REAL,
            avg_brightness REAL,
            total_samples INTEGER,
            visibility_duration INTEGER,
            max_visibility_duration INTEGER,
            reconnect_count INTEGER,
            corruption_count INTEGER,
            uptime_percentage REAL,
            weather_condition TEXT,
            avg_temperature REAL,
            notes TEXT,
            UNIQUE(camera_id, date)
        )
        ''')
        
        # Weather data table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            temperature REAL,
            humidity REAL,
            condition TEXT,
            wind_speed REAL,
            pressure REAL,
            visibility REAL,
            sunrise TEXT,
            sunset TEXT
        )
        ''')
        
        # Events table for highlights and significant events
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            duration INTEGER,
            file_path TEXT,
            notes TEXT
        )
        ''')
        
        # Create indexes for better query performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visibility_metrics_camera_timestamp ON visibility_metrics(camera_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_stats_camera_date ON daily_stats(camera_id, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_weather_data_city_timestamp ON weather_data(city, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_camera_timestamp ON events(camera_id, timestamp)')
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        logger.info("Database setup complete")
        return True
    except Exception as e:
        logger.error(f"Database setup failed: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def load_camera_config():
    """Load camera configuration from JSON file or create default if not exists"""
    config_path = 'config/cameras.json'
    os.makedirs("config", exist_ok=True)
    
    # Default camera configuration
    default_config = {
        "Manila_Observatory": {
            "name": "Manila Observatory",
            "rtsp_url": "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1",
            "location": "Manila Observatory",
            "weather_city": "Quezon City",
            "visibility_threshold": 80,
            "recovery_threshold": 100,
            "stream_settings": {
                "width": 1280,
                "height": 720,
                "fps": 20,
                "codec": "mp4v",
                "buffer_size": 1,
                "rtsp_transport": "tcp"
            }
        },
        "AIC": {
            "name": "AIC",
            "rtsp_url": "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1",
            "location": "AIC",
            "weather_city": "Baguio City",
            "visibility_threshold": 80,
            "recovery_threshold": 100,
            "stream_settings": {
                "width": 1280,
                "height": 720,
                "fps": 20,
                "codec": "mp4v",
                "buffer_size": 1,
                "rtsp_transport": "tcp"
            }
        }
    }
    
    try:
        # Try to load the configuration file
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                cameras = json.load(f)
                logger.info(f"Loaded camera configuration from {config_path}")
        else:
            # Create default configuration file if it doesn't exist
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            cameras = default_config
            logger.info(f"Created default camera configuration at {config_path}")
        
        # Validate and update camera configurations
        for camera_id, config in cameras.items():
            # Ensure all required fields are present
            required_fields = ["name", "rtsp_url", "location", "weather_city", "visibility_threshold", "recovery_threshold"]
            for field in required_fields:
                if field not in config:
                    logger.warning(f"Missing required field '{field}' in camera {camera_id}, using default value")
                    if field in default_config[camera_id]:
                        config[field] = default_config[camera_id][field]
                    else:
                        raise ValueError(f"Missing required field '{field}' in default configuration")
            
            # Add stream settings if not present
            if "stream_settings" not in config:
                config["stream_settings"] = default_config[camera_id]["stream_settings"]
            else:
                # Ensure all stream settings are present
                for setting, value in default_config[camera_id]["stream_settings"].items():
                    if setting not in config["stream_settings"]:
                        config["stream_settings"][setting] = value
                        logger.warning(f"Missing stream setting '{setting}' in camera {camera_id}, using default value")
        
        return cameras
    except Exception as e:
        logger.error(f"Error loading camera configuration: {str(e)}")
        logger.error(traceback.format_exc())
        logger.info("Using default camera configuration")
        return default_config

def create_camera_connection(camera_id, rtsp_url, stream_settings):
    """Create a connection to the camera"""
    try:
        # Configure FFmpeg options
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{stream_settings['rtsp_transport']}|"
            f"analyzeduration;10000000|"
            f"buffer_size;{stream_settings['buffer_size']}|"
            f"stimeout;5000000|"
            f"max_delay;500000|"
            f"fflags;nobuffer|"
            f"flags;low_delay"
        )
        
        # Create video capture object
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        
        if not cap.isOpened():
            raise Exception("Failed to open RTSP stream")
        
        # Apply stream settings
        cap.set(cv2.CAP_PROP_BUFFERSIZE, stream_settings['buffer_size'])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, stream_settings['width'])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, stream_settings['height'])
        cap.set(cv2.CAP_PROP_FPS, stream_settings['fps'])
        
        # Verify settings
        actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        
        logger.info(f"Camera {camera_id} connected successfully")
        logger.info(f"Stream settings: {actual_width}x{actual_height}@{actual_fps:.1f}")
        
        return cap
        
    except Exception as e:
        logger.error(f"Error connecting to camera {camera_id}: {str(e)}")
        return None

def test_camera_connection(camera_id, rtsp_url, stream_settings):
    """Test if a camera connection is working"""
    try:
        cap = create_camera_connection(camera_id, rtsp_url, stream_settings)
        if cap is None:
            return False
        
        # Try to read a frame
        ret, frame = cap.read()
        if not ret:
            logger.error(f"Failed to read frame from camera {camera_id}")
            cap.release()
            return False
        
        # Test frame dimensions
        if frame.shape[1] != stream_settings['width'] or frame.shape[0] != stream_settings['height']:
            logger.warning(f"Frame dimensions mismatch for camera {camera_id}")
            logger.warning(f"Expected: {stream_settings['width']}x{stream_settings['height']}")
            logger.warning(f"Actual: {frame.shape[1]}x{frame.shape[0]}")
        
        cap.release()
        return True
    except Exception as e:
        logger.error(f"Error testing camera connection for {camera_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def save_daily_stats(camera_id, stats):
    """Save daily statistics to the database"""
    try:
        conn = sqlite3.connect('data/analytics.db')
        cursor = conn.cursor()
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Check if entry already exists for this camera and date
        cursor.execute('''
        SELECT id FROM daily_stats WHERE camera_id = ? AND date = ?
        ''', (camera_id, today))
        
        result = cursor.fetchone()
        
        if result:
            # Update existing entry
            cursor.execute('''
            UPDATE daily_stats SET
                min_brightness = ?,
                max_brightness = ?,
                avg_brightness = ?,
                total_samples = ?,
                visibility_duration = ?,
                max_visibility_duration = ?,
                reconnect_count = ?,
                corruption_count = ?,
                uptime_percentage = ?
            WHERE camera_id = ? AND date = ?
            ''', (
                stats["min_brightness"] if stats["min_brightness"] != float('inf') else 0,
                stats["max_brightness"],
                stats["avg_brightness"],
                stats["total_samples"],
                stats["visibility_duration"],
                stats["max_visibility_duration"],
                stats["reconnect_count"],
                stats["corruption_count"],
                stats["uptime_percentage"],
                camera_id,
                today
            ))
        else:
            # Insert new entry
            cursor.execute('''
            INSERT INTO daily_stats (
                camera_id, date, min_brightness, max_brightness, avg_brightness,
                total_samples, visibility_duration, max_visibility_duration,
                reconnect_count, corruption_count, uptime_percentage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                camera_id,
                today,
                stats["min_brightness"] if stats["min_brightness"] != float('inf') else 0,
                stats["max_brightness"],
                stats["avg_brightness"],
                stats["total_samples"],
                stats["visibility_duration"],
                stats["max_visibility_duration"],
                stats["reconnect_count"],
                stats["corruption_count"],
                stats["uptime_percentage"]
            ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving daily stats: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def log_brightness_sample(camera_id, timestamp, brightness, is_corrupted, is_poor_visibility):
    """Log a brightness sample to the database (sampled at intervals to avoid too much data)"""
    # Only log every 60th sample (approximately once per minute) to avoid database bloat
    if st.session_state.data_update_counter % 60 != 0:
        return
    
    try:
        conn = sqlite3.connect('data/analytics.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO visibility_metrics (
            camera_id, timestamp, brightness, is_corrupted, is_poor_visibility
        ) VALUES (?, ?, ?, ?, ?)
        ''', (
            camera_id,
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            brightness,
            1 if is_corrupted else 0,
            1 if is_poor_visibility else 0
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging brightness sample: {str(e)}")
        logger.error(traceback.format_exc())

def save_weather_data(city, weather_data):
    """Save weather data to the database"""
    try:
        # Skip if weather data is not available (API key missing, etc.)
        if weather_data.get("temperature") == "N/A":
            return False
        
        conn = sqlite3.connect('data/analytics.db')
        cursor = conn.cursor()
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
        INSERT INTO weather_data (
            city, timestamp, temperature, humidity, condition,
            wind_speed, pressure, visibility, sunrise, sunset
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            city,
            timestamp,
            weather_data["temperature"],
            weather_data["humidity"],
            weather_data["condition"],
            weather_data["wind_speed"],
            weather_data["pressure"],
            weather_data["visibility"],
            weather_data["sunrise"],
            weather_data["sunset"]
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving weather data: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def log_highlight_event(camera_id, timestamp, file_path):
    """Log a highlight event to the database"""
    try:
        conn = sqlite3.connect('data/analytics.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO events (
            camera_id, event_type, timestamp, file_path
        ) VALUES (?, ?, ?, ?)
        ''', (
            camera_id,
            "highlight",
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            file_path
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error logging highlight event: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def get_historical_stats(camera_id, days=7):
    """Get historical statistics for a camera from the database"""
    try:
        conn = sqlite3.connect('data/analytics.db')
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days)
        
        cursor.execute('''
        SELECT * FROM daily_stats 
        WHERE camera_id = ? AND date BETWEEN ? AND ?
        ORDER BY date DESC
        ''', (
            camera_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return results
    except Exception as e:
        logger.error(f"Error getting historical stats: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def backup_database():
    """Create a backup of the database"""
    try:
        os.makedirs("backups", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        source_path = 'data/analytics.db'
        
        if os.path.exists(source_path):
            backup_path = f'backups/analytics_{timestamp}.db'
            shutil.copy2(source_path, backup_path)
            logger.info(f"Database backup created at {backup_path}")
            
            # Clean up old backups (keep only last 10)
            backup_files = sorted(Path('backups').glob('analytics_*.db'))
            if len(backup_files) > 10:
                for old_backup in backup_files[:-10]:
                    os.remove(old_backup)
                    logger.info(f"Removed old backup: {old_backup}")
            
            return True
        else:
            logger.warning("No database file found to backup")
            return False
    except Exception as e:
        logger.error(f"Database backup failed: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def save_session_state():
    """Save session state to a JSON file for persistence across restarts"""
    try:
        os.makedirs("data", exist_ok=True)
        
        # Create a serializable copy of the session state
        serializable_state = {}
        
        # Handle cameras_data
        if 'cameras_data' in st.session_state:
            serializable_state['cameras_data'] = {}
            
            for camera_id, camera_data in st.session_state.cameras_data.items():
                serializable_state['cameras_data'][camera_id] = {}
                
                # Handle brightness_history (convert datetime objects to strings)
                if 'brightness_history' in camera_data:
                    serializable_state['cameras_data'][camera_id]['brightness_history'] = camera_data['brightness_history']
                
                # Handle timestamps (convert datetime objects to strings)
                if 'timestamps' in camera_data:
                    serializable_state['cameras_data'][camera_id]['timestamps'] = [t.strftime("%Y-%m-%d %H:%M:%S") if isinstance(t, datetime.datetime) else str(t) for t in camera_data['timestamps']]
                
                # Handle highlight_marker
                if 'highlight_marker' in camera_data:
                    serializable_state['cameras_data'][camera_id]['highlight_marker'] = camera_data['highlight_marker']
                
                # Handle daily_stats
                if 'daily_stats' in camera_data:
                    serializable_state['cameras_data'][camera_id]['daily_stats'] = camera_data['daily_stats']
                
                # Handle weather_data (simplify to avoid complex objects)
                if 'weather_data' in camera_data and camera_data['weather_data']:
                    weather_simple = {}
                    for key, value in camera_data['weather_data'].items():
                        # Skip complex objects or non-serializable values
                        if isinstance(value, (str, int, float, bool, type(None))):
                            weather_simple[key] = value
                    serializable_state['cameras_data'][camera_id]['weather_data'] = weather_simple
                
                # Handle primitive types
                for key, value in camera_data.items():
                    if key not in ['brightness_history', 'timestamps', 'highlight_marker', 'daily_stats', 'weather_data']:
                        if isinstance(value, (str, int, float, bool, type(None))):
                            serializable_state['cameras_data'][camera_id][key] = value
        
        # Handle other session state variables
        for key, value in st.session_state.items():
            if key != 'cameras_data' and isinstance(value, (str, int, float, bool, type(None))):
                serializable_state[key] = value
        
        # Save to file
        with open('data/session_state.json', 'w') as f:
            json.dump(serializable_state, f, indent=4)
            
        logger.info("Session state saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving session state: {str(e)}")
        logger.error(traceback.format_exc())
        return False

# Schedule periodic tasks
def schedule_periodic_tasks():
    """Schedule tasks like database backup and stats saving"""
    current_time = datetime.datetime.now()
    
    # Backup the database at midnight
    if current_time.hour == 0 and current_time.minute == 0 and current_time.second < 5:
        backup_database()
    
    # Save daily stats every hour
    if current_time.minute == 0 and current_time.second < 5:
        for camera_id in st.session_state.cameras_data:
            save_daily_stats(camera_id, st.session_state.cameras_data[camera_id]["daily_stats"])
    
    # Save session state every 10 minutes
    if current_time.minute % 10 == 0 and current_time.second < 5:
        save_session_state()

# Initialize database and load configuration
setup_database()
CAMERAS = load_camera_config()

# Initialize UI components
if 'visibility_status' not in st.session_state:
    st.session_state.visibility_status = st.empty()
if 'recording_status' not in st.session_state:
    st.session_state.recording_status = st.empty()
if 'current_brightness' not in st.session_state:
    st.session_state.current_brightness = st.empty()
if 'debug_info' not in st.session_state:
    st.session_state.debug_info = st.empty()
if 'reconnect_counter' not in st.session_state:
    st.session_state.reconnect_counter = st.empty()
if 'brightness_chart' not in st.session_state:
    st.session_state.brightness_chart = st.empty()
if 'alerts_container' not in st.session_state:
    st.session_state.alerts_container = st.empty()

def start_recording(camera_id):
    """Start recording the camera feed"""
    try:
        if 'out' not in st.session_state:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            st.session_state.out = cv2.VideoWriter(
                f"recordings/{camera_id}/{today_date}_{datetime.datetime.now().strftime('%H-%M-%S')}.mp4",
                fourcc, STREAM_FPS, (FRAME_WIDTH, FRAME_HEIGHT)
            )
        st.session_state.recording = True
        logger.info(f"Started recording for camera {camera_id}")
    except Exception as e:
        logger.error(f"Error starting recording: {str(e)}")
        st.session_state.recording = False

def stop_recording():
    """Stop recording the camera feed"""
    try:
        if 'out' in st.session_state and st.session_state.out is not None:
            st.session_state.out.release()
            st.session_state.out = None
        st.session_state.recording = False
        logger.info("Stopped recording")
    except Exception as e:
        logger.error(f"Error stopping recording: {str(e)}")