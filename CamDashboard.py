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

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
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
</style>
""", unsafe_allow_html=True)

# Configuration variables
RTSP_URL = "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1"
FRAME_WIDTH, FRAME_HEIGHT = 1280, 720
VISIBILITY_THRESHOLD = 80
RECOVERY_THRESHOLD = 100

# File paths setup
os.makedirs("recordings", exist_ok=True)
os.makedirs("highlights", exist_ok=True)
today_date = datetime.datetime.now().strftime("%Y-%m-%d")
recording_filename = f"recordings/recording_{today_date}_{datetime.datetime.now().strftime('%H-%M-%S')}.mp4"

# Load API key securely
try:
    with open('api_key.txt', 'r') as file:
        API_KEY = file.read().strip()
    CITY = "Quezon City"
    WEATHER_URL = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric"
except FileNotFoundError:
    logger.warning("⚠️ API key file not found. Weather data will not be available.")
    API_KEY = None

# Session state initialization
if 'brightness_history' not in st.session_state:
    st.session_state.brightness_history = []
if 'timestamps' not in st.session_state:
    st.session_state.timestamps = []
if 'recording_active' not in st.session_state:
    st.session_state.recording_active = True  # Always active now
if 'highlight_marker' not in st.session_state:
    st.session_state.highlight_marker = []
if 'data_update_counter' not in st.session_state:
    st.session_state.data_update_counter = 0
if 'last_plot_update_time' not in st.session_state:
    st.session_state.last_plot_update_time = datetime.datetime.now()
if 'plot_timeframe' not in st.session_state:
    st.session_state.plot_timeframe = "1 minute"
if 'plot_update_interval' not in st.session_state:
    st.session_state.plot_update_interval = 5  # Update plot every 5 data points
if 'poor_visibility_start' not in st.session_state:
    st.session_state.poor_visibility_start = None
if 'last_highlight_time' not in st.session_state:
    st.session_state.last_highlight_time = time.time() - 60  # Initialize with timestamp 60 seconds ago

def get_weather():
    """Fetch weather data from OpenWeatherMap API."""
    if not API_KEY:
        return {"temperature": "N/A", "humidity": "N/A", "condition": "API key missing", "icon": "❓"}
    
    try:
        response = requests.get(WEATHER_URL, timeout=5)
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
            "icon": icon
        }
    except Exception as e:
        logger.warning(f"Weather API error: {str(e)}")
        weather = {"temperature": "N/A", "humidity": "N/A", "condition": "Error fetching weather", "icon": "❓"}
    
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

def create_highlight(start_time, duration=10):
    """Create a highlight clip from the main recording."""
    highlight_filename = f"highlights/highlight_{today_date}_{datetime.datetime.now().strftime('%H-%M-%S')}.mp4"
    st.session_state.highlight_marker.append(datetime.datetime.now().strftime("%H:%M:%S"))
    
    # Log the highlight creation in the session state
    st.session_state.last_highlight_time = time.time()
    
    return highlight_filename

def resample_brightness_data(timeframe):
    """Resample brightness data based on selected timeframe."""
    if not st.session_state.timestamps or not st.session_state.brightness_history:
        return [], []
    
    # Create DataFrame from session state data
    df = pd.DataFrame({
        'timestamp': st.session_state.timestamps,
        'brightness': st.session_state.brightness_history
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

# Camera selection (for future expansion)
camera_options = {"Main Entrance": RTSP_URL, "Alternative Camera": RTSP_URL}
selected_camera = st.sidebar.selectbox("Select Camera", list(camera_options.keys()))

# Visibility threshold adjustment
visibility_threshold = st.sidebar.slider(
    "Visibility Threshold", 
    min_value=50, 
    max_value=150, 
    value=VISIBILITY_THRESHOLD,
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
st.markdown("<h1 class='main-header'>Camera Surveillance Dashboard</h1>", unsafe_allow_html=True)

# Create tabs - now with separate tabs for recordings and highlights
tab1, tab2, tab3, tab4 = st.tabs(["📡 Live Monitoring", "📊 Analytics", "📼 Recordings", "🔍 Highlights"])

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
        weather = get_weather()
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<h2 class='sub-header'>{weather['icon']} Weather</h2>", unsafe_allow_html=True)
        st.metric("Temperature", f"{weather['temperature']}°C")
        st.metric("Humidity", f"{weather['humidity']}%")
        st.markdown(f"<p><b>Condition:</b> {weather['condition']}</p>", unsafe_allow_html=True)
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
    st.markdown("<h2 class='sub-header'>📈 Visibility Trends</h2>", unsafe_allow_html=True)
    st.write(f"Showing data for the last **{st.session_state.plot_timeframe}** (resampled)")
    
    # Create placeholder for chart
    brightness_chart = st.empty()
    
    # Add manual refresh button when using manual refresh
    if st.session_state.plot_update_interval == -1:
        if st.button("Refresh Plot"):
            st.session_state.last_plot_update_time = datetime.datetime.now()
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>⚠️ Recent Alerts</h2>", unsafe_allow_html=True)
    alerts_container = st.container()
    st.markdown("</div>", unsafe_allow_html=True)

# --- 📼 Recordings Tab (now separate) ---
with tab3:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>📼 Recorded Sessions</h2>", unsafe_allow_html=True)
    
    # Get and display recordings
    recordings = sorted(os.listdir("recordings"), reverse=True) if os.path.exists("recordings") and os.listdir("recordings") else []
    
    if not recordings:
        st.info("No recordings available yet. Start recording to capture footage.")
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
                    recording_date = selected_file.split("_")[1].split(".")[0]
                    st.info(f"Recording date: {recording_date}")
                except:
                    pass
                
                # Get file size
                file_path = os.path.join("recordings", selected_file)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
                st.info(f"File size: {file_size:.2f} MB")
        
        with col2:
            if selected_file:
                st.video(f"recordings/{selected_file}")
    
    st.markdown("</div>", unsafe_allow_html=True)

# --- 🔍 Highlights Tab (now separate) ---
with tab4:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='sub-header'>🔍 Highlight Clips</h2>", unsafe_allow_html=True)
    
    # Get and display highlights
    highlights = sorted(os.listdir("highlights"), reverse=True) if os.path.exists("highlights") and os.listdir("highlights") else []
    
    if not highlights:
        st.info("No highlights available yet. Use the 'Mark Highlight' button to save important moments.")
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
                    pass
                
                # Get file size
                file_path = os.path.join("highlights", selected_highlight)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
                st.info(f"File size: {file_size:.2f} MB")
                
                # Add option to add a note to the highlight
                highlight_note = st.text_input("Add a note to this highlight")
                if st.button("Save Note"):
                    st.success("Note saved successfully!")
        
        with col2:
            if selected_highlight:
                st.video(f"highlights/{selected_highlight}")
    
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
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    
    # Apply additional capture properties to improve HEVC handling
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Smallest buffer for less delay
    
    # Set resolution and framerate
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
    
    # Setup video writer for recording - always active
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Same codec as Cam.py
    out = cv2.VideoWriter(recording_filename, fourcc, STREAM_FPS, (FRAME_WIDTH, FRAME_HEIGHT))
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
                cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
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
            st.session_state.brightness_history.append(brightness)
            st.session_state.timestamps.append(current_time)
            
            # Keep history size reasonable (limit to 24 hours of data at 1 sample per second)
            max_history = 86400  # 24 hours * 60 minutes * 60 seconds
            if len(st.session_state.brightness_history) > max_history:
                st.session_state.brightness_history.pop(0)
                st.session_state.timestamps.pop(0)
            
            # AUTOMATIC HIGHLIGHT LOGIC
            current_unix_time = time.time()
            time_since_last_highlight = current_unix_time - st.session_state.last_highlight_time
            
            # Only process visibility logic if the frame is not corrupted
            if not is_corrupted:
                consecutive_corrupted_frames = 0  # Reset counter for good frames
                
                if brightness < visibility_threshold:
                    # Visibility is poor
                    if not visibility_poor:
                        # Just became poor
                        st.session_state.poor_visibility_start = current_unix_time
                        visibility_poor = True
                        poor_visibility_duration = 0
                    else:
                        # Continue counting poor visibility duration
                        poor_visibility_duration = current_unix_time - st.session_state.poor_visibility_start
                    
                    # If poor visibility has lasted long enough and we've waited the minimum gap, create highlight
                    if (poor_visibility_duration >= 2 and  # At least 2 seconds of poor visibility
                        time_since_last_highlight >= MIN_HIGHLIGHT_GAP):  # Minimum time between highlights
                        highlight_path = create_highlight(current_time)
                        
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
                    reconnect_count = getattr(st.session_state, 'reconnect_count', 0) + 1
                    st.session_state.reconnect_count = reconnect_count
                    
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
                    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
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
                f"<div class='indicator good-visibility'>Recording: Always Active</div>", 
                unsafe_allow_html=True
            )
            
            current_brightness.markdown(f"<p>Current brightness: <b>{brightness:.1f}</b></p>", unsafe_allow_html=True)
            
            # Add visual indicators and timestamp to frame
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame_rgb, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
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
                <p><b>Streaming:</b> Transport: {rtsp_transport} | URL Format: {url_format} | Buffer: {cap.get(cv2.CAP_PROP_BUFFERSIZE)}</p>
                <p><b>Codec:</b> {codec_str} | Requested: {STREAM_WIDTH}x{STREAM_HEIGHT}@{STREAM_FPS} | Actual: {actual_width}x{actual_height}@{actual_fps:.1f}</p>
                """, unsafe_allow_html=True)
                
                reconnect_counter.markdown(f"""
                <p><b>Reconnects:</b> {getattr(st.session_state, 'reconnect_count', 0)} | 
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
                    x_times, y_values = resample_brightness_data(st.session_state.plot_timeframe)
                    
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
                    if len(st.session_state.highlight_marker) > 0:
                        for i, time_mark in enumerate(reversed(st.session_state.highlight_marker[-5:])):
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