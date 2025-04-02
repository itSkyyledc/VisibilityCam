import requests
import cv2
import socket
import time
import json
import threading
import sys
import os
from urllib.parse import urlparse

# Camera settings
ip = '129.150.48.140'
port = 8800
user = 'admin'
password = 'AIC_admin'

def test_http_endpoints():
    """Test common HTTP endpoints that V380 cameras might expose"""
    print("Testing HTTP endpoints...")
    
    base_urls = [
        f"http://{ip}:{port}",
        f"http://{ip}:80",
        f"http://{ip}:8080",
    ]
    
    endpoints = [
        "/",
        "/cgi-bin/hi3510/snap.cgi?&-getstream&-chn=1",
        "/videostream.cgi?user={user}&pwd={password}",
        "/api/v1/snap.cgi",
        "/v380.htm",
        "/device.rsp?opt=get",
        "/get_status.cgi",
        "/snapshot.jpg",
        "/live/stream",
        "/streaming/video",
    ]
    
    for base_url in base_urls:
        print(f"\nTrying base URL: {base_url}")
        for endpoint in endpoints:
            url = base_url + endpoint.format(user=user, password=password)
            try:
                print(f"  Testing: {url}")
                response = requests.get(url, auth=(user, password), timeout=5)
                print(f"  ✓ Got response: {response.status_code}")
                
                # Check if response looks like an image or video
                content_type = response.headers.get('Content-Type', '')
                if 'image' in content_type or 'video' in content_type or len(response.content) > 1000:
                    print(f"  ✓ Received media content ({len(response.content)} bytes, {content_type})")
                    
                    # Save content for inspection
                    extension = '.jpg' if 'image' in content_type else '.data'
                    parsed_url = urlparse(url)
                    path = parsed_url.path.replace('/', '_')
                    if not path:
                        path = "root"
                    output_file = f"v380_response_{path}{extension}"
                    
                    with open(output_file, 'wb') as f:
                        f.write(response.content)
                    print(f"  ✓ Saved response to {output_file}")
            except requests.RequestException as e:
                print(f"  ✗ Failed: {str(e)}")

def test_v380_protocol():
    """Test the proprietary V380 protocol (if we can determine it from Wireshark)"""
    print("\nTesting proprietary V380 protocol...")
    
    # This is placeholder code - update after analyzing Wireshark capture
    try:
        # Create a socket connection to the camera
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        print(f"Connecting to {ip}:{port}...")
        sock.connect((ip, port))
        print(f"✓ Connected to {ip}:{port}")
        
        # Send authentication packet (update this based on Wireshark analysis)
        # This is just an example format - update with actual protocol details
        auth_packet = bytearray([
            0x01, 0x00, 0x00, 0x00,  # Header
            len(user), 0x00, 0x00, 0x00,  # Username length
        ])
        auth_packet.extend(user.encode('utf-8'))
        auth_packet.extend([
            len(password), 0x00, 0x00, 0x00,  # Password length
        ])
        auth_packet.extend(password.encode('utf-8'))
        
        print(f"Sending authentication packet ({len(auth_packet)} bytes)...")
        sock.send(auth_packet)
        
        # Receive response
        response = sock.recv(1024)
        print(f"Received {len(response)} bytes")
        print(f"Response (hex): {response.hex()}")
        
        # Close connection
        sock.close()
        
    except Exception as e:
        print(f"✗ Error testing proprietary protocol: {str(e)}")

def test_custom_rtsp_urls():
    """Test custom RTSP URL formats that V380 cameras might use"""
    print("\nTesting custom V380 RTSP URL formats...")
    
    # Configure OpenCV for better RTSP handling
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
    
    # V380-specific RTSP URL formats to try
    rtsp_urls = [
        f"rtsp://{user}:{password}@{ip}:{port}/v380media",
        f"rtsp://{user}:{password}@{ip}:{port}/live/ch0",
        f"rtsp://{user}:{password}@{ip}:{port}/live/ch00_0",
        f"rtsp://{user}:{password}@{ip}:{port}/v380/live",
        f"rtsp://{user}:{password}@{ip}:{port}/cam/realmonitor?channel=1&subtype=0",
        f"rtsp://{user}:{password}@{ip}:{port}/stream1",
        f"rtsp://{user}:{password}@{ip}:{port}/v380stream",
        f"rtsp://{user}:{password}@{ip}:{port}/onvif1",
        # Try standard RTSP port
        f"rtsp://{user}:{password}@{ip}:554/v380media",
        f"rtsp://{user}:{password}@{ip}:554/live/ch0",
    ]
    
    for url in rtsp_urls:
        print(f"\nTrying URL: {url}")
        try:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            
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
                filename = f"v380_frame_{url.replace('://', '_').replace('/', '_').replace(':', '_')}.jpg"
                cv2.imwrite(filename, frame)
                print(f"  ✓ Saved test frame to {filename}")
                
                # Save working URL to file
                with open("working_v380_url.txt", "w") as f:
                    f.write(url)
                print(f"  ✓ Saved working URL to working_v380_url.txt")
                
                # Immediate feedback for working connection
                print("\n✓✓✓ FOUND WORKING V380 CAMERA CONNECTION! ✓✓✓")
                print(f"Please update the configuration to use: {url}")
                
                # Break after finding a working URL
                break
                
            # Clean up
            cap.release()
            
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
        
        # Short pause between attempts
        time.sleep(0.5)

if __name__ == "__main__":
    print("V380 Camera Connection Test")
    print("==========================")
    print(f"Testing connection to camera at {ip}:{port}")
    print("Please capture Wireshark traffic while using the V380 Pro app")
    print("to help refine this script with the actual protocol.\n")
    
    # Run tests
    test_http_endpoints()
    test_v380_protocol()
    test_custom_rtsp_urls()
    
    print("\nTesting complete.")
    print("""
Next steps:
1. Analyze Wireshark traffic while using the V380 Pro app
2. Look for HTTP requests, WebSocket connections, or custom protocols
3. Update this script with the actual protocol used
4. Once you find the working method, update your application config
""") 