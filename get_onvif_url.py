from onvif.client import ONVIFCamera
import cv2
import time

# ONVIF Camera settings
wsdl_path = r"./wsdl"  # Use the path relative to where you'll run this script
ip = '129.150.48.140'
port = 8800
user = 'admin'
password = 'AIC_admin'

print("Connecting to ONVIF camera...")
try:
    # Connect to camera
    camera = ONVIFCamera(ip, port, user, password, wsdl_path)
    print("Connected to camera.")

    # Create media service
    media_service = camera.create_media_service()
    print("Created media service.")

    # Get available profiles
    profiles = media_service.GetProfiles()
    print(f"Found {len(profiles)} profiles")

    # For each profile, get the stream URI and test it
    for i, profile in enumerate(profiles):
        try:
            print(f"\nProfile {i+1}: {profile.Name}")
            stream_setup = {
                'StreamSetup': {
                    'Stream': 'RTP-Unicast',
                    'Transport': {
                        'Protocol': 'RTSP'
                    }
                },
                'ProfileToken': profile.token
            }
            
            stream_uri = media_service.GetStreamUri(stream_setup)
            print(f"  Stream URI: {stream_uri.Uri}")
            
            # Test the RTSP URL with OpenCV
            print(f"  Testing connection to: {stream_uri.Uri}")
            cap = cv2.VideoCapture(stream_uri.Uri)
            if cap.isOpened():
                print("  ✓ Successfully connected!")
                ret, frame = cap.read()
                if ret:
                    print(f"  ✓ Successfully read a frame ({frame.shape[1]}x{frame.shape[0]})")
                    
                    # Save a test frame
                    test_file = f"test_frame_profile_{i+1}.jpg"
                    cv2.imwrite(test_file, frame)
                    print(f"  ✓ Saved test frame to {test_file}")
                else:
                    print("  ✗ Could not read a frame")
                cap.release()
            else:
                print("  ✗ Could not connect to the stream")
                
        except Exception as e:
            print(f"  ✗ Error testing profile {i+1}: {str(e)}")
    
    print("\nRTSP URL Format for settings.py:")
    print(f"rtsp://{user}:{password}@{ip}:{port}" + "[PROFILE_PATH]")
    
except Exception as e:
    print(f"Error connecting to camera: {str(e)}") 