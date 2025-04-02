#!/usr/bin/env python3
"""
V380 Protocol Analyzer

This script analyzes a Wireshark PCAP file to identify how V380 Pro communicates with the camera.
You need to install pyshark (pip install pyshark) to use this script.

Usage:
    python analyze_v380_traffic.py capture.pcapng 129.150.48.140
"""

import sys
import os
import pyshark
import json
from collections import Counter
from datetime import datetime

def analyze_pcap(pcap_file, camera_ip):
    """Analyze a PCAP file to identify V380 communication patterns"""
    if not os.path.exists(pcap_file):
        print(f"Error: PCAP file not found: {pcap_file}")
        return
    
    print(f"Analyzing {pcap_file} for traffic with {camera_ip}...")
    
    # Open the capture file
    try:
        cap = pyshark.FileCapture(pcap_file, display_filter=f"ip.addr == {camera_ip}")
    except Exception as e:
        print(f"Error opening PCAP file: {str(e)}")
        print("Make sure you have Wireshark installed and pyshark (pip install pyshark)")
        return
    
    # Counters for analysis
    protocol_counter = Counter()
    tcp_ports = Counter()
    udp_ports = Counter()
    http_urls = Counter()
    http_methods = Counter()
    
    # Results storage
    rtsp_urls = set()
    http_endpoints = set()
    possible_auth_packets = []
    websocket_connections = []
    
    # Process the packets
    packet_count = 0
    try:
        for packet in cap:
            packet_count += 1
            if packet_count % 100 == 0:
                print(f"Processed {packet_count} packets...")
            
            # Get the highest layer protocol
            highest_layer = packet.highest_layer
            protocol_counter[highest_layer] += 1
            
            # Check for TCP/UDP connections
            if hasattr(packet, 'tcp'):
                tcp_ports[f"{packet.tcp.srcport} -> {packet.tcp.dstport}"] += 1
                
                # Look for potential login/auth packets (small TCP packets)
                if hasattr(packet, 'tcp.payload') and camera_ip in packet.ip.dst:
                    try:
                        payload_size = len(packet.tcp.payload.split(':'))
                        if 20 <= payload_size <= 200:  # Likely auth packet size
                            possible_auth_packets.append({
                                'timestamp': packet.sniff_time,
                                'src_port': packet.tcp.srcport,
                                'dst_port': packet.tcp.dstport,
                                'size': payload_size,
                                'payload': packet.tcp.payload
                            })
                    except:
                        pass
            
            if hasattr(packet, 'udp'):
                udp_ports[f"{packet.udp.srcport} -> {packet.udp.dstport}"] += 1
            
            # HTTP analysis
            if highest_layer == 'HTTP':
                if hasattr(packet.http, 'request_method'):
                    http_methods[packet.http.request_method] += 1
                    
                    # Get URL
                    if hasattr(packet.http, 'request_uri'):
                        full_url = f"http://{packet.http.host}{packet.http.request_uri}" 
                        http_urls[full_url] += 1
                        
                        # Store the HTTP endpoint
                        if camera_ip in packet.http.host:
                            http_endpoints.add(packet.http.request_uri)
            
            # RTSP analysis
            if highest_layer == 'RTSP':
                if hasattr(packet.rtsp, 'request_uri'):
                    rtsp_urls.add(packet.rtsp.request_uri)
            
            # WebSocket analysis
            if highest_layer == 'WEBSOCKET':
                if hasattr(packet, 'ws'):
                    websocket_connections.append({
                        'timestamp': packet.sniff_time,
                        'src_port': packet.tcp.srcport if hasattr(packet, 'tcp') else 'unknown',
                        'dst_port': packet.tcp.dstport if hasattr(packet, 'tcp') else 'unknown',
                        'payload': packet.ws.payload if hasattr(packet.ws, 'payload') else 'unknown'
                    })
            
    except Exception as e:
        print(f"Error processing packet: {str(e)}")
    
    # Output the results
    print("\n=== V380 Camera Protocol Analysis ===\n")
    
    print(f"Processed {packet_count} packets with {camera_ip}")
    
    print("\nProtocol Distribution:")
    for protocol, count in protocol_counter.most_common(10):
        print(f"  {protocol}: {count} packets")
    
    print("\nTop TCP Port Pairs:")
    for port_pair, count in tcp_ports.most_common(10):
        print(f"  {port_pair}: {count} packets")
    
    print("\nTop UDP Port Pairs:")
    for port_pair, count in udp_ports.most_common(10):
        print(f"  {port_pair}: {count} packets")
    
    if http_urls:
        print("\nHTTP URLs:")
        for url, count in http_urls.most_common(20):
            print(f"  {url}: {count} requests")
    
    if http_endpoints:
        print("\nHTTP Endpoints on Camera:")
        for endpoint in sorted(http_endpoints):
            print(f"  {endpoint}")
    
    if rtsp_urls:
        print("\nRTSP URLs:")
        for url in sorted(rtsp_urls):
            print(f"  {url}")
    
    if possible_auth_packets:
        print("\nPossible Authentication Packets:")
        for i, packet in enumerate(possible_auth_packets[:5]):  # Show first 5
            print(f"  Packet {i+1}: {packet['timestamp']} Port {packet['src_port']}->{packet['dst_port']} Size: {packet['size']}")
    
    if websocket_connections:
        print("\nWebSocket Connections:")
        for i, conn in enumerate(websocket_connections[:5]):  # Show first 5
            print(f"  Connection {i+1}: {conn['timestamp']} Port {conn['src_port']}->{conn['dst_port']}")
    
    # Export detailed results to a JSON file
    results = {
        'camera_ip': camera_ip,
        'analysis_time': datetime.now().isoformat(),
        'packet_count': packet_count,
        'protocols': dict(protocol_counter),
        'tcp_ports': dict(tcp_ports),
        'udp_ports': dict(udp_ports),
        'http_urls': dict(http_urls),
        'http_methods': dict(http_methods),
        'http_endpoints': list(http_endpoints),
        'rtsp_urls': list(rtsp_urls),
        'possible_auth_packets': possible_auth_packets,
        'websocket_connections': websocket_connections[:20]  # Limit to 20
    }
    
    output_file = f"v380_analysis_{os.path.basename(pcap_file)}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results exported to {output_file}")
    
    # Provide guidance
    print("\n=== Next Steps ===")
    print("1. Look for HTTP or RTSP URLs in the analysis")
    print("2. Check TCP connections on non-standard ports")
    print("3. Look for WebSocket connections that might be used for streaming")
    print("4. Update test_v380_connection.py with the findings")
    print("5. Run additional Wireshark captures focusing on the identified ports/protocols")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <pcap_file> <camera_ip>")
        print(f"Example: {sys.argv[0]} v380_capture.pcapng 129.150.48.140")
        sys.exit(1)
    
    pcap_file = sys.argv[1]
    camera_ip = sys.argv[2]
    analyze_pcap(pcap_file, camera_ip) 