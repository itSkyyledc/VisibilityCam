import cv2
import requests
import time
import os
from urllib.parse import urlparse
import socket

# Camera settings
ip = '129.150.48.140'
ports = [8800, 8089]  # The ports we discovered with nmap
user = 'admin'
password = 'AIC_admin'

def test_http_web_interface():
    """Test if we can access a web interface on the discovered ports"""
    print("\nTesting web interfaces...")
    
    for port in ports:
        url = f"http://{ip}:{port}/"
        print(f"Trying web interface at: {url}")
        try:
            response = requests.get(url, auth=(user, password), timeout=5)
            print(f"  Response status: {response.status_code}")
            print(f"  Content type: {response.headers.get('Content-Type', 'unknown')}")
            print(f"  Content size: {len(response.content)} bytes")
            
            # Save the response for examination
            if len(response.content) > 0:
                with open(f"web_interface_port_{port}.html", "wb") as f:
                    f.write(response.content)
                print(f"  Saved response to web_interface_port_{port}.html")
        except requests.RequestException as e:
            print(f"  Error accessing web interface: {e}")

def test_rtsp_streams():
    """Test RTSP streaming on different ports and paths"""
    print("\nTesting RTSP streams...")
    
    # Configure OpenCV for better RTSP handling
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
    
    # Common RTSP paths for IP cameras including V380
    rtsp_paths = [
        "/",                           # Root
        "/h264/ch1/main/av_stream",    # Common format
        "/live/ch00_0",                # Another common format
        "/cam/realmonitor",            # Alternative format
        "/live/ch0",                   # Simple channel format
        "/v380media",                  # V380 specific
        "/v380/live",                  # V380 specific
        "/Streaming/Channels/1",       # Hikvision format
        "/Streaming/Channels/101",     # Hikvision format
        "/onvif1",                     # ONVIF format
        "/media/video1",               # Generic media format
        "/video1",                     # Simple video format
        "/stream1",                    # Simple stream format
        "/videostream.asf",            # ASF format
        "/videostream.cgi",            # CGI format
    ]
    
    # Test each port and path combination
    for port in ports:
        for path in rtsp_paths:
            url = f"rtsp://{user}:{password}@{ip}:{port}{path}"
            print(f"\nTrying RTSP URL: {url}")
            
            try:
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                time.sleep(2)  # Give some time to connect
                
                if not cap.isOpened():
                    print("  ✗ Failed to open stream")
                    cap.release()
                    continue
                
                print("  ✓ Successfully connected!")
                
                # Try to read a frame
                ret, frame = cap.read()
                if not ret:
                    print("  ✗ Failed to read frame")
                else:
                    print(f"  ✓ Successfully read frame: {frame.shape[1]}x{frame.shape[0]}")
                    
                    # Save frame to file
                    filename = f"stream_frame_port{port}_path{path.replace('/', '_')}.jpg"
                    cv2.imwrite(filename, frame)
                    print(f"  ✓ Saved test frame to {filename}")
                    
                    # Save working URL to file
                    with open("working_stream_url.txt", "w") as f:
                        f.write(url)
                    print(f"  ✓ Saved working URL to working_stream_url.txt")
                    
                    print(f"\n✓✓✓ SUCCESS! FOUND WORKING STREAM URL: {url} ✓✓✓")
                    return url  # Return on first success
                
                cap.release()
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
            
            # Short pause between attempts
            time.sleep(0.5)
    
    return None

def test_http_streams():
    """Test HTTP streaming on different ports and paths"""
    print("\nTesting HTTP streams...")
    
    # Common HTTP paths for IP camera streams
    http_paths = [
        "/videostream.cgi",
        "/mjpg/video.mjpg",
        "/video",
        "/video.cgi",
        "/video.mjpg",
        "/cgi-bin/mjpeg",
        "/cgi-bin/video.cgi",
        "/snapshot.cgi",
        "/cgi-bin/snapshot.cgi",
        "/live/stream",
        "/v380/live/video",
        "/streaming/video",
        "/api/v1/stream",
    ]
    
    # Test each port and path combination
    for port in ports:
        for path in http_paths:
            url = f"http://{user}:{password}@{ip}:{port}{path}"
            print(f"\nTrying HTTP URL: {url}")
            
            try:
                # First try a direct request to see if the endpoint exists
                direct_url = f"http://{ip}:{port}{path}"
                response = requests.get(direct_url, auth=(user, password), timeout=5, stream=True)
                
                if response.status_code == 200:
                    print(f"  ✓ Got successful response: {response.status_code}")
                    content_type = response.headers.get('Content-Type', '')
                    print(f"  Content type: {content_type}")
                    
                    # If it's an image, save it
                    if 'image' in content_type:
                        filename = f"http_image_port{port}_path{path.replace('/', '_')}.jpg"
                        with open(filename, 'wb') as f:
                            f.write(response.content)
                        print(f"  ✓ Saved image to {filename}")
                    
                    # Try to open with OpenCV if it might be a video stream
                    if 'video' in content_type or 'stream' in content_type or 'mjpeg' in content_type:
                        cap = cv2.VideoCapture(url)
                        if cap.isOpened():
                            print("  ✓ Successfully opened as video stream")
                            ret, frame = cap.read()
                            if ret:
                                print(f"  ✓ Successfully read frame: {frame.shape[1]}x{frame.shape[0]}")
                                # Save frame
                                filename = f"http_stream_frame_port{port}_path{path.replace('/', '_')}.jpg"
                                cv2.imwrite(filename, frame)
                                print(f"  ✓ Saved test frame to {filename}")
                                
                                # Save working URL
                                with open("working_stream_url.txt", "w") as f:
                                    f.write(url)
                                print(f"  ✓ Saved working URL to working_stream_url.txt")
                                
                                print(f"\n✓✓✓ SUCCESS! FOUND WORKING STREAM URL: {url} ✓✓✓")
                                cap.release()
                                return url
                            else:
                                print("  ✗ Failed to read frame")
                            cap.release()
                        else:
                            print("  ✗ Failed to open as video stream")
                
            except requests.RequestException as e:
                print(f"  ✗ Error with HTTP request: {str(e)}")
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
            
            # Short pause between attempts
            time.sleep(0.5)
    
    return None

def probe_v380_port_8089():
    """Special probe for port 8089 which might be V380's proprietary protocol"""
    print("\nProbing V380 proprietary protocol on port 8089...")
    
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        print(f"Connecting to {ip}:8089...")
        sock.connect((ip, 8089))
        print(f"✓ Connected to {ip}:8089")
        
        # Try different protocol probes
        
        # Probe 1: Simple HTTP-like request
        print("Sending HTTP-like probe...")
        sock.send(b"GET / HTTP/1.1\r\nHost: " + ip.encode() + b"\r\n\r\n")
        response = sock.recv(4096)
        print(f"Received {len(response)} bytes")
        print(f"Response (preview): {response[:100]}")
        
        with open("port_8089_probe1.bin", "wb") as f:
            f.write(response)
        print("✓ Saved probe response to port_8089_probe1.bin")
        
        # Probe 2: V380-specific probe (based on common patterns)
        print("Sending V380-specific probe...")
        # This is a guess at what a V380 protocol packet might look like
        probe = bytearray([
            0x56, 0x33, 0x38, 0x30,  # V380 in ASCII
            0x01, 0x00, 0x00, 0x00,  # Command type (guessing)
            0x00, 0x00, 0x00, 0x00   # Payload length (empty)
        ])
        sock.send(probe)
        response = sock.recv(4096)
        print(f"Received {len(response)} bytes")
        print(f"Response (hex): {response.hex()[:100]}")
        
        with open("port_8089_probe2.bin", "wb") as f:
            f.write(response)
        print("✓ Saved probe response to port_8089_probe2.bin")
        
        # Close socket
        sock.close()
    except Exception as e:
        print(f"✗ Error during port 8089 probe: {str(e)}")

def test_mjpeg_stream():
    """Test MJPEG streaming on both ports"""
    print("\nTesting MJPEG streams...")
    
    mjpeg_paths = [
        "/mjpg/video.mjpg",
        "/video.mjpg",
        "/mjpegstream",
        "/mjpeg/stream",
        "/cgi-bin/mjpeg",
        "/v380/mjpeg",
    ]
    
    for port in ports:
        for path in mjpeg_paths:
            url = f"http://{ip}:{port}{path}"
            print(f"\nTrying MJPEG URL: {url}")
            
            try:
                cap = cv2.VideoCapture(url)
                if cap.isOpened():
                    print("  ✓ Successfully opened MJPEG stream")
                    ret, frame = cap.read()
                    if ret:
                        print(f"  ✓ Successfully read frame: {frame.shape[1]}x{frame.shape[0]}")
                        filename = f"mjpeg_frame_port{port}_path{path.replace('/', '_')}.jpg"
                        cv2.imwrite(filename, frame)
                        print(f"  ✓ Saved test frame to {filename}")
                        
                        with open("working_stream_url.txt", "w") as f:
                            f.write(url)
                        print(f"  ✓ Saved working URL to working_stream_url.txt")
                        
                        print(f"\n✓✓✓ SUCCESS! FOUND WORKING MJPEG STREAM: {url} ✓✓✓")
                        cap.release()
                        return url
                    else:
                        print("  ✗ Failed to read frame")
                    cap.release()
                else:
                    print("  ✗ Failed to open MJPEG stream")
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
            
            time.sleep(0.5)
    
    return None

def update_config_with_url(url):
    """Update the config with the working URL"""
    print(f"\nTo use this URL in your application, update src/config/settings.py with:")
    print(f"""
"V380 Camera": {{
    "name": "V380 Camera",
    "location": "Remote Location",
    "camera_type": "v380",
    "ip": "{ip}",
    "port": "{url.split(':')[2].split('/')[0]}",
    "username": "{user}",
    "password": "{password}",
    "rtsp_url": "{url if url.startswith('rtsp://') else ''}",  # Only for RTSP
    "http_url": "{url if url.startswith('http://') else ''}",  # Only for HTTP
    "weather_city": "Manila",
    "visibility_threshold": 30,
    "recovery_threshold": 50,
    "stream_settings": {{
        "width": 1280,
        "height": 720,
        "fps": 15,
        "buffer_size": 3,
        "rtsp_transport": "tcp",
        "connection_timeout": 10,
        "retry_interval": 30,
        "max_retries": 3
    }}
}}
    """)
    
    # Also save this to a file for easy reference
    with open("camera_config_update.txt", "w") as f:
        f.write(f"""
"V380 Camera": {{
    "name": "V380 Camera",
    "location": "Remote Location",
    "camera_type": "v380",
    "ip": "{ip}",
    "port": "{url.split(':')[2].split('/')[0]}",
    "username": "{user}",
    "password": "{password}",
    "rtsp_url": "{url if url.startswith('rtsp://') else ''}",  # Only for RTSP
    "http_url": "{url if url.startswith('http://') else ''}",  # Only for HTTP
    "weather_city": "Manila",
    "visibility_threshold": 30,
    "recovery_threshold": 50,
    "stream_settings": {{
        "width": 1280,
        "height": 720,
        "fps": 15,
        "buffer_size": 3,
        "rtsp_transport": "tcp",
        "connection_timeout": 10,
        "retry_interval": 30,
        "max_retries": 3
    }}
}}
        """)
    print("This configuration has been saved to camera_config_update.txt")

if __name__ == "__main__":
    print(f"V380 Camera Stream Test - IP: {ip}, Ports: {ports}")
    print("=================================================")
    
    # First, test HTTP web interface on both ports
    test_http_web_interface()
    
    # Then probe port 8089 which might be the V380 proprietary protocol
    probe_v380_port_8089()
    
    # Test for streams in order of likelihood
    working_url = None
    
    if not working_url:
        working_url = test_rtsp_streams()
    
    if not working_url:
        working_url = test_http_streams()
    
    if not working_url:
        working_url = test_mjpeg_stream()
    
    if working_url:
        update_config_with_url(working_url)
    else:
        print("\n⚠️ Could not find a working stream URL")
        print("""
Suggestions:
1. Check if the camera's web interface is accessible at http://129.150.48.140:8800 or http://129.150.48.140:8089
2. Try capturing Wireshark traffic while using the V380 Pro app
3. Check if the camera requires a specific app or protocol for streaming
4. Verify the username/password combination
        """) 