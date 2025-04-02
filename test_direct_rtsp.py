import cv2
import os
import time

# Configure OpenCV for better RTSP handling
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"

# Camera settings from Camtest.py
ip = '129.150.48.140'
port = 8800
user = 'admin'
password = 'AIC_admin'

# Common RTSP URL formats to try
rtsp_urls = [
    # Standard formats
    f"rtsp://{user}:{password}@{ip}:{port}/",
    f"rtsp://{user}:{password}@{ip}:{port}/live",
    f"rtsp://{user}:{password}@{ip}:{port}/stream",
    f"rtsp://{user}:{password}@{ip}:{port}/media",
    
    # Hikvision formats
    f"rtsp://{user}:{password}@{ip}:{port}/Streaming/Channels/1",
    f"rtsp://{user}:{password}@{ip}:{port}/Streaming/Channels/101",
    f"rtsp://{user}:{password}@{ip}:{port}/Streaming/Channels/102",
    
    # Axis formats
    f"rtsp://{user}:{password}@{ip}:{port}/axis-media/media.amp",
    f"rtsp://{user}:{password}@{ip}:{port}/mpeg4/media.amp",
    
    # Common manufacturer formats
    f"rtsp://{user}:{password}@{ip}:{port}/h264",
    f"rtsp://{user}:{password}@{ip}:{port}/h264/media.amp",
    f"rtsp://{user}:{password}@{ip}:{port}/h264_stream",
    f"rtsp://{user}:{password}@{ip}:{port}/av0_0",
    f"rtsp://{user}:{password}@{ip}:{port}/cam/realmonitor?channel=1&subtype=0",
    
    # Try port 554 (standard RTSP port) with various paths
    f"rtsp://{user}:{password}@{ip}:554/",
    f"rtsp://{user}:{password}@{ip}:554/Streaming/Channels/1",
    f"rtsp://{user}:{password}@{ip}:554/h264/media.amp",
]

print("Testing direct RTSP connections...")
print("This may take several minutes as each connection attempt can timeout")

for i, url in enumerate(rtsp_urls):
    print(f"\n[{i+1}/{len(rtsp_urls)}] Testing: {url}")
    
    try:
        # Create capture object with a shorter timeout
        start_time = time.time()
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        
        # Set a short timeout for connection attempts
        if time.time() - start_time > 10:
            print("  ✗ Connection taking too long, skipping")
            cap.release()
            continue
        
        if not cap.isOpened():
            print("  ✗ Failed to open stream")
            cap.release()
            continue
            
        print("  ✓ Successfully connected!")
        
        # Try to read a frame
        print("  Attempting to read frame...")
        ret, frame = cap.read()
        
        if not ret:
            print("  ✗ Failed to read frame")
        else:
            print(f"  ✓ Successfully read frame: {frame.shape[1]}x{frame.shape[0]}")
            
            # Save frame to file
            filename = f"rtsp_test_frame_{i+1}.jpg"
            cv2.imwrite(filename, frame)
            print(f"  ✓ Saved test frame to {filename}")
            
            # Save working URL to file
            with open("working_rtsp_url.txt", "w") as f:
                f.write(url)
            print(f"  ✓ Saved working URL to working_rtsp_url.txt")
            
            # Update camera config in settings
            print("\n✓✓✓ FOUND WORKING CAMERA CONNECTION! ✓✓✓")
            print(f"Please update the RTSP URL in your settings.py to: {url}")
            
            # Break after finding a working URL
            break
            
        # Always release the capture object
        cap.release()
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
    
    # Short pause between attempts
    time.sleep(0.5)
    
print("\nTesting complete.")
print("If no working connection was found, try using an ONVIF Device Manager or IP Camera Viewer software")
print("to determine the exact connection string for your camera.") 