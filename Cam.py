import cv2
import time
import os
import numpy as np
from collections import deque

# RTSP Stream URL (Replace with correct login details)
RTSP_URL ="rtsp://buth:4ytkfe@192.168.1.210/live/ch00_1" 
#"rtsp://ECCEF324-thesis:ilovemyproject@192.168.1.118:554/stream1"
#rtsp://username:password@ip_address/live/ch00_1
# 100.112.240.104 
#rtsp://ECCEF324-thesis:ilovemyproject@192.168.1.118/live/ch00_1
# Video Parameters
FRAME_WIDTH, FRAME_HEIGHT = 1280, 720
FPS = 20

# Visibility Detection Thresholds
VISIBILITY_THRESHOLD = 80
RECOVERY_THRESHOLD = 100
MIN_HIGHLIGHT_GAP = 10  # Seconds between highlights
POST_RECORD_DURATION = 20  # Seconds after visibility restores

# Buffer for past and future frames
BUFFER_SIZE = 20 * FPS  # 20 seconds
frame_buffer = deque(maxlen=BUFFER_SIZE)

# Recording Control
highlight_triggered = False
highlight_writer = None
last_highlight_time = 0
post_record_frames = 0  # Frames to keep recording after recovery

# Output Directory
SAVE_DIR = "recordings/"
os.makedirs(SAVE_DIR, exist_ok=True)

# Create Continuous Session Recorder
session_filename = os.path.join(SAVE_DIR, "session.mp4")
session_writer = cv2.VideoWriter(session_filename, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (FRAME_WIDTH, FRAME_HEIGHT))

def analyze_visibility(frame):
    """Analyze frame brightness."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return np.mean(gray)

def save_video(writer, frame):
    """Write frame to video file."""
    if writer is not None:
        writer.write(frame)

def create_video_writer(filename):
    """Create video writer with fallback to AVI if MP4 fails."""
    filepath = os.path.join(SAVE_DIR, filename)
    writer = cv2.VideoWriter(filepath, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (FRAME_WIDTH, FRAME_HEIGHT))
    return writer if writer.isOpened() else None

# Open Video Stream
cap = cv2.VideoCapture(RTSP_URL)
if not cap.isOpened():
    print("Error: Cannot open RTSP stream.")
    exit()

print("🎥 RTSP stream started... Press 'q' to exit.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to retrieve frame.")
            break

        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        frame_buffer.append(frame)

        # Continuous Recording
        save_video(session_writer, frame)

        brightness = analyze_visibility(frame)
        print(f"🔆 Brightness: {brightness:.2f}")

        # Highlight Trigger
        current_time = time.time()
        if brightness < VISIBILITY_THRESHOLD and not highlight_triggered:
            if current_time - last_highlight_time > MIN_HIGHLIGHT_GAP:
                print("⚠️ Visibility dropped! Creating highlight...")

                # Create highlight writer
                highlight_filename = f"highlight_{int(current_time)}.mp4"
                highlight_writer = create_video_writer(highlight_filename)

                # Save past frames
                for past_frame in frame_buffer:
                    save_video(highlight_writer, past_frame)

                highlight_triggered = True
                last_highlight_time = current_time
                post_record_frames = POST_RECORD_DURATION * FPS  # Extend recording

        # Continue recording if highlight is active
        if highlight_triggered:
            save_video(highlight_writer, frame)
            post_record_frames -= 1

        # Stop highlight when brightness recovers AND post-recording is done
        if highlight_triggered and brightness > RECOVERY_THRESHOLD and post_record_frames <= 0:
            print("✅ Visibility restored. Stopping highlight recording.")
            highlight_writer.release()
            highlight_writer = None
            highlight_triggered = False

        # Display Stream
        cv2.imshow("RTSP Stream", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n🔴 Stopping Recording... Saving Files...")
            break

except KeyboardInterrupt:
    print("\n🔴 Stopping Recording due to Keyboard Interrupt...")

finally:
    cap.release()
    session_writer.release()
    if highlight_writer:
        highlight_writer.release()
    cv2.destroyAllWindows()
    print("✅ All recordings saved. Exiting.")
