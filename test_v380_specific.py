import cv2
import requests
import socket
import time
import os
import sys
import struct
import binascii
import threading
import json

# Camera settings
ip = '129.150.48.140'
ports = [8800, 8089]  # The ports discovered with nmap
user = 'admin'
password = 'AIC_admin'

def test_v380_specific_urls():
    """Test V380-specific connection patterns"""
    print("\nTesting V380-specific URL patterns...")
    
    # V380 often uses specific URL formats that aren't standard RTSP/HTTP
    v380_urls = [
        # V380 Pro app might use these URL formats
        f"http://{ip}:80/livestream/v380?username={user}&password={password}",
        f"http://{ip}:8089/livestream/v380?username={user}&password={password}",
        f"http://{ip}:8800/livestream/v380?username={user}&password={password}",
        f"rtsp://{user}:{password}@{ip}:8089/v380stream",
        f"rtsp://{user}:{password}@{ip}:8089/v380stream/0",
        f"rtsp://{user}:{password}@{ip}:8800/v380stream",
        f"rtsp://{user}:{password}@{ip}:8800/v380stream/0",
        # Try some unusual ports that V380 might use
        f"rtsp://{user}:{password}@{ip}:10554/v380stream",
        f"rtsp://{user}:{password}@{ip}:554/v380stream"
    ]
    
    # Configure OpenCV for better connection
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
    
    for url in v380_urls:
        print(f"\nTrying URL: {url}")
        try:
            # For HTTP URLs, first check with requests
            if url.startswith("http"):
                try:
                    print("  Trying direct HTTP request...")
                    response = requests.get(url, timeout=5)
                    print(f"  Response status: {response.status_code}")
                    content_type = response.headers.get('Content-Type', '')
                    print(f"  Content type: {content_type}")
                    
                    # If we got a successful response, try to open it with OpenCV
                    if response.status_code == 200:
                        print("  Got successful response, now trying with OpenCV...")
                except requests.RequestException as e:
                    print(f"  HTTP request failed: {e}")
            
            # Try with OpenCV
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            time.sleep(3)  # Give more time for connection
            
            if not cap.isOpened():
                print("  ✗ Failed to open with OpenCV")
                cap.release()
                continue
            
            print("  ✓ Successfully opened connection!")
            
            # Try to read frames
            ret, frame = cap.read()
            if not ret:
                print("  ✗ Failed to read frame")
            else:
                print(f"  ✓ Successfully read frame: {frame.shape[1]}x{frame.shape[0]}")
                
                # Save the frame
                filename = f"v380_frame_{url.replace('://', '_').replace('/', '_').replace(':', '_').replace('?', '_')}.jpg"
                cv2.imwrite(filename, frame)
                print(f"  ✓ Saved frame to {filename}")
                
                # Save the working URL
                with open("working_v380_url.txt", "w") as f:
                    f.write(url)
                print(f"  ✓ Saved working URL to working_v380_url.txt")
                
                print(f"\n✓✓✓ SUCCESS! FOUND WORKING V380 URL: {url} ✓✓✓")
                return url
                
            cap.release()
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        time.sleep(1)  # Pause between attempts
    
    return None

def test_v380_protocol_frames():
    """Test V380 proprietary protocol connection using common patterns"""
    print("\nTesting V380 proprietary protocol...")
    
    for port in ports:
        print(f"\nTrying V380 protocol connection on port {port}...")
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            print(f"  Connecting to {ip}:{port}...")
            sock.connect((ip, port))
            print(f"  ✓ Connected to {ip}:{port}")
            
            # Try V380 protocol handshake (based on common patterns)
            # Format: header (4 bytes) + auth data
            print("  Sending V380 protocol handshake...")
            
            # Different packet formats to try
            packets = [
                # Format 1: "V380" + version + auth credentials
                bytearray([
                    0x56, 0x33, 0x38, 0x30,  # "V380" in ASCII
                    0x01, 0x00, 0x00, 0x00,  # Version 1
                ]) + f"{user}:{password}".encode(),
                
                # Format 2: Login request with credentials
                bytearray([
                    0x01, 0x00, 0x00, 0x00,  # Login command
                    len(user), 0x00, 0x00, 0x00,  # Username length (little endian)
                ]) + user.encode() + bytearray([
                    len(password), 0x00, 0x00, 0x00,  # Password length
                ]) + password.encode(),
                
                # Format 3: Simple connection request
                bytearray([
                    0x00, 0x01, 0x00, 0x00,  # Command type
                    0x01, 0x00, 0x00, 0x00,  # Payload length
                    0x01                     # Payload (simple connection request)
                ]),
                
                # Format 4: Another login format
                struct.pack("<4sII", b"V380", 1, len(user) + len(password) + 1) + user.encode() + b":" + password.encode()
            ]
            
            for i, packet in enumerate(packets):
                print(f"  Trying packet format {i+1}/{len(packets)}...")
                print(f"  Packet hex: {binascii.hexlify(packet[:min(20, len(packet))]).decode()}...")
                
                try:
                    sock.send(packet)
                    response = sock.recv(4096)
                    
                    print(f"  Received {len(response)} bytes")
                    print(f"  Response hex: {binascii.hexlify(response[:min(20, len(response))]).decode()}...")
                    
                    # Save response for analysis
                    with open(f"v380_response_port{port}_format{i+1}.bin", "wb") as f:
                        f.write(response)
                    print(f"  ✓ Saved response to v380_response_port{port}_format{i+1}.bin")
                    
                    # Look for success indicators in the response
                    if len(response) > 8:
                        print("  Response looks promising! Check the saved file for video data patterns.")
                        # If we get a response larger than 8 bytes, it might be a successful connection
                        # The actual video data would need to be parsed based on the V380 protocol
                        print(f"\n✓ Potential V380 protocol connection on port {port} with format {i+1}")
                        print(f"  To implement this in code, you would need to reverse engineer the protocol further")
                        print(f"  using Wireshark while the V380 Pro app is connected.")
                        
                except socket.timeout:
                    print("  No response (timeout)")
                except Exception as e:
                    print(f"  Error sending/receiving: {e}")
                
                time.sleep(1)
            
            sock.close()
        except Exception as e:
            print(f"  ✗ Connection error: {e}")
    
    return None

def test_v380_web_config():
    """Try to access the V380 web configuration page to find stream URL"""
    print("\nTrying to access V380 web configuration...")
    
    # Common V380 login/config paths
    config_paths = [
        "/login.html",
        "/index.html",
        "/login.cgi",
        "/cgi-bin/login.cgi",
        "/cgi-bin/hi3510/login.cgi",
        "/v380.htm",
        "/v380pro.htm",
        "/live.html",
        "/livestream.html",
        "/app/index.html",
        "/onvif/device_service",
        "/onvif-http/snapshot",
        "/api/v1/login"
    ]
    
    for port in ports:
        for path in config_paths:
            url = f"http://{ip}:{port}{path}"
            print(f"\nTrying config URL: {url}")
            
            try:
                response = requests.get(url, auth=(user, password), timeout=3)
                print(f"  Response status: {response.status_code}")
                print(f"  Content type: {response.headers.get('Content-Type', 'unknown')}")
                print(f"  Content size: {len(response.content)} bytes")
                
                # Save content for analysis if it looks promising
                if response.status_code == 200 and len(response.content) > 100:
                    filename = f"v380_config_port{port}_path{path.replace('/', '_')}.html"
                    with open(filename, "wb") as f:
                        f.write(response.content)
                    print(f"  ✓ Saved response to {filename}")
                    
                    # Look for stream URLs in the response
                    content_str = response.content.decode('utf-8', errors='ignore')
                    # Look for common patterns in the config page that might reveal the stream URL
                    rtsp_matches = []
                    if "rtsp://" in content_str:
                        rtsp_matches = ["rtsp://" + part.split("rtsp://")[1].split('"')[0] for part in content_str.split("rtsp://")[1:]]
                    
                    http_matches = []
                    if "livestream" in content_str:
                        http_matches = [url.rsplit('/', 1)[0] + "/" + part.split("livestream")[1].split('"')[0] for part in content_str.split("livestream")[1:]]
                    
                    if rtsp_matches:
                        print("  ✓ Found potential RTSP URLs in config page:")
                        for url in rtsp_matches:
                            print(f"    - {url}")
                        
                        # Save the potential URLs
                        with open("v380_potential_urls.txt", "w") as f:
                            f.write("\n".join(rtsp_matches))
                        print(f"  ✓ Saved potential URLs to v380_potential_urls.txt")
                    
                    if http_matches:
                        print("  ✓ Found potential HTTP stream URLs in config page:")
                        for url in http_matches:
                            print(f"    - {url}")
                        
                        # Append to the potential URLs file
                        with open("v380_potential_urls.txt", "a") as f:
                            f.write("\n" + "\n".join(http_matches))
            
            except requests.RequestException as e:
                print(f"  ✗ Error: {e}")
            
            time.sleep(0.5)
    
    return None

def test_v380_app_scan():
    """
    Scan for ports that the V380 app might use.
    This is a quicker scan focused on ports commonly used by IP cameras.
    """
    print("\nScanning for additional V380 camera ports...")
    
    # Common IP camera ports
    camera_ports = [
        80, 554, 8000, 8080, 8081, 8082, 8554, 443, 9000, 10554, 1935
    ]
    
    open_ports = []
    
    for port in camera_ports:
        try:
            print(f"Testing port {port}...", end="")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((ip, port))
            if result == 0:
                print(f" ✓ OPEN")
                open_ports.append(port)
            else:
                print(f" ✗ closed")
            sock.close()
        except Exception as e:
            print(f" ✗ Error: {e}")
    
    if open_ports:
        print(f"\nAdditional open ports found: {open_ports}")
        print("Consider testing these ports with the V380 camera testing scripts.")
    else:
        print("\nNo additional open ports found beyond 8800 and 8089.")
    
    return open_ports

if __name__ == "__main__":
    print(f"V380 Specific Camera Tests - IP: {ip}, Known Ports: {ports}")
    print("===========================================================")
    
    # First scan for additional ports
    additional_ports = test_v380_app_scan()
    if additional_ports:
        ports.extend(additional_ports)
        ports = list(set(ports))  # Remove duplicates
        print(f"Updated port list for testing: {ports}")
    
    # Try to access the web configuration pages
    test_v380_web_config()
    
    # Test V380-specific URL patterns
    url = test_v380_specific_urls()
    
    # Test V380 proprietary protocol
    test_v380_protocol_frames()
    
    if url:
        print(f"\n✓✓✓ SUCCESS! Found working URL: {url}")
        print(f"Update your configuration file to use this URL.")
    else:
        print("\n⚠️ Could not find a working stream URL through automated testing")
        print("""
Next steps:
1. Check saved files for any successful responses or images
2. Capture Wireshark traffic while using the V380 Pro app
3. Look for any potential URLs found in the configuration pages
4. The camera may require the specific V380 Pro app - consider installing this on a phone or PC 
   and capturing the network traffic to see how it communicates with the camera
""")
        
        print("\nTo capture traffic while using the V380 Pro app:")
        print("1. Install Wireshark")
        print("2. Start a capture on your network interface")
        print("3. Run the V380 Pro app and connect to the camera")
        print("4. Stop the capture and analyze the traffic between your device and the camera")
        print("5. Look for TCP or UDP connections to ports 8800 or 8089")
        print("6. Extract the protocol details from the capture to implement in your code") 