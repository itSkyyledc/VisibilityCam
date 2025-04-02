from scapy.all import sniff, wrpcap
import datetime
import os
import argparse

def capture_traffic(interface, camera_ip, duration=60, output_dir='.'):
    """
    Capture network traffic between the local machine and the V380 camera.
    
    Args:
        interface (str): Network interface to capture on
        camera_ip (str): IP address of the V380 camera
        duration (int): Duration of capture in seconds
        output_dir (str): Directory to save the capture file
    """
    print(f"Starting packet capture on interface {interface} for {duration} seconds...")
    print(f"Filtering for traffic to/from camera IP: {camera_ip}")
    
    # Create timestamp for filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"v380_capture_{timestamp}.pcap")
    
    # Build filter string to capture traffic to/from the camera IP
    capture_filter = f"host {camera_ip}"
    
    # Start the capture
    packets = sniff(iface=interface, filter=capture_filter, timeout=duration)
    
    # Save the captured packets
    wrpcap(output_file, packets)
    print(f"Capture complete. {len(packets)} packets captured and saved to {output_file}")
    
    return output_file

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Capture network traffic to/from V380 camera')
    parser.add_argument('--interface', required=True, help='Network interface to capture on')
    parser.add_argument('--camera-ip', required=True, help='IP address of the V380 camera')
    parser.add_argument('--duration', type=int, default=60, help='Duration of capture in seconds')
    parser.add_argument('--output-dir', default='.', help='Directory to save capture file')
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    
    # Start the capture
    capture_file = capture_traffic(args.interface, args.camera_ip, args.duration, args.output_dir)
    
    print(f"You can analyze the capture file {capture_file} with Wireshark")
    print("Example command: wireshark -r " + capture_file)

if __name__ == "__main__":
    main() 