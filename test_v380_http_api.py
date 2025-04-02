import requests
import json
import argparse
import sys
import logging
import cv2
import numpy as np
import time
import os
from requests.auth import HTTPDigestAuth, HTTPBasicAuth
import urllib3
from urllib.parse import urljoin
import concurrent.futures

# Disable SSL warning for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("v380_http_api.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("V380HTTPClient")

# Known V380 endpoints from online documentation and forums
COMMON_ENDPOINTS = [
    "/api/v1/login",
    "/api/login",
    "/api/v1/stream",
    "/api/stream",
    "/api/v1/snapshot",
    "/api/snapshot",
    "/api/v1/device/info",
    "/api/device/info",
    "/cgi-bin/api.cgi",
    "/onvif/device_service",
    "/onvif/media_service",
    "/media/video1",
    "/media/video2",
    "/live/ch00_0",
    "/live/ch01_0",
    "/live",
    "/video",
    "/v380media",
    "/1",
    "/1.jpg",
    "/cgi-bin/snapshot.cgi",
    "/Streaming/Channels/101",
]

# Common query parameters found in IP camera APIs
COMMON_PARAMS = [
    {},
    {"username": "admin", "password": "AIC_admin"},
    {"user": "admin", "password": "AIC_admin"},
    {"account": "admin", "pwd": "AIC_admin"},
    {"token": "admin:AIC_admin"},
]

# Auth methods to try
AUTH_METHODS = [
    None,  # No auth
    HTTPBasicAuth("admin", "AIC_admin"),  # Basic auth
    HTTPDigestAuth("admin", "AIC_admin"),  # Digest auth
]

def test_endpoint(camera_ip, port, use_ssl, endpoint, auth_method=None, params=None, timeout=5):
    """Test a single endpoint with the given auth method and parameters"""
    scheme = "https" if use_ssl else "http"
    base_url = f"{scheme}://{camera_ip}:{port}"
    url = urljoin(base_url, endpoint)
    
    logger.debug(f"Testing endpoint: {url}")
    logger.debug(f"Auth method: {auth_method.__class__.__name__ if auth_method else 'None'}")
    logger.debug(f"Params: {params}")
    
    headers = {
        "User-Agent": "V380/2.0.7 (Windows 10; Chrome)"
    }
    
    try:
        response = requests.get(
            url, 
            auth=auth_method,
            params=params,
            headers=headers,
            timeout=timeout,
            verify=False  # Ignore SSL certificate verification
        )
        
        logger.info(f"Response from {url}: Status {response.status_code}")
        
        # Save response content to file for further analysis
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            timestamp = int(time.time())
            
            # Save response metadata (headers, etc.)
            metadata_file = f"response_{camera_ip}_{port}_{timestamp}_metadata.json"
            with open(metadata_file, 'w') as f:
                metadata = {
                    "url": url,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "auth_method": auth_method.__class__.__name__ if auth_method else "None",
                    "params": params
                }
                json.dump(metadata, f, indent=2)
                
            # Handle different content types
            if 'image' in content_type:
                filename = f"response_{camera_ip}_{port}_{timestamp}.jpg"
                with open(filename, 'wb') as f:
                    f.write(response.content)
                logger.info(f"Image saved to {filename}")
                
                # Also try to display the image using OpenCV
                try:
                    img_array = np.frombuffer(response.content, np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        cv2.imwrite(f"decoded_{filename}", img)
                        logger.info(f"Decoded image saved to decoded_{filename}")
                except Exception as e:
                    logger.error(f"Error decoding image: {e}")
                    
            elif 'video' in content_type or 'stream' in content_type:
                # For video streams, save a short sample
                filename = f"stream_{camera_ip}_{port}_{timestamp}.mp4"
                with open(filename, 'wb') as f:
                    chunk_size = 1024
                    max_chunks = 1000  # Limit to prevent endless streaming
                    chunks = 0
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            chunks += 1
                            if chunks >= max_chunks:
                                break
                logger.info(f"Stream sample saved to {filename}")
                
            else:
                # Text or other content
                filename = f"response_{camera_ip}_{port}_{timestamp}.txt"
                with open(filename, 'wb') as f:
                    f.write(response.content)
                logger.info(f"Response content saved to {filename}")
                
                # Also log the first 1000 characters of text responses
                try:
                    text_content = response.text[:1000]
                    logger.info(f"Response text: {text_content}")
                except Exception as e:
                    logger.error(f"Error decoding text: {e}")
            
            return True, response.status_code
        
        return False, response.status_code
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error accessing {url}: {e}")
        return False, str(e)

def test_all_endpoints(camera_ip, port, use_ssl=False):
    """Test all known endpoints with various auth methods and parameters"""
    successful_endpoints = []
    
    # Create output directory for results
    output_dir = f"v380_api_results_{camera_ip}_{port}"
    os.makedirs(output_dir, exist_ok=True)
    os.chdir(output_dir)
    
    logger.info(f"Starting API tests for camera at {camera_ip}:{port}")
    logger.info(f"Protocol: {'HTTPS' if use_ssl else 'HTTP'}")
    
    # Test each endpoint with different auth methods and parameters
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_endpoint = {}
        
        for endpoint in COMMON_ENDPOINTS:
            for auth_method in AUTH_METHODS:
                for params in COMMON_PARAMS:
                    future = executor.submit(
                        test_endpoint,
                        camera_ip,
                        port,
                        use_ssl,
                        endpoint,
                        auth_method,
                        params
                    )
                    future_to_endpoint[future] = (endpoint, auth_method, params)
        
        for future in concurrent.futures.as_completed(future_to_endpoint):
            endpoint, auth_method, params = future_to_endpoint[future]
            try:
                success, status = future.result()
                if success:
                    auth_name = auth_method.__class__.__name__ if auth_method else "None"
                    successful_endpoints.append((endpoint, auth_name, params, status))
            except Exception as e:
                logger.error(f"Error testing {endpoint}: {e}")
    
    # Write summary report
    report_file = "api_test_results.json"
    with open(report_file, 'w') as f:
        json.dump({
            "camera_ip": camera_ip,
            "port": port,
            "protocol": "https" if use_ssl else "http",
            "successful_endpoints": [
                {
                    "endpoint": ep[0],
                    "auth_method": ep[1],
                    "params": ep[2],
                    "status": ep[3]
                } for ep in successful_endpoints
            ],
            "total_successful": len(successful_endpoints),
            "total_tested": len(COMMON_ENDPOINTS) * len(AUTH_METHODS) * len(COMMON_PARAMS)
        }, f, indent=2)
    
    logger.info(f"Test completed. Results saved to {report_file}")
    logger.info(f"Found {len(successful_endpoints)} successful endpoints out of {len(COMMON_ENDPOINTS) * len(AUTH_METHODS) * len(COMMON_PARAMS)} tested")
    
    # Move back to original directory
    os.chdir("..")
    
    return successful_endpoints

def main():
    parser = argparse.ArgumentParser(description='Test V380 camera HTTP API endpoints')
    parser.add_argument('--ip', required=True, help='Camera IP address')
    parser.add_argument('--ports', default='443,8800,8089', help='Comma-separated list of ports to test')
    parser.add_argument('--https', action='store_true', help='Use HTTPS instead of HTTP')
    
    args = parser.parse_args()
    
    # Parse ports
    ports = [int(p.strip()) for p in args.ports.split(',')]
    
    # Test all ports
    all_successful = []
    for port in ports:
        successful = test_all_endpoints(args.ip, port, args.https)
        all_successful.extend(successful)
    
    # Print summary
    if all_successful:
        logger.info("\nSuccessful endpoints summary:")
        for endpoint, auth, params, status in all_successful:
            param_str = str(params) if params else "None"
            logger.info(f"Endpoint: {endpoint}, Auth: {auth}, Params: {param_str}, Status: {status}")
    else:
        logger.info("No successful endpoints found.")

if __name__ == "__main__":
    main() 