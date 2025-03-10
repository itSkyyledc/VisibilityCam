import cv2
import time
import numpy as np
import streamlit as st
import requests
import datetime
import os

# RTSP Stream URL
RTSP_URL = "rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1"
FRAME_WIDTH, FRAME_HEIGHT = 640, 360

# Visibility Detection Thresholds
VISIBILITY_THRESHOLD = 80
RECOVERY_THRESHOLD = 100

# OpenWeatherMap API
API_KEY = "YOUR_OPENWEATHERMAP_API_KEY"
CITY = "Quezon City"
WEATHER_URL = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric"

# Create recordings directory if it doesn't exist
os.makedirs("recordings", exist_ok=True)

# Generate a unique filename for today's recording
today_date = datetime.datetime.now().strftime("%Y-%m-%d")
recording_filename = f"recordings/recording_{today_date}.mp4"

def get_weather():
    """Fetch weather data from OpenWeatherMap API."""
    try:
        response = requests.get(WEATHER_URL)
        data = response.json()
        weather = {
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "condition": data["weather"][0]["description"].capitalize()
        }
    except Exception:
        weather = {"temperature": "N/A", "humidity": "N/A", "condition": "Error fetching weather"}
    return weather

def analyze_visibility(frame):
    """Calculate the brightness of the frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return np.mean(gray)

st.title("RTSP Camera Dashboard")
weather = get_weather()

# Tabs for different sections
tab1, tab2 = st.tabs(["📡 Live Stream", "📂 Recordings & Highlights"])

# --- 📡 Live Stream Tab ---
with tab1:
    st.subheader("🌤 Weather Information")
    st.write(f"Temperature: {weather['temperature']}°C")
    st.write(f"Humidity: {weather['humidity']}%")
    st.write(f"Condition: {weather['condition']}")

    st.subheader("📷 RTSP Stream & Visibility Detection")
    frame_holder = st.empty()

    # Open RTSP Stream
    cap = cv2.VideoCapture(RTSP_URL)

    # Setup video writer for recording
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # Codec for MP4
    out = cv2.VideoWriter(recording_filename, fourcc, 20.0, (FRAME_WIDTH, FRAME_HEIGHT))

    if not cap.isOpened():
        st.error("❌ Failed to connect to RTSP stream. Check your URL or network settings.")
    else:
        while True:
            ret, frame = cap.read()
            if not ret:
                st.error("❌ Failed to read frame from RTSP stream.")
                break
            
            # Resize and convert color
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Analyze brightness
            brightness = analyze_visibility(frame)

            # Overlay brightness info
            cv2.putText(frame, f"Brightness: {brightness:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # Save frame to video file
            out.write(frame)

            # Display frame in Streamlit
            frame_holder.image(frame_rgb, channels="RGB", use_container_width=True)

    cap.release()
    out.release()

# --- 📂 Recordings & Highlights Tab ---
with tab2:
    st.subheader("📂 Recorded Sessions")
    
    # List recorded files
    recordings = sorted(os.listdir("recordings"), reverse=True)
    selected_file = st.selectbox("Select a recording:", recordings if recordings else ["No recordings available"])

    # Playback recorded video
    if selected_file != "No recordings available":
        st.video(f"recordings/{selected_file}")
