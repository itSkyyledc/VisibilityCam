# Visibility Camera Dashboard

A Streamlit-based dashboard for monitoring visibility conditions from IP cameras. The application provides real-time monitoring, analytics, weather insights, and automatic recording of low visibility events.

## Features

- Real-time visibility monitoring from IP cameras
- Automatic recording during low visibility conditions
- Weather data integration
- Historical analytics and trends
- Dark/light theme support
- Configurable visibility thresholds
- Automatic highlight creation for significant visibility events
- ROI (Regions of Interest) selection for targeted monitoring
- Multi-camera support with independent settings

## Prerequisites

- Python 3.8 or higher
- FFmpeg installed on your system
- IP cameras with RTSP streams
- Internet connection for weather data (OpenWeather API)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/VisibilityCam.git
cd VisibilityCam
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create an `api_key.txt` file in the project root with your OpenWeather API key, or set it as an environment variable:
```
your_openweather_api_key_here
```

## Configuration

Configure your cameras by editing the `camera_config.json` file in the project root:

```json
{
  "Camera1": {
    "rtsp_url": "rtsp://your_camera_ip:554/stream1",
    "weather_city": "Manila",
    "visibility_threshold": 0.3,
    "recovery_threshold": 0.5,
    "color_delta_threshold": 30
  }
}
```

You can add multiple cameras with different configurations.

## Usage

1. Start the application:
```bash
python -m streamlit run run.py
```

   Alternatively, you can use:
```bash
streamlit run src/main.py
```

2. Open your web browser and navigate to the URL shown in the terminal (typically http://localhost:8501)

3. Use the sidebar to:
   - Select different cameras
   - Adjust visibility thresholds
   - Configure ROI regions
   - Configure display settings
   - Toggle dark/light theme

4. Navigate between tabs to:
   - View live camera feed
   - Check visibility analytics
   - Monitor weather conditions
   - Access recordings and highlights
   - View historical data and trends

## Project Structure

```
VisibilityCam/
├── src/
│   ├── config/          # Configuration management
│   ├── core/            # Core functionality (camera and weather)
│   ├── database/        # Database operations
│   ├── ui/              # UI components and layout
│   ├── utils/           # Utility functions and analytics
│   └── main.py          # Main application entry point
├── data/                # Data storage
├── recordings/          # Stored video recordings
├── highlights/          # Visibility event highlights
├── logs/                # Application logs
├── .streamlit/          # Streamlit configuration
├── run.py               # Application runner
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

## Recordings and Highlights

The application automatically records video during low visibility events. Recordings are stored in the `recordings/` directory.

Highlight clips of significant visibility changes are created automatically and stored in the `highlights/` directory.

## Regions of Interest (ROI)

You can define specific regions of interest on the camera feed to monitor visibility in targeted areas. This is useful for monitoring specific landmarks, roads, or areas where visibility is critical.

## Weather Integration

The dashboard integrates with OpenWeather API to provide real-time weather data for the camera location. This helps correlate visibility conditions with weather events.

## Analytics

The analytics feature provides:

- Historical visibility trends
- Visibility change detection
- Event logging and playback
- Statistical analysis of visibility patterns

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Streamlit for the web framework
- OpenCV for image processing
- OpenWeather API for weather data
- FFmpeg for video processing 