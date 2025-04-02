import requests
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

def get_weather_data(location, api_key=None):
    """
    Get weather data for a location.
    Uses a simple mock implementation if no API key is provided.
    """
    
    # If we have an API key, use a real weather API
    if api_key:
        try:
            return get_real_weather_data(location, api_key)
        except Exception as e:
            logger.error(f"Error getting real weather data: {str(e)}")
            # Fall back to mock data if API call fails
            return get_mock_weather_data(location)
    else:
        # Use mock data if no API key
        return get_mock_weather_data(location)

def get_real_weather_data(location, api_key):
    """Get real weather data from a weather API"""
    # Example implementation for OpenWeatherMap API
    # You can replace this with any weather API of your choice
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Weather API returned status code {response.status_code}")
    
    data = response.json()
    
    weather_data = {
        "location": location,
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "wind_speed": data["wind"]["speed"],
        "visibility": data["visibility"] / 1000,  # Convert to kilometers
        "condition": data["weather"][0]["description"],
        "icon_url": f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return weather_data

def get_mock_weather_data(location):
    """Get mock weather data for development/testing"""
    # Create some realistic mock data
    weather_data = {
        "location": location,
        "temperature": 22.5,
        "humidity": 65,
        "wind_speed": 10.2,
        "visibility": 8.5,  # kilometers
        "condition": "Partly Cloudy",
        "icon_url": "https://openweathermap.org/img/wn/02d@2x.png",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Randomize data a bit to simulate changing conditions
    import random
    
    # Adjust temperature by ±2°C
    weather_data["temperature"] += random.uniform(-2.0, 2.0)
    
    # Adjust humidity by ±5%
    weather_data["humidity"] += random.uniform(-5.0, 5.0)
    weather_data["humidity"] = max(0, min(100, weather_data["humidity"]))
    
    # Adjust wind speed by ±2 km/h
    weather_data["wind_speed"] += random.uniform(-2.0, 2.0)
    weather_data["wind_speed"] = max(0, weather_data["wind_speed"])
    
    # Adjust visibility by ±1 km
    weather_data["visibility"] += random.uniform(-1.0, 1.0)
    weather_data["visibility"] = max(0.1, weather_data["visibility"])
    
    # Randomly select a condition based on visibility
    if weather_data["visibility"] < 2.0:
        weather_data["condition"] = random.choice(["Foggy", "Misty", "Heavy Rain", "Snow"])
        weather_data["icon_url"] = random.choice([
            "https://openweathermap.org/img/wn/50d@2x.png",  # Mist
            "https://openweathermap.org/img/wn/10d@2x.png",  # Rain
            "https://openweathermap.org/img/wn/13d@2x.png"   # Snow
        ])
    elif weather_data["visibility"] < 5.0:
        weather_data["condition"] = random.choice(["Light Rain", "Cloudy", "Overcast"])
        weather_data["icon_url"] = random.choice([
            "https://openweathermap.org/img/wn/03d@2x.png",  # Cloudy
            "https://openweathermap.org/img/wn/04d@2x.png",  # Overcast
            "https://openweathermap.org/img/wn/09d@2x.png"   # Light rain
        ])
    else:
        weather_data["condition"] = random.choice(["Clear", "Sunny", "Partly Cloudy"])
        weather_data["icon_url"] = random.choice([
            "https://openweathermap.org/img/wn/01d@2x.png",  # Clear
            "https://openweathermap.org/img/wn/02d@2x.png"   # Partly cloudy
        ])
    
    return weather_data 