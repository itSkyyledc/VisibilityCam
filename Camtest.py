from onvif.client import ONVIFCamera

wsdl = r"C:\Users\steve\Documents\GitHub\VisibilityCam\wsdl"
ip = '158.178.242.183'
port = 8900
user = 'admin'
password = 'AIC_admin'
camera = ONVIFCamera(ip, port, user, password, wsdl)

media_service = camera.create_media_service()

profiles = media_service.GetProfiles()

stream_url = media_service.GetStreamUri({
    'StreamSetup': {
        'Stream': 'RTP-Unicast',
        'Transport': {
            'Protocol': 'RTSP'
        }
    },
    'ProfileToken': profiles[0].token
})

print ("Stream URL:", stream_url)  # Print the stream_url