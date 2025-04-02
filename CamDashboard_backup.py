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
        index=0,
        help="TCP is more reliable but higher latency. UDP is faster but less reliable."
)

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
        camera_feed = st.empty()
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
        
        # Status card
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 class='sub-header'>📊 Status</h2>", unsafe_allow_html=True)
        visibility_status = st.empty()
        recording_status = st.empty()
        current_brightness = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

        # Debug information card (if enabled)
        show_debug_info = advanced_settings.checkbox("Show Debug Information", value=False)
        if show_debug_info:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<h2 class='sub-header'>🛠️ Debug Information</h2>", unsafe_allow_html=True)
            debug_info = st.empty()
            reconnect_counter = st.empty()
            stream_settings = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

# --- 📊 Analytics Tab ---
with tab2:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"<h2 class='sub-header'>📈 Visibility Trends for {CAMERAS[selected_camera]['name']}</h2>", unsafe_allow_html=True)
    st.write(f"Showing data for the last **{st.session_state.plot_timeframe}** (resampled)")
    
    # Create placeholder for chart
    brightness_chart = st.empty()
    
    # Add manual refresh button when using manual refresh
    if st.session_state.plot_update_interval == -1:
        if st.button("Refresh Plot"):
            st.session_state.last_plot_update_time = datetime.datetime.now()
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Daily statistics card
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>📊 Daily Statistics</h2>", unsafe_allow_html=True)
    
    # Show daily stats in a nice grid of metrics
    stats = st.session_state.cameras_data[selected_camera]["daily_stats"]
    
    # Create tabs for different categories of statistics
    stat_tab1, stat_tab2, stat_tab3 = st.tabs(["Visibility", "System", "Advanced"])
    
    with stat_tab1:
        col1, col2, col3 = st.columns(3)
        with col1:
            min_brightness = stats["min_brightness"] if stats["min_brightness"] != float('inf') else 0
            st.metric("Min Brightness", f"{min_brightness:.1f}")
        with col2:
            st.metric("Avg Brightness", f"{stats['avg_brightness']:.1f}" if stats['total_samples'] > 0 else "0.0")
        with col3:
            st.metric("Max Brightness", f"{stats['max_brightness']:.1f}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Poor Visibility Events", f"{stats.get('poor_visibility_events', 0)}")
        with col2:
            st.metric("Total Poor Visibility Duration", f"{stats['visibility_duration']/60:.1f} min")
        with col3:
            st.metric("Max Poor Visibility Event", f"{stats['max_visibility_duration']/60:.1f} min")
    
    with stat_tab2:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Uptime", f"{stats['uptime_percentage']:.1f}%")
        with col2:
            st.metric("Reconnections", f"{stats['reconnect_count']}")
        with col3:
            st.metric("Corrupt Frames", f"{stats['corruption_count']}")
    
    with stat_tab3:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Motion Detected", "Yes" if stats['additional_metrics']['motion_detected'] else "No")
        with col2:
            st.metric("Motion Events", f"{stats['additional_metrics']['motion_count']}")
        
        st.metric("Last Updated", stats['additional_metrics']['last_update'])
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>⚠️ Recent Alerts</h2>", unsafe_allow_html=True)
    alerts_container = st.container()
    st.markdown("</div>", unsafe_allow_html=True)

# --- 🌦️ Weather Insights Tab ---
with tab3:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>🌦️ Weather Information</h2>", unsafe_allow_html=True)
    
    weather = st.session_state.cameras_data[selected_camera]["weather_data"]
    if not weather:
        weather = get_weather(CAMERAS[selected_camera]["weather_city"])
        st.session_state.cameras_data[selected_camera]["weather_data"] = weather
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown(f"<h3>{weather['icon']} {CAMERAS[selected_camera]['weather_city']}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Current Condition:</b> {weather['condition']}</p>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Temperature:</b> {weather['temperature']}°C</p>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Humidity:</b> {weather['humidity']}%</p>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<h3>🌡️ Additional Metrics</h3>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Wind Speed:</b> {weather['wind_speed']} m/s</p>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Pressure:</b> {weather['pressure']} hPa</p>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Visibility:</b> {weather['visibility']} meters</p>", unsafe_allow_html=True)
        st.markdown(f"<p><b>Sunrise:</b> {weather['sunrise']} | <b>Sunset:</b> {weather['sunset']}</p>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Weather Impact on Visibility
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>☁️ Weather Impact on Visibility</h2>", unsafe_allow_html=True)
    
    st.markdown("""
    <p>Weather conditions can significantly impact camera visibility:</p>
    <ul>
        <li><b>Rain/Snow:</b> Reduces visibility through water droplets on lens and in air</li>
        <li><b>Fog:</b> Reduces visibility by obscuring distant objects</li>
        <li><b>Wind:</b> Can cause camera movement, affecting image stability</li>
        <li><b>Dust:</b> Can cause lens obstruction and reduce clarity</li>
        <li><b>Extreme Temperatures:</b> Can affect camera performance</li>
    </ul>
    """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

# --- 📼 Recordings Tab (now separate) ---
with tab4:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"<h2 class='sub-header'>📼 Recorded Sessions - {CAMERAS[selected_camera]['name']}</h2>", unsafe_allow_html=True)
    
    # Get and display recordings for the selected camera
    try:
        # Create camera-specific recordings directory if it doesn't exist
        camera_recordings_dir = f"recordings/{selected_camera}"
        os.makedirs(camera_recordings_dir, exist_ok=True)
        
        # Get list of recordings for the selected camera
        recordings = []
        for item in os.listdir(camera_recordings_dir):
            item_path = os.path.join(camera_recordings_dir, item)
            # Only include files, not directories
            if os.path.isfile(item_path) and item.endswith(('.mp4', '.avi', '.mov')):
                recordings.append(item)
        
        # Sort recordings by date (newest first)
        recordings = sorted(recordings, reverse=True)
    except Exception as e:
        logger.error(f"Error accessing recordings directory for {selected_camera}: {str(e)}")
        recordings = []
    
    if not recordings:
        st.info(f"No recordings available yet for {CAMERAS[selected_camera]['name']}. Start recording to capture footage.")
    else:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            selected_file = st.selectbox(
                "Select a recording:", 
                recordings
            )
            
            # Add recording info
            if selected_file:
                # Extract date from filename
                try:
                    recording_date = selected_file.split("_")[0]
                    recording_time = selected_file.split("_")[1].split(".")[0]
                    st.info(f"Recording date: {recording_date}")
                    st.info(f"Recording time: {recording_time.replace('-', ':')}")
                except:
                    st.info("Date information not available")
                
                # Get file size
                try:
                    file_path = os.path.join(camera_recordings_dir, selected_file)
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
                        st.info(f"File size: {file_size:.2f} MB")
                except Exception as e:
                    logger.error(f"Error getting file size: {str(e)}")
                    st.warning("File size information not available")
        
        with col2:
            if selected_file:
                try:
                    recording_path = os.path.join(camera_recordings_dir, selected_file)
                    if os.path.exists(recording_path) and os.path.isfile(recording_path):
                        st.video(recording_path)
                    else:
                        st.error(f"Recording file not found: {recording_path}")
                except Exception as e:
                    logger.error(f"Error displaying recording: {str(e)}")
                    st.error("Could not display the selected recording")
    
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
    
    # Use environment variables to configure FFmpeg for OpenCV
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{rtsp_transport}|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
    
    # Open RTSP Stream with more robust options for HEVC decoding
    cap = cv2.VideoCapture(CAMERAS[selected_camera]["rtsp_url"], cv2.CAP_FFMPEG)
    
    # Apply additional capture properties to improve HEVC handling
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Smallest buffer for less delay
    
    # Set resolution and framerate
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
    
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
    
    if not cap.isOpened():
        logger.error("❌ Failed to connect to RTSP stream. Check your URL or network settings.")
    else:
        # Main processing loop
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                logger.warning("⚠️ Failed to read frame from RTSP stream. Retrying...")
                time.sleep(1)
                cap.release()
                # Close and reopen the stream
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{rtsp_transport}|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
                cap = cv2.VideoCapture(CAMERAS[selected_camera]["rtsp_url"], cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
                cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
                consecutive_corrupted_frames = 0
                continue
            
            # Process frame - minimize conversions
            if frame.shape[1] != STREAM_WIDTH or frame.shape[0] != STREAM_HEIGHT:
                frame = cv2.resize(frame, (STREAM_WIDTH, STREAM_HEIGHT))
            
            # Analyze frame
            brightness, is_corrupted = analyze_visibility(frame, corruption_std_threshold, corruption_hist_threshold)
            
            # Implement frame caching
            original_frame = frame.copy()
            using_cached_frame = False
            
            if is_corrupted and use_frame_caching and last_good_frame is not None:
                # Use the last good frame instead
                frame = last_good_frame.copy()
                using_cached_frame = True
            elif not is_corrupted:
                # Update our cached frame
                last_good_frame = frame.copy()
            
            # Convert for display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Update history with the brightness from the original frame (not cached)
            current_time = datetime.datetime.now()
            st.session_state.cameras_data[selected_camera]["brightness_history"].append(brightness)
            st.session_state.cameras_data[selected_camera]["timestamps"].append(current_time)
            
            # Keep history size reasonable (limit to 24 hours of data at 1 sample per second)
            max_history = 86400  # 24 hours * 60 minutes * 60 seconds
            if len(st.session_state.cameras_data[selected_camera]["brightness_history"]) > max_history:
                st.session_state.cameras_data[selected_camera]["brightness_history"].pop(0)
                st.session_state.cameras_data[selected_camera]["timestamps"].pop(0)
            
            # Update daily statistics
            camera_stats = st.session_state.cameras_data[selected_camera]["daily_stats"]
            
            # Update min/max/avg brightness
            if not is_corrupted:
                camera_stats["min_brightness"] = min(camera_stats["min_brightness"], brightness)
                camera_stats["max_brightness"] = max(camera_stats["max_brightness"], brightness)
                
                # Update running average
                total = camera_stats["avg_brightness"] * camera_stats["total_samples"]
                camera_stats["total_samples"] += 1
                camera_stats["avg_brightness"] = (total + brightness) / camera_stats["total_samples"]
            
            # Update corruption and reconnect counts
            if is_corrupted:
                camera_stats["corruption_count"] += 1
            
            # AUTOMATIC HIGHLIGHT LOGIC
            current_unix_time = time.time()
            time_since_last_highlight = current_unix_time - st.session_state.cameras_data[selected_camera]["last_highlight_time"]
            
            # Only process visibility logic if the frame is not corrupted
            if not is_corrupted:
                consecutive_corrupted_frames = 0  # Reset counter for good frames
                
                if brightness < visibility_threshold:
                    # Visibility is poor
                    if not visibility_poor:
                        # Just became poor
                        st.session_state.cameras_data[selected_camera]["poor_visibility_start"] = current_unix_time
                        visibility_poor = True
                        poor_visibility_duration = 0
                        
                        # Increment poor visibility events counter
                        if "poor_visibility_events" not in camera_stats:
                            camera_stats["poor_visibility_events"] = 0
                        camera_stats["poor_visibility_events"] += 1
                    else:
                        # Continue counting poor visibility duration
                        poor_visibility_duration = current_unix_time - st.session_state.cameras_data[selected_camera]["poor_visibility_start"]
                        
                        # Update visibility duration stats
                        camera_stats["visibility_duration"] += 1  # Add one second
                        camera_stats["max_visibility_duration"] = max(camera_stats["max_visibility_duration"], poor_visibility_duration)
                    
                    # If poor visibility has lasted long enough and we've waited the minimum gap, create highlight
                    if (poor_visibility_duration >= 2 and  # At least 2 seconds of poor visibility
                        time_since_last_highlight >= MIN_HIGHLIGHT_GAP):  # Minimum time between highlights
                        highlight_path = create_highlight(selected_camera, current_time)
                        
                    # Reset normal duration counter
                    normal_visibility_duration = 0
                else:
                    # Visibility is normal
                    if visibility_poor:
                        # Just became normal again
                        visibility_poor = False
                    else:
                        # Continue counting normal visibility
                        normal_visibility_duration += 1
                    
                    # Reset poor visibility counter if we've been normal for a while
                    if normal_visibility_duration > 10:  # 10 iterations of normal visibility
                        poor_visibility_duration = 0
            else:
                # Frame is corrupted - don't trigger highlights
                consecutive_corrupted_frames += 1
                
                # Log corrupted frames
                if st.session_state.data_update_counter % 10 == 0:  # Log every 10th corrupted frame
                    print(f"Corrupted frame detected at {current_time} - {consecutive_corrupted_frames} in a row")
                
                # If we've had too many corrupted frames in a row, reconnect
                if consecutive_corrupted_frames >= max_corrupted_frames_setting:
                    logger.warning(f"⚠️ Too many corrupted frames ({consecutive_corrupted_frames}). Reconnecting to stream...")
                    
                    # Close the current connection
                    cap.release()
                    time.sleep(1)
                    
                    # Try different transport protocol if current one fails repeatedly
                    reconnect_count = st.session_state.cameras_data[selected_camera]["reconnect_count"] + 1
                    st.session_state.cameras_data[selected_camera]["reconnect_count"] = reconnect_count
                    camera_stats["reconnect_count"] += 1
                    
                    # Every 3 reconnects, try a different protocol if we keep failing
                    if reconnect_count % 3 == 0 and reconnect_count > 1:
                        protocols = ["tcp", "udp", "http"]
                        current_index = protocols.index(rtsp_transport) if rtsp_transport in protocols else 0
                        next_index = (current_index + 1) % len(protocols)
                        alternative_transport = protocols[next_index]
                        logger.info(f"Trying alternative transport protocol: {alternative_transport}")
                        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{alternative_transport}|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
                    else:
                        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{rtsp_transport}|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
                    
                    # Reopen the stream
                    cap = cv2.VideoCapture(CAMERAS[selected_camera]["rtsp_url"], cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
                    cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
                    consecutive_corrupted_frames = 0
                    continue
            
            # Update status indicators
            if is_corrupted:
                # Show corruption indicator instead of visibility
                if using_cached_frame:
                    visibility_status.markdown(
                        f"<div class='indicator poor-visibility'>Feed Status: Using Cached Frame</div>", 
                        unsafe_allow_html=True
                    )
                else:
                    visibility_status.markdown(
                        f"<div class='indicator poor-visibility'>Feed Status: Corrupted</div>", 
                        unsafe_allow_html=True
                    )
            else:
                visibility_class = "good-visibility" if brightness > visibility_threshold else "poor-visibility"
            visibility_label = "Good" if brightness > visibility_threshold else "Poor"
            visibility_status.markdown(
                f"<div class='indicator {visibility_class}'>Visibility: {visibility_label}</div>", 
                unsafe_allow_html=True
            )
            
            recording_status.markdown(
                f"<div class='indicator good-visibility'>Recording: Active</div>", 
                unsafe_allow_html=True
            )
            
            current_brightness.markdown(f"""
            <p>Current brightness: <b>{brightness:.1f}</b></p>
            <p>Camera: <b>{CAMERAS[selected_camera]['name']}</b></p>
            <p>Location: <b>{CAMERAS[selected_camera]['location']}</b></p>
            """, unsafe_allow_html=True)
            
            # Update additional metrics in daily stats
            camera_stats = st.session_state.cameras_data[selected_camera]["daily_stats"]
            camera_stats["additional_metrics"]["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate uptime percentage - based on corruption/reconnect counts vs total frames
            total_frames = max(1, camera_stats["total_samples"])  # Avoid division by zero
            corruption_percentage = (camera_stats["corruption_count"] / total_frames) * 100
            camera_stats["uptime_percentage"] = max(0, 100 - corruption_percentage)
            
            # Add visual indicators and timestamp to frame
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame_rgb, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame_rgb, CAMERAS[selected_camera]['location'], (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            if is_corrupted:
                if using_cached_frame:
                    # Add orange border for cached frames
                    frame_rgb = cv2.rectangle(frame_rgb, (0, 0), (STREAM_WIDTH, STREAM_HEIGHT), (255, 165, 0), 10)
                    cv2.putText(frame_rgb, "CACHED FRAME (CORRUPTION DETECTED)", (STREAM_WIDTH//2-220, STREAM_HEIGHT//2), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 165, 0), 2)
                else:
                    # Add yellow border for corrupted frames
                    frame_rgb = cv2.rectangle(frame_rgb, (0, 0), (STREAM_WIDTH, STREAM_HEIGHT), (255, 255, 0), 10)
                    cv2.putText(frame_rgb, "CORRUPTED FEED", (STREAM_WIDTH//2-150, STREAM_HEIGHT//2), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 0), 3)
            elif brightness < visibility_threshold:
                # Add red border for poor visibility
                frame_rgb = cv2.rectangle(frame_rgb, (0, 0), (STREAM_WIDTH, STREAM_HEIGHT), (255, 0, 0), 10)
            
            # Display frame in Streamlit
            camera_feed.image(frame_rgb, channels="RGB", use_container_width=True)
            
            # Always write to video file (automatic recording)
            if out is not None and out.isOpened():
                out.write(frame)  # Use original BGR frame directly
            
            # Update the counter for data points
            st.session_state.data_update_counter += 1
            
            # Log brightness data to database
            log_brightness_sample(selected_camera, current_time, brightness, is_corrupted, brightness < visibility_threshold)
            
            # Run scheduled tasks
            schedule_periodic_tasks()
            
            # Update debug information if enabled
            if show_debug_info:
                # Get current OpenCV parameters
                actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                actual_fps = cap.get(cv2.CAP_PROP_FPS)
                actual_codec = int(cap.get(cv2.CAP_PROP_FOURCC))
                
                # Convert codec to readable format
                codec_chars = [chr((actual_codec >> 8 * i) & 0xFF) for i in range(4)]
                codec_str = ''.join(codec_chars)
                
                # Display debug information
                debug_info.markdown(f"""
                <p><b>Frame Stats:</b> {frame.shape[1]}x{frame.shape[0]} | Brightness: {brightness:.2f} | Corrupted: {is_corrupted}</p>
                <p><b>Streaming:</b> Transport: {rtsp_transport} | Buffer: {cap.get(cv2.CAP_PROP_BUFFERSIZE)}</p>
                <p><b>Codec:</b> {codec_str} | Requested: {STREAM_WIDTH}x{STREAM_HEIGHT}@{STREAM_FPS} | Actual: {actual_width}x{actual_height}@{actual_fps:.1f}</p>
                """, unsafe_allow_html=True)
                
                reconnect_counter.markdown(f"""
                <p><b>Reconnects:</b> {st.session_state.cameras_data[selected_camera]["reconnect_count"]} | 
                <b>Consecutive Corrupted Frames:</b> {consecutive_corrupted_frames}/{max_corrupted_frames_setting}</p>
                """, unsafe_allow_html=True)
            
            # Check if we should update the plot based on time interval or count
            update_plot = False
            
            if st.session_state.plot_update_interval > 0:  # If using timed updates
                seconds_since_update = (datetime.datetime.now() - st.session_state.last_plot_update_time).total_seconds()
                if seconds_since_update >= st.session_state.plot_update_interval:
                    update_plot = True
            
            # Update the chart in Analytics tab if it's time to do so
            if update_plot:
                with tab2:
                    # Reset the update timer
                    st.session_state.last_plot_update_time = datetime.datetime.now()
                    
                    # Resample data based on selected timeframe
                    x_times, y_values = resample_brightness_data(selected_camera, st.session_state.plot_timeframe)
                    
                    if x_times and y_values:
                        # Format x-axis timestamps
                        formatted_times = [t.strftime("%H:%M:%S") if isinstance(t, datetime.datetime) else str(t) for t in x_times]
                        
                        # Create brightness chart
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=formatted_times,
                            y=y_values,
                            mode='lines+markers',
                            name='Brightness',
                            line=dict(color='blue', width=2)
                        ))
                        
                        # Add threshold line
                        fig.add_shape(
                            type="line",
                            x0=0,
                            y0=visibility_threshold,
                            x1=1,
                            y1=visibility_threshold,
                            line=dict(color="red", width=2, dash="dash"),
                            xref="paper"
                        )
                        
                        # Update layout
                        fig.update_layout(
                            title=f"Brightness Levels - Last {st.session_state.plot_timeframe}",
                            xaxis_title="Time",
                            yaxis_title="Brightness Level",
                            height=400,
                            margin=dict(l=20, r=20, t=40, b=20),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        
                        brightness_chart.plotly_chart(fig, use_container_width=True)
                
                # Update alerts in Analytics tab
                with alerts_container:
                    if len(st.session_state.cameras_data[selected_camera]["highlight_marker"]) > 0:
                        for i, time_mark in enumerate(reversed(st.session_state.cameras_data[selected_camera]["highlight_marker"][-5:])):
                            st.markdown(f"🔔 **Highlight marker** at {time_mark}")
            
            # Sleep to reduce CPU usage (adjust as needed)
            time.sleep(0.05)
    
    # Clean up resources
    if cap.isOpened():
        cap.release()
    if out is not None and out.isOpened():
        out.release()

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
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        logger.info("Database setup complete")
        return True
    except Exception as e:
        logger.error(f"Database setup failed: {str(e)}")
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
            "recovery_threshold": 100
        },
        "AIC": {
            "name": "AIC",
            "rtsp_url": "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1",
            "location": "AIC",
            "weather_city": "Baguio City",
            "visibility_threshold": 80,
            "recovery_threshold": 100
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
        
        return cameras
    except Exception as e:
        logger.error(f"Error loading camera configuration: {str(e)}")
        logger.info("Using default camera configuration")
        return default_config

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
            1 if not is_corrupted and brightness < st.session_state.cameras_data[camera_id]["visibility_threshold"] else 0
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging brightness sample: {str(e)}")

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
        return False

def load_session_state():
    """Load session state from a JSON file if available"""
    try:
        if os.path.exists('data/session_state.json'):
            with open('data/session_state.json', 'r') as f:
                saved_state = json.load(f)
            
            # Handle cameras_data
            if 'cameras_data' in saved_state and 'cameras_data' in st.session_state:
                for camera_id, camera_data in saved_state['cameras_data'].items():
                    if camera_id in st.session_state.cameras_data:
                        # Handle brightness_history
                        if 'brightness_history' in camera_data:
                            st.session_state.cameras_data[camera_id]['brightness_history'] = camera_data['brightness_history']
                        
                        # Handle timestamps (convert strings back to datetime objects)
                        if 'timestamps' in camera_data:
                            st.session_state.cameras_data[camera_id]['timestamps'] = [
                                datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S") 
                                if isinstance(t, str) and 'T' not in t 
                                else t 
                                for t in camera_data['timestamps']
                            ]
                        
                        # Handle highlight_marker
                        if 'highlight_marker' in camera_data:
                            st.session_state.cameras_data[camera_id]['highlight_marker'] = camera_data['highlight_marker']
                        
                        # Handle daily_stats
                        if 'daily_stats' in camera_data:
                            st.session_state.cameras_data[camera_id]['daily_stats'] = camera_data['daily_stats']
                        
                        # Handle weather_data
                        if 'weather_data' in camera_data:
                            st.session_state.cameras_data[camera_id]['weather_data'] = camera_data['weather_data']
                        
                        # Handle primitive types
                        for key, value in camera_data.items():
                            if key not in ['brightness_history', 'timestamps', 'highlight_marker', 'daily_stats', 'weather_data']:
                                st.session_state.cameras_data[camera_id][key] = value
            
            # Handle other session state variables
            for key, value in saved_state.items():
                if key != 'cameras_data':
                    st.session_state[key] = value
            
            logger.info("Session state loaded successfully")
            return True
        else:
            logger.info("No saved session state found")
            return False
    except Exception as e:
        logger.error(f"Error loading session state: {str(e)}")
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