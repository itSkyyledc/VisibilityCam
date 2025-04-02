import cv2
import time
import os

# Set FFmpeg options for better reliability
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"

# RTSP URL with different variants to try
rtsp_urls = [
    "rtsp://admin:AIC_admin@129.150.48.140:8800",  # Base URL
    "rtsp://admin:AIC_admin@129.150.48.140:8800/Streaming/Channels/101",  # Common Hikvision format
    "rtsp://admin:AIC_admin@129.150.48.140:8800/live/ch00_0",  # Another common format
    "rtsp://admin:AIC_admin@129.150.48.140:8800/h264Preview_01_main",  # Common Dahua format
    "rtsp://admin:AIC_admin@129.150.48.140:8800/profile1/media.smp"  # Common ONVIF format
]

# Try each URL
for i, url in enumerate(rtsp_urls):
    print(f"\nTrying URL {i+1}: {url}")
    try:
        # Open the stream
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        
        # Check if connection was successful
        if not cap.isOpened():
            print("  ✗ Failed to open stream")
            continue
            
        print("  ✓ Successfully connected to stream")
        
        # Try to read a frame
        print("  Attempting to read frame...")
        ret, frame = cap.read()
        
        if not ret:
            print("  ✗ Failed to read frame")
        else:
            print(f"  ✓ Successfully read a frame ({frame.shape[1]}x{frame.shape[0]})")
            
            # Save frame to file
            filename = f"test_frame_{i+1}.jpg"
            cv2.imwrite(filename, frame)
            print(f"  ✓ Saved test frame to {filename}")
            
            # Try to read a few more frames to confirm stable connection
            frame_count = 1
            success_count = 0
            start_time = time.time()
            
            while frame_count < 10 and time.time() - start_time < 10:
                ret, frame = cap.read()
                if ret:
                    success_count += 1
                frame_count += 1
                time.sleep(0.5)
                
            print(f"  ✓ Successfully read {success_count} out of {frame_count-1} additional frames")
        
        # Release capture
        cap.release()
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
    
print("\nTesting complete.") 