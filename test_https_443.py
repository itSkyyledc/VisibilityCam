import cv2
import requests
import time
import os
import ssl
import urllib3
import json
from urllib3.exceptions import InsecureRequestWarning

# Suppress only the single warning from urllib3 needed
urllib3.disable_warnings(InsecureRequestWarning)

# Camera settings
ip = '129.150.48.140'
port = 443  # HTTPS port
user = 'admin'
password = 'AIC_admin'

def test_https_web_interface():
    """Test HTTPS web interface paths that might be available on port 443"""
    print("\nTesting HTTPS web interface on port 443...")
    
    # Common paths for camera web interfaces, including V380-specific ones
    paths = [
        "/",
        "/index.html",
        "/login.html",
        "/v380/index",
        "/v380/login",
        "/v380pro/index",
        "/v380pro/login",
        "/device",
        "/app",
        "/api/v1/login",
        "/api/login",
        "/api/device/login",
        "/onvif/device_service",
        "/onvif-http/snapshot",
        "/cgi-bin/login",
        "/cgi-bin/hi3510/login",
        "/cgi/hi3510",
        "/webservice"
    ]
    
    for path in paths:
        url = f"https://{ip}:{port}{path}"
        print(f"\nTrying HTTPS URL: {url}")
        
        try:
            # Try with auth in URL
            response = requests.get(
                url, 
                auth=(user, password),
                verify=False,  # Skip SSL verification since it might have a self-signed cert
                timeout=5
            )
            
            print(f"  Response status: {response.status_code}")
            print(f"  Content type: {response.headers.get('Content-Type', 'unknown')}")
            print(f"  Content length: {len(response.content)} bytes")
            
            # Save any non-error responses for analysis
            if response.status_code < 400 and len(response.content) > 0:
                filename = f"https_response_{path.replace('/', '_')}.html"
                with open(filename, "wb") as f:
                    f.write(response.content)
                print(f"  ✓ Saved response to {filename}")
                
                # Try to parse JSON response
                try:
                    json_data = response.json()
                    print(f"  ✓ JSON response: {json.dumps(json_data, indent=2)[:200]}...")
                except:
                    pass
                
                # Check for URLs in the response
                content_str = response.content.decode('utf-8', errors='ignore')
                if "rtsp://" in content_str or "rtmp://" in content_str or "stream" in content_str:
                    print("  ✓ Response contains potential stream URLs!")
                
                # If we get a login page or dashboard, it's a good sign
                if "login" in content_str.lower() or "dashboard" in content_str.lower():
                    print("  ✓ Found login page or dashboard!")
                    
        except requests.RequestException as e:
            print(f"  ✗ Error: {e}")
        
        time.sleep(0.5)

def test_https_api_endpoints():
    """Test potential API endpoints on the HTTPS port"""
    print("\nTesting HTTPS API endpoints...")
    
    # Common API endpoints for cameras
    api_endpoints = [
        "/api/v1/login",
        "/api/device/rtsp",
        "/api/stream/url",
        "/api/v1/stream",
        "/api/v380/stream",
        "/api/camera/stream",
        "/api/camera/snapshot",
        "/api/snapshot",
        "/onvif/device_service",
        "/api/device/info",
        "/api/v1/device/info"
    ]
    
    # Common JSON payloads for login
    login_payloads = [
        {"username": user, "password": password},
        {"user": user, "pass": password},
        {"account": user, "password": password},
        {"name": user, "pwd": password},
        {"login": user, "password": password}
    ]
    
    # Test GET requests first
    for endpoint in api_endpoints:
        url = f"https://{ip}:{port}{endpoint}"
        print(f"\nTrying GET to {url}")
        
        try:
            response = requests.get(
                url,
                auth=(user, password),
                verify=False,
                timeout=5
            )
            
            print(f"  Response status: {response.status_code}")
            content_type = response.headers.get('Content-Type', 'unknown')
            print(f"  Content type: {content_type}")
            print(f"  Content length: {len(response.content)} bytes")
            
            # Save successful responses
            if response.status_code < 400 and len(response.content) > 0:
                filename = f"https_api_get_{endpoint.replace('/', '_')}.json" if "json" in content_type else f"https_api_get_{endpoint.replace('/', '_')}.bin"
                with open(filename, "wb") as f:
                    f.write(response.content)
                print(f"  ✓ Saved response to {filename}")
                
                # Try to parse as JSON
                if "json" in content_type:
                    try:
                        data = response.json()
                        print(f"  ✓ JSON response: {json.dumps(data, indent=2)[:200]}...")
                    except:
                        pass
        
        except requests.RequestException as e:
            print(f"  ✗ GET request error: {e}")
        
        # Now try POST requests for login endpoints
        if "login" in endpoint:
            for payload in login_payloads:
                print(f"\nTrying POST to {url} with payload: {payload}")
                
                try:
                    response = requests.post(
                        url,
                        json=payload,
                        verify=False,
                        timeout=5
                    )
                    
                    print(f"  Response status: {response.status_code}")
                    print(f"  Content type: {response.headers.get('Content-Type', 'unknown')}")
                    print(f"  Content length: {len(response.content)} bytes")
                    
                    # Save successful responses
                    if response.status_code < 400 and len(response.content) > 0:
                        filename = f"https_api_post_{endpoint.replace('/', '_')}_payload{login_payloads.index(payload)}.json"
                        with open(filename, "wb") as f:
                            f.write(response.content)
                        print(f"  ✓ Saved response to {filename}")
                        
                        # Try to parse as JSON
                        try:
                            data = response.json()
                            print(f"  ✓ JSON response: {json.dumps(data, indent=2)[:200]}...")
                            
                            # Look for tokens, stream URLs, or other useful info
                            if "token" in str(data).lower():
                                print("  ✓ Response contains authentication token!")
                            if "url" in str(data).lower() or "stream" in str(data).lower():
                                print("  ✓ Response might contain stream URL!")
                            
                            # Save working login credentials and endpoint
                            if response.status_code == 200:
                                with open("working_login_endpoint.txt", "w") as f:
                                    f.write(f"URL: {url}\nPayload: {json.dumps(payload)}")
                                print("  ✓ Saved working login endpoint info")
                        except:
                            pass
                
                except requests.RequestException as e:
                    print(f"  ✗ POST request error: {e}")
                
                time.sleep(0.5)
        
        time.sleep(0.5)

def test_https_rtsp_proxy():
    """Try HTTPS endpoints that might proxy to RTSP streams"""
    print("\nTesting HTTPS to RTSP proxy endpoints...")
    
    # Paths that might proxy to RTSP
    proxy_paths = [
        "/stream",
        "/live",
        "/video",
        "/rtsp",
        "/v380/stream",
        "/v380/live",
        "/app/stream",
        "/api/stream",
        "/media/stream",
        "/videostream",
        "/live/stream",
        "/media/live"
    ]
    
    # Try with different extensions
    extensions = ["", ".mjpg", ".jpg", ".mp4", ".flv", ".m3u8", "?type=flv", "?type=hls"]
    
    for path in proxy_paths:
        for ext in extensions:
            url = f"https://{ip}:{port}{path}{ext}"
            print(f"\nTrying stream URL: {url}")
            
            try:
                # First try with requests to see if endpoint exists
                response = requests.get(
                    url,
                    auth=(user, password),
                    verify=False,
                    stream=True,
                    timeout=5
                )
                
                print(f"  Response status: {response.status_code}")
                content_type = response.headers.get('Content-Type', 'unknown')
                print(f"  Content type: {content_type}")
                
                # If we get a video/stream content type, save the first part
                if response.status_code == 200:
                    if any(media_type in content_type for media_type in ['video', 'stream', 'mpegurl', 'mp4', 'flv', 'octet-stream']):
                        print("  ✓ Found potential video stream!")
                        filename = f"https_stream_sample_{path.replace('/', '_')}{ext.replace('?', '_')}.bin"
                        with open(filename, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    if f.tell() > 100000:  # Save ~100KB to analyze
                                        break
                        print(f"  ✓ Saved stream sample to {filename}")
                        
                        # Save working stream URL
                        with open("working_https_stream.txt", "w") as f:
                            f.write(url)
                        print(f"  ✓ Saved working HTTPS stream URL")
                        
                    elif 'image' in content_type:
                        # It's an image, might be a snapshot
                        filename = f"https_snapshot_{path.replace('/', '_')}{ext.replace('?', '_')}.jpg"
                        with open(filename, "wb") as f:
                            f.write(response.content)
                        print(f"  ✓ Saved snapshot to {filename}")
                
                # Try with OpenCV if content type suggests video
                if response.status_code == 200 and any(media_type in content_type for media_type in ['video', 'stream', 'mpegurl', 'mp4', 'flv']):
                    print("  Trying to open with OpenCV...")
                    # Define environment variables for better RTSP handling
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;10000000|buffer_size;65536|stimeout;5000000|max_delay;500000|fflags;nobuffer|flags;low_delay"
                    
                    # OpenCV can handle some HTTPS streams directly
                    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                    if cap.isOpened():
                        print("  ✓ Successfully opened with OpenCV!")
                        ret, frame = cap.read()
                        if ret:
                            print(f"  ✓ Successfully read frame: {frame.shape[1]}x{frame.shape[0]}")
                            cv2.imwrite(f"https_frame_{path.replace('/', '_')}{ext.replace('?', '_')}.jpg", frame)
                            print(f"  ✓ Saved frame")
                            
                            # This is the working stream URL!
                            with open("working_stream_url.txt", "w") as f:
                                f.write(url)
                            print(f"  ✓ FOUND WORKING V380 STREAM URL: {url}")
                            
                            return url
                        else:
                            print("  ✗ Failed to read frame")
                        cap.release()
                    else:
                        print("  ✗ Failed to open with OpenCV")
            
            except requests.RequestException as e:
                print(f"  ✗ Error: {e}")
            
            time.sleep(1)
    
    return None

def test_v380_mobile_app_endpoints():
    """Test endpoints that might be used by the V380 mobile app"""
    print("\nTesting V380 mobile app endpoints...")
    
    # Paths that the V380 app might use
    app_paths = [
        "/app/v380.json",
        "/app/config",
        "/app/login",
        "/app/api/login",
        "/app/api/stream",
        "/mobile/login",
        "/mobile/stream",
        "/v380/app/login",
        "/v380/app/stream"
    ]
    
    for path in app_paths:
        url = f"https://{ip}:{port}{path}"
        print(f"\nTrying mobile app endpoint: {url}")
        
        try:
            response = requests.get(
                url,
                auth=(user, password),
                verify=False,
                timeout=5
            )
            
            print(f"  Response status: {response.status_code}")
            print(f"  Content type: {response.headers.get('Content-Type', 'unknown')}")
            print(f"  Content length: {len(response.content)} bytes")
            
            if response.status_code < 400 and len(response.content) > 0:
                filename = f"v380_app_{path.replace('/', '_')}.bin"
                with open(filename, "wb") as f:
                    f.write(response.content)
                print(f"  ✓ Saved response to {filename}")
                
                # Try to parse as JSON
                try:
                    data = response.json()
                    print(f"  ✓ JSON response: {json.dumps(data, indent=2)[:200]}...")
                    
                    # Look for stream URLs in the response
                    if any(stream_keyword in str(data).lower() for stream_keyword in ['url', 'stream', 'rtsp', 'video']):
                        print("  ✓ Response might contain stream information!")
                except:
                    pass
                
        except requests.RequestException as e:
            print(f"  ✗ Error: {e}")
        
        time.sleep(0.5)

def summarize_findings():
    """Check for any successful results from previous tests"""
    print("\n\nSummarizing findings...")
    
    # Check for any saved stream URLs or successful responses
    found_files = []
    
    # Check for streaming URLs
    if os.path.exists("working_stream_url.txt"):
        with open("working_stream_url.txt", "r") as f:
            url = f.read().strip()
            print(f"✅ Found working stream URL: {url}")
            found_files.append("working_stream_url.txt")
    
    if os.path.exists("working_https_stream.txt"):
        with open("working_https_stream.txt", "r") as f:
            url = f.read().strip()
            print(f"✅ Found working HTTPS stream URL: {url}")
            found_files.append("working_https_stream.txt")
    
    if os.path.exists("working_login_endpoint.txt"):
        with open("working_login_endpoint.txt", "r") as f:
            info = f.read().strip()
            print(f"✅ Found working login endpoint:\n{info}")
            found_files.append("working_login_endpoint.txt")
    
    # Check for saved frames
    frame_files = [f for f in os.listdir() if f.startswith("https_frame_")]
    if frame_files:
        print(f"✅ Captured {len(frame_files)} frames:")
        for file in frame_files:
            print(f"  - {file}")
        found_files.extend(frame_files)
    
    # Check for saved stream samples
    stream_files = [f for f in os.listdir() if f.startswith("https_stream_sample_")]
    if stream_files:
        print(f"✅ Saved {len(stream_files)} stream samples:")
        for file in stream_files:
            print(f"  - {file}")
        found_files.extend(stream_files)
    
    # If we found nothing
    if not found_files:
        print("❌ No successful connections found.")
        print("""
Recommendations:
1. Try installing the V380 mobile app and monitor traffic with Wireshark
2. Check if the camera requires a specific firmware update
3. Try resetting the camera to factory defaults
4. Verify network connectivity and firewall settings
5. Try a different username/password combination
        """)
    else:
        print("""
Next steps:
1. Check the captured frames or stream samples
2. Update your camera configuration to use any working URLs found
3. If login is required, implement the login flow before accessing streams
        """)

if __name__ == "__main__":
    print(f"V380 Camera HTTPS Testing - IP: {ip}, Port: {port}")
    print("=================================================")
    
    # Test different approaches to access the camera via HTTPS
    test_https_web_interface()
    test_https_api_endpoints()
    test_https_rtsp_proxy()
    test_v380_mobile_app_endpoints()
    
    # Summarize what we found
    summarize_findings() 