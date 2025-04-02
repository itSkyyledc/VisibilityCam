import socket
import binascii
import time
import sys

def test_socket_connection(ip, port, description=""):
    """Test a direct socket connection to the specified IP and port"""
    print(f"\n\nTesting direct socket connection to {ip}:{port} {description}")
    print("=" * 60)
    
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        # Connect
        print(f"Connecting to {ip}:{port}...")
        sock.connect((ip, port))
        print(f"✓ Connected successfully to {ip}:{port}")
        
        # Try sending different probe packets
        probes = [
            # Empty probe - just connect and listen
            b"",
            
            # HTTP GET request (useful for port 443 which might be HTTP/HTTPS)
            b"GET / HTTP/1.1\r\nHost: " + ip.encode() + b"\r\n\r\n",
            
            # HTTP GET request with V380 specific path
            b"GET /v380 HTTP/1.1\r\nHost: " + ip.encode() + b"\r\n\r\n",
            
            # RTSP probe
            b"OPTIONS rtsp://" + ip.encode() + b" RTSP/1.0\r\nCSeq: 1\r\n\r\n",
            
            # V380 probe - ASCII "V380" + version byte + zeros 
            b"V380\x01\x00\x00\x00",
            
            # Another V380 format with credentials
            b"V380\x01\x00\x00\x00admin:AIC_admin",
            
            # Simple binary probe (common for proprietary protocols)
            bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        ]
        
        for i, probe in enumerate(probes):
            try:
                print(f"\nTrying probe {i+1}/{len(probes)}: ", end="")
                if probe:
                    print(f"Hex: {binascii.hexlify(probe[:min(16, len(probe))]).decode()}...")
                else:
                    print("Empty probe (just listening)")
                
                # Send probe if not empty
                if probe:
                    sock.send(probe)
                
                # Try to receive some data
                start_time = time.time()
                data = b""
                
                # Keep receiving data until timeout or 3 seconds passed
                try:
                    while time.time() - start_time < 3:
                        try:
                            sock.settimeout(3 - (time.time() - start_time))
                            chunk = sock.recv(4096)
                            if not chunk:
                                break
                            data += chunk
                            print(f"Received {len(chunk)} bytes")
                        except socket.timeout:
                            break
                except Exception as e:
                    print(f"Error during receive: {e}")
                
                # Display results
                if data:
                    print(f"Received total {len(data)} bytes")
                    print("First 100 bytes as hex:")
                    print(binascii.hexlify(data[:100]).decode())
                    
                    # Try to decode as ASCII/UTF-8 if it looks like text
                    if all(c < 128 for c in data[:100]):
                        try:
                            print("\nAs text:")
                            print(data[:100].decode('utf-8', errors='replace'))
                        except:
                            pass
                    
                    # Save the response to a file
                    filename = f"socket_response_port{port}_probe{i+1}.bin"
                    with open(filename, "wb") as f:
                        f.write(data)
                    print(f"✓ Saved response to {filename}")
                else:
                    print("No data received")
                
            except socket.timeout:
                print("Timeout waiting for response")
            except Exception as e:
                print(f"Error during probe {i+1}: {e}")
                
            # Short delay between probes
            time.sleep(1)
        
        # Close socket
        sock.close()
        print("\n✓ Socket closed")
        
    except socket.timeout:
        print(f"✗ Connection timeout to {ip}:{port}")
    except ConnectionRefusedError:
        print(f"✗ Connection refused to {ip}:{port}")
    except Exception as e:
        print(f"✗ Error: {e}")

def main():
    # Camera IP
    ip = "129.150.48.140"
    
    # Test port 443 (HTTPS)
    test_socket_connection(ip, 443, "(HTTPS port)")
    
    # Test port 8800
    test_socket_connection(ip, 8800, "(Primary port)")
    
    # Test port 8089
    test_socket_connection(ip, 8089, "(Secondary port)")
    
    print("\n\nTesting completed. Check the generated response files for any useful information.")
    print("To capture more detailed protocol information, use Wireshark while connecting with the V380 app.")

if __name__ == "__main__":
    main() 