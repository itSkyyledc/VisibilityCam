import socket
import struct
import time
import cv2
import numpy as np
import threading
import logging
import os
import argparse
import traceback
import binascii
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("v380_client.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("V380Client")

class V380Client:
    """
    A client for connecting to V380 cameras using their proprietary protocol
    Based on analysis of V380 app behavior and common IP camera protocols
    """
    
    def __init__(self, ip, port=8800, username="admin", password="AIC_admin"):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.socket = None
        self.connected = False
        self.auth_token = None
        self.stop_event = threading.Event()
        self.frame_buffer = []
        self.buffer_lock = threading.Lock()
        self.last_frame_time = 0
        self.frame_count = 0
        
    def connect(self):
        """Establish connection to the camera"""
        logger.info(f"Connecting to V380 camera at {self.ip}:{self.port}")
        
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            
            # Connect
            self.socket.connect((self.ip, self.port))
            logger.info(f"Socket connected to {self.ip}:{self.port}")
            
            # Try to authenticate
            if self._authenticate():
                self.connected = True
                logger.info("Successfully authenticated with camera")
                return True
            else:
                logger.error("Authentication failed")
                self.socket.close()
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            logger.debug(f"Connection error trace: {traceback.format_exc()}")
            if self.socket:
                self.socket.close()
                self.socket = None
            return False
    
    def _authenticate(self):
        """Authenticate with the camera using various known protocols"""
        auth_methods = [
            self._auth_v380_protocol,
            self._auth_binary_protocol,
            self._auth_http_digest,
            self._auth_simple_credentials
        ]
        
        for method in auth_methods:
            try:
                logger.debug(f"Trying authentication method: {method.__name__}")
                if method():
                    logger.debug(f"Authentication successful with method: {method.__name__}")
                    return True
            except Exception as e:
                logger.debug(f"Auth method {method.__name__} failed: {str(e)}")
                logger.debug(f"Trace: {traceback.format_exc()}")
                # Try next method
                continue
                
        return False
    
    def _auth_binary_protocol(self):
        """Try various binary protocol authentication patterns"""
        logger.debug("Trying binary protocol authentication formats")
        
        # Binary formats to try
        packets = [
            # Format 1: Basic hello packet
            bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            
            # Format 2: Command type + length + payload
            bytes([0x00, 0x01, 0x00, 0x00, 0x0C, 0x00, 0x00, 0x00]) + self.username.encode() + b":" + self.password.encode(),
            
            # Format 3: Login with credentials length
            bytes([0x01, 0x00, 0x00, 0x00]) + struct.pack("<I", len(self.username)) + self.username.encode() + \
            struct.pack("<I", len(self.password)) + self.password.encode(),
            
            # Format 4: Another format with credentials
            struct.pack("<II", 0x0100, len(self.username) + len(self.password) + 2) + \
            self.username.encode() + b":" + self.password.encode()
        ]
        
        for i, packet in enumerate(packets):
            try:
                logger.debug(f"Trying binary auth format {i+1}: {binascii.hexlify(packet[:min(16, len(packet))]).decode()}...")
                
                # Make sure we have a fresh socket for each attempt
                if i > 0:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(5)
                    self.socket.connect((self.ip, self.port))
                
                # Send packet
                self.socket.send(packet)
                
                # Wait for response
                response = b""
                start_time = time.time()
                
                try:
                    while time.time() - start_time < 3:
                        try:
                            chunk = self.socket.recv(1024)
                            if not chunk:
                                break
                            response += chunk
                            logger.debug(f"Received {len(chunk)} bytes")
                        except socket.timeout:
                            break
                except Exception as e:
                    logger.debug(f"Error during receive: {str(e)}")
                
                # Log response
                if response:
                    logger.debug(f"Got response ({len(response)} bytes): {binascii.hexlify(response[:min(32, len(response))]).decode()}")
                    
                    # Save response to file for analysis
                    with open(f"auth_response_{self.port}_format{i+1}.bin", "wb") as f:
                        f.write(response)
                    
                    # Check if response indicates success
                    # This is a guess at success indicators
                    if len(response) > 8:
                        # Longer responses might indicate success
                        return True
                
            except Exception as e:
                logger.debug(f"Binary auth format {i+1} failed: {str(e)}")
        
        return False
    
    def _auth_v380_protocol(self):
        """Authenticate using the V380 proprietary protocol"""
        logger.debug("Trying V380 proprietary authentication")
        
        # The packet format appears to start with "V380" followed by a version byte
        # and then authentication credentials
        auth_packet = b"V380" + struct.pack("<I", 1) + f"{self.username}:{self.password}".encode()
        
        try:
            self.socket.send(auth_packet)
            logger.debug(f"Sent V380 auth packet: {binascii.hexlify(auth_packet[:min(16, len(auth_packet))]).decode()}...")
            
            # Wait for response
            start_time = time.time()
            response = b""
            
            try:
                while time.time() - start_time < 3:
                    try:
                        chunk = self.socket.recv(1024)
                        if not chunk:
                            break
                        response += chunk
                        logger.debug(f"Received {len(chunk)} bytes")
                    except socket.timeout:
                        break
            except Exception as e:
                logger.debug(f"Error during receive: {str(e)}")
            
            # Log response
            if response:
                logger.debug(f"Auth response received: {len(response)} bytes")
                logger.debug(f"Response hex: {binascii.hexlify(response[:min(32, len(response))]).decode()}")
                
                # Save response to file for analysis
                with open(f"v380_auth_response_{self.port}.bin", "wb") as f:
                    f.write(response)
                
                if len(response) > 8:
                    # Extract auth token or session info if present
                    # This is a guess at the protocol, adapt based on actual responses
                    return True  # Assume success if we got a response
                
            return False
            
        except Exception as e:
            logger.debug(f"V380 auth error: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
    
    def _auth_http_digest(self):
        """Try HTTP digest authentication over socket"""
        logger.debug("Trying HTTP digest authentication")
        
        # Try multiple HTTP request formats
        requests = [
            # Standard HTTP GET
            f"GET / HTTP/1.1\r\nHost: {self.ip}\r\nConnection: keep-alive\r\nAuthorization: Basic {self.username}:{self.password}\r\n\r\n".encode(),
            
            # HTTP GET with Auth header
            f"GET /login HTTP/1.1\r\nHost: {self.ip}\r\nAuthorization: Digest username=\"{self.username}\", realm=\"V380\", nonce=\"{int(time.time())}\", uri=\"/login\", response=\"\", qop=auth\r\nUser-Agent: V380Client/1.0\r\n\r\n".encode(),
            
            # V380 specific login
            f"GET /v380/login HTTP/1.1\r\nHost: {self.ip}\r\nAuthorization: Basic {self.username}:{self.password}\r\nUser-Agent: V380Client/1.0\r\n\r\n".encode(),
        ]
        
        for i, auth_request in enumerate(requests):
            try:
                logger.debug(f"Trying HTTP auth request {i+1}")
                
                # Make sure we have a fresh socket for each attempt
                if i > 0:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(5)
                    self.socket.connect((self.ip, self.port))
                
                # Send request
                self.socket.send(auth_request)
                
                # Wait for response
                response = b""
                start_time = time.time()
                
                try:
                    while time.time() - start_time < 3:
                        try:
                            chunk = self.socket.recv(1024)
                            if not chunk:
                                break
                            response += chunk
                            logger.debug(f"Received {len(chunk)} bytes")
                        except socket.timeout:
                            break
                except Exception as e:
                    logger.debug(f"Error during receive: {str(e)}")
                
                # Log response
                if response:
                    logger.debug(f"HTTP response received ({len(response)} bytes): {response[:min(100, len(response))].decode(errors='replace')}")
                    
                    # Save response to file for analysis
                    with open(f"http_auth_response_{self.port}_req{i+1}.bin", "wb") as f:
                        f.write(response)
                    
                    if b"200 OK" in response:
                        logger.debug("Got HTTP 200 OK")
                        return True
                    elif b"401 Unauthorized" in response and b"nonce=" in response:
                        # Extract nonce and calculate proper digest response
                        # This is just a placeholder - actual implementation would be more complex
                        logger.debug("Got 401, would need to implement proper digest auth")
                
            except Exception as e:
                logger.debug(f"HTTP digest auth request {i+1} failed: {str(e)}")
                logger.debug(traceback.format_exc())
        
        return False
    
    def _auth_simple_credentials(self):
        """Try simple username/password authentication"""
        logger.debug("Trying simple credential authentication")
        
        # Authentication formats to try
        formats = [
            # Format 1: Simple JSON-like format
            f"{{\"username\":\"{self.username}\",\"password\":\"{self.password}\"}}".encode(),
            
            # Format 2: Simple colon-separated format
            f"{self.username}:{self.password}".encode(),
            
            # Format 3: URL-encoded format
            f"username={self.username}&password={self.password}".encode(),
        ]
        
        for i, auth_packet in enumerate(formats):
            try:
                logger.debug(f"Trying simple auth format {i+1}: {auth_packet.decode()}")
                
                # Make sure we have a fresh socket for each attempt
                if i > 0:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(5)
                    self.socket.connect((self.ip, self.port))
                
                # Send packet
                self.socket.send(auth_packet)
                
                # Wait for response
                response = b""
                start_time = time.time()
                
                try:
                    while time.time() - start_time < 3:
                        try:
                            chunk = self.socket.recv(1024)
                            if not chunk:
                                break
                            response += chunk
                            logger.debug(f"Received {len(chunk)} bytes")
                        except socket.timeout:
                            break
                except Exception as e:
                    logger.debug(f"Error during receive: {str(e)}")
                
                # Log response
                if response:
                    logger.debug(f"Simple auth response received: {len(response)} bytes")
                    try:
                        logger.debug(f"Response text: {response[:min(100, len(response))].decode(errors='replace')}")
                    except:
                        logger.debug(f"Response hex: {binascii.hexlify(response[:min(32, len(response))]).decode()}")
                    
                    # Save response to file for analysis
                    with open(f"simple_auth_response_{self.port}_format{i+1}.bin", "wb") as f:
                        f.write(response)
                    
                    if b"success" in response.lower() or b"200" in response or b"ok" in response.lower():
                        return True
                
            except Exception as e:
                logger.debug(f"Simple auth format {i+1} failed: {str(e)}")
                logger.debug(traceback.format_exc())
        
        return False
    
    def start_stream(self):
        """Request video stream from the camera"""
        if not self.connected or not self.socket:
            logger.error("Not connected, cannot start stream")
            return False
            
        try:
            # Request video stream - try different formats
            stream_requests = [
                # Format 1: HTTP-like request
                f"GET /livestream HTTP/1.1\r\nHost: {self.ip}\r\nUser-Agent: V380Client/1.0\r\n\r\n".encode(),
                
                # Format 2: RTSP-like request
                f"DESCRIBE rtsp://{self.ip}/live RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\nUser-Agent: V380Client/1.0\r\n\r\n".encode(),
                
                # Format 3: Binary command - 0x02 might be for video stream
                struct.pack("<II", 0x02, 0),
            ]
            
            for i, request in enumerate(stream_requests):
                logger.debug(f"Trying stream request format {i+1}")
                
                # Send request
                self.socket.send(request)
                
                # Wait a bit to see if we get a response
                time.sleep(0.5)
            
            # Start receiving thread
            self.stop_event.clear()
            receiver_thread = threading.Thread(target=self._receive_stream)
            receiver_thread.daemon = True
            receiver_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start stream: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
    
    def _receive_stream(self):
        """Receive and process video stream data"""
        logger.info("Stream receiver thread started")
        
        # Buffer for received data
        buffer = b""
        
        try:
            while not self.stop_event.is_set():
                try:
                    # Receive data
                    data = self.socket.recv(8192)
                    
                    if not data:
                        logger.warning("No data received, connection may be closed")
                        break
                    
                    # Log first chunk to help with protocol analysis
                    if self.frame_count == 0:
                        logger.debug(f"First data chunk received ({len(data)} bytes): {binascii.hexlify(data[:min(64, len(data))]).decode()}")
                        
                        # Save first chunk to file for analysis
                        with open(f"first_stream_chunk_{self.port}.bin", "wb") as f:
                            f.write(data)
                        
                    # Add to buffer
                    buffer += data
                    
                    # Process buffer for frames
                    # This is a simplified example - actual implementation depends on
                    # the exact format of the V380 stream (could be MJPEG, H.264, etc.)
                    
                    # For MJPEG-like stream, look for JPEG markers
                    while len(buffer) > 4:
                        # Check for JPEG SOI marker (0xFFD8) and EOI marker (0xFFD9)
                        soi_idx = buffer.find(b'\xFF\xD8')
                        if soi_idx == -1:
                            # No start marker, discard first byte and continue
                            buffer = buffer[1:]
                            continue
                            
                        # Found SOI, now look for EOI
                        eoi_idx = buffer.find(b'\xFF\xD9', soi_idx + 2)
                        if eoi_idx == -1:
                            # No end marker yet, wait for more data
                            break
                            
                        # Extract frame
                        frame_data = buffer[soi_idx:eoi_idx + 2]
                        buffer = buffer[eoi_idx + 2:]
                        
                        try:
                            # Decode JPEG frame
                            nparr = np.frombuffer(frame_data, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                # Add to frame buffer
                                with self.buffer_lock:
                                    self.frame_buffer.append(frame)
                                    # Keep only last 5 frames
                                    if len(self.frame_buffer) > 5:
                                        self.frame_buffer.pop(0)
                                
                                self.frame_count += 1
                                self.last_frame_time = time.time()
                                
                                # Save first frame
                                if self.frame_count == 1:
                                    filename = f"first_frame_{self.port}.jpg"
                                    cv2.imwrite(filename, frame)
                                    logger.info(f"Saved first frame to {filename}")
                                
                                # Log frame rate occasionally
                                if self.frame_count % 30 == 0:
                                    logger.info(f"Received {self.frame_count} frames")
                        except Exception as e:
                            logger.error(f"Error decoding frame: {str(e)}")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error in stream receiver: {str(e)}")
                    logger.debug(traceback.format_exc())
                    break
                    
        finally:
            logger.info("Stream receiver thread stopped")
    
    def get_frame(self):
        """Get the latest frame from the buffer"""
        with self.buffer_lock:
            if self.frame_buffer:
                return self.frame_buffer[-1]
            return None
    
    def stop_stream(self):
        """Stop the video stream"""
        self.stop_event.set()
        logger.info("Stopping stream")
    
    def disconnect(self):
        """Disconnect from the camera"""
        self.stop_stream()
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        self.connected = False
        logger.info("Disconnected from camera")

def save_frame(frame, directory="frames"):
    """Save a frame to disk"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{directory}/frame_{timestamp}.jpg"
    cv2.imwrite(filename, frame)
    return filename

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='V380 Camera Client')
    parser.add_argument('--ip', required=True, help='Camera IP address')
    parser.add_argument('--port', type=int, default=8800, help='Camera port (default: 8800)')
    parser.add_argument('--username', default='admin', help='Username (default: admin)')
    parser.add_argument('--password', default='AIC_admin', help='Password (default: AIC_admin)')
    parser.add_argument('--save-frames', action='store_true', help='Save frames to disk')
    parser.add_argument('--display', action='store_true', help='Display video stream')
    args = parser.parse_args()
    
    # Create client
    client = V380Client(args.ip, args.port, args.username, args.password)
    
    try:
        # Connect
        if not client.connect():
            logger.error("Failed to connect")
            return
            
        # Start stream
        if not client.start_stream():
            logger.error("Failed to start stream")
            client.disconnect()
            return
            
        # Display stream if requested
        if args.display:
            cv2.namedWindow("V380 Stream", cv2.WINDOW_NORMAL)
            
        # Main loop
        frame_count = 0
        start_time = time.time()
        
        while True:
            frame = client.get_frame()
            
            if frame is not None:
                frame_count += 1
                
                # Calculate FPS every 30 frames
                if frame_count % 30 == 0:
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed
                    logger.info(f"FPS: {fps:.2f}")
                
                # Display frame
                if args.display:
                    cv2.imshow("V380 Stream", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
                # Save frame if requested
                if args.save_frames and frame_count % 10 == 0:  # Save every 10th frame
                    filename = save_frame(frame)
                    logger.info(f"Saved frame: {filename}")
            
            # Small delay to prevent CPU hogging
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Clean up
        if args.display:
            cv2.destroyAllWindows()
        client.disconnect()
        logger.info("Client stopped")

if __name__ == "__main__":
    main() 