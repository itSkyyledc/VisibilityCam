#!/usr/bin/python3
import socket
import sys

DEVICEID = sys.argv[1]
SERVER = '158.178.242.183'
PORT = 34567  # Common V380 Pro port

def try_query(port, query_data):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((SERVER, port))
        sock.send(query_data)
        response = sock.recv(4096)
        sock.close()
        return response
    except:
        return None

# Protocol format from new Wireshark capture
header = bytes.fromhex('7f16d0010000001001020000d000000016000e00')
data = header + bytes(DEVICEID, 'utf-8') + bytes([0] * 100)

print(f'\u001b[32m[+] Checking camera {DEVICEID}...\u001b[37m')
response = try_query(PORT, data)

if response:
    print(f'\u001b[32m[+] Response: {response.hex()}\u001b[37m')
    
    # Try to find stream URL in response
    try:
        response_text = response.decode('utf-8', errors='ignore')
        if 'rtsp://' in response_text:
            print(f'\u001b[32m[+] Found RTSP URL: {response_text}\u001b[37m')
        elif 'v380://' in response_text:
            print(f'\u001b[32m[+] Found V380 URL: {response_text}\u001b[37m')
        elif 'http://' in response_text:
            print(f'\u001b[32m[+] Found HTTP URL: {response_text}\u001b[37m')
    except:
        pass

print('\u001b[31m[-] No stream URL found\u001b[37m')