import cv2
import time
import os

# Set FFmpeg options for better reliability
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"

# Common RTSP ports to try
rtsp_ports = [554, 1554, 8554, 10554, 8000, 8080, 8800, 7070]

# Common RTSP URL paths
rtsp_paths = [
    "",  # Base URL
    "/Streaming/Channels/101",  # Common Hikvision format
    "/live/ch00_0",  # Another common format
    "/h264Preview_01_main",  # Common Dahua format
    "/profile1/media.smp",  # Common ONVIF format
    "/cam/realmonitor",  # Alternative format
    "/live/stream1",  # Generic stream format
]

# Try each port and path combination
for port in rtsp_ports:
    for path in rtsp_paths:
        url = f"rtsp://admin:AIC_admin@129.150.48.140:{port}{path}"
        print(f"\nTrying URL: {url}")
        
        try:
            # Set a short timeout for quicker testing
            start_time = time.time()
            
            # Open the stream
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            
            # Check if connection was successful within timeout
            if not cap.isOpened():
                print("  ✗ Failed to open stream")
                cap.release()
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
                filename = f"test_frame_port{port}_path{path.replace('/', '_')}.jpg"
                cv2.imwrite(filename, frame)
                print(f"  ✓ Saved test frame to {filename}")
                
                # Try to read one more frame to confirm stable connection
                ret, frame = cap.read()
                if ret:
                    print("  ✓ Successfully read a second frame")
                else:
                    print("  ✗ Failed to read a second frame")
            
            # Release capture
            cap.release()
            
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            
        # Limit test time per URL to 5 seconds
        elapsed = time.time() - start_time
        if elapsed < 5:
            time.sleep(0.1)  # Short sleep between attempts
    
print("\nTesting complete.") 