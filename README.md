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

## Prerequisites

- Python 3.8 or higher
- FFmpeg installed on your system
- IP cameras with RTSP streams

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

4. Create a `.env` file in the project root with your configuration:
```env
OPENWEATHER_API_KEY=your_api_key_here
```

## Configuration

Edit `src/config/settings.py` to configure your cameras and other settings:

```python
DEFAULT_CAMERA_CONFIG = {
    "Camera1": {
        "rtsp_url": "rtsp://your_camera_ip:554/stream1",
        "weather_city": "Manila",
        "visibility_threshold": 0.3,
        "recovery_threshold": 0.5
    }
}
```

## Usage

1. Start the application:
```bash
streamlit run src/main.py
```

2. Open your web browser and navigate to the URL shown in the terminal (typically http://localhost:8501)

3. Use the sidebar to:
   - Select different cameras
   - Adjust visibility thresholds
   - Configure display settings
   - Toggle dark/light theme

4. Navigate between tabs to:
   - View live camera feed
   - Check visibility analytics
   - Monitor weather conditions
   - Access recordings and highlights
   - View historical data

## Project Structure

```
VisibilityCam/
├── src/
│   ├── config/
│   │   └── settings.py
│   ├── core/
│   │   ├── camera_manager.py
│   │   └── weather_manager.py
│   ├── database/
│   │   └── db_manager.py
│   ├── ui/
│   │   └── components.py
│   └── main.py
├── data/
│   ├── recordings/
│   └── highlights/
├── logs/
├── requirements.txt
└── README.md
```

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