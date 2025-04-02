from onvif.client import ONVIFCamera
import time
import sys
import traceback

# ONVIF Camera settings
wsdl_path = "wsdl"  # Use relative path in same directory
ip = '129.150.48.140'
port = 8800
user = 'admin'
password = 'AIC_admin'

def main():
    print("Connecting to ONVIF camera...")
    print(f"IP: {ip}, Port: {port}, User: {user}")
    print(f"WSDL Path: {wsdl_path}")
    
    try:
        # Connect with timeout
        start_time = time.time()
        print("Creating ONVIFCamera object...")
        camera = ONVIFCamera(ip, port, user, password, wsdl_path)
        print(f"Connected in {time.time() - start_time:.2f} seconds")
        
        # Get device information
        print("Creating device management service...")
        devicemgmt = camera.create_devicemgmt_service()
        print("Getting device information...")
        device_info = devicemgmt.GetDeviceInformation()
        print("\nDevice Information:")
        print(f"Manufacturer: {device_info.Manufacturer}")
        print(f"Model: {device_info.Model}")
        print(f"Firmware Version: {device_info.FirmwareVersion}")
        print(f"Serial Number: {device_info.SerialNumber}")
        print(f"Hardware ID: {device_info.HardwareId}")
        
        # Get media service
        print("\nCreating media service...")
        media_service = camera.create_media_service()
        
        # Get profiles
        print("Getting profiles...")
        profiles = media_service.GetProfiles()
        print(f"\nFound {len(profiles)} profiles")
        
        # For each profile, get stream URI
        for i, profile in enumerate(profiles):
            print(f"\nProfile {i+1}: {profile.Name} (Token: {profile.token})")
            
            try:
                stream_setup = {
                    'StreamSetup': {
                        'Stream': 'RTP-Unicast',
                        'Transport': {
                            'Protocol': 'RTSP'
                        }
                    },
                    'ProfileToken': profile.token
                }
                
                # Get stream URI
                print(f"Getting stream URI for profile {profile.Name}...")
                stream_uri = media_service.GetStreamUri(stream_setup)
                print(f"Stream URI: {stream_uri.Uri}")
                
                # Print full RTSP URL with credentials
                url_parts = stream_uri.Uri.split('://')
                if len(url_parts) > 1:
                    auth_url = f"{url_parts[0]}://{user}:{password}@{url_parts[1]}"
                    print(f"Complete RTSP URL: {auth_url}")
                    
                    # Save to a file for easy reference
                    with open(f"rtsp_url_profile_{i+1}.txt", "w") as f:
                        f.write(auth_url)
                    print(f"Saved URL to rtsp_url_profile_{i+1}.txt")
                
            except Exception as e:
                print(f"Error getting stream URI for profile {profile.Name}: {str(e)}")
                traceback.print_exc()
        
    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
        
if __name__ == "__main__":
    main() 