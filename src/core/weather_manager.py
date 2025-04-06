import requests
import logging
import time
from datetime import datetime
from ..config.settings import WEATHER_API_KEY_FILE, WEATHER_UPDATE_INTERVAL

logger = logging.getLogger(__name__)

class WeatherManager:
    """Manager for weather data fetching and processing"""
    
    def __init__(self, location, api_key=None):
        """Initialize weather manager"""
        self.location = location
        self.api_key = api_key
        
        # Try to load API key from file if not provided
        if not self.api_key:
            self.api_key = self._load_api_key()
            
        self.weather_data = None
        self.last_update = 0
        self.update_interval = 3600  # Update every hour
        
        # Cache to store weather data
        self.weather_cache = {}
        self.last_fetch_time = {}
        
        # Default refresh interval (30 minutes in seconds)
        self.default_refresh_interval = 1800
        self.refresh_intervals = {}
        
        # Add base_url for weather API
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        
        # Safely initialize DatabaseManager
        try:
            from ..database.db_manager import DatabaseManager
            self.db_manager = DatabaseManager()
        except (ImportError, ModuleNotFoundError) as e:
            logger.warning(f"Could not import DatabaseManager: {str(e)}")
            self.db_manager = None
        except Exception as e:
            logger.error(f"Error initializing DatabaseManager: {str(e)}")
            self.db_manager = None
    
    def get_weather_updated(self, force_update=False):
        """Get weather data, fetching from API if needed"""
        current_time = time.time()
        
        # Check if we need to update
        if force_update or not self.weather_data or (current_time - self.last_update) > self.update_interval:
            self._fetch_weather()
        
        return self.weather_data
    
    def _fetch_weather(self):
        """Fetch weather data from API or use mock data"""
        try:
            if self.api_key:
                # Use OpenWeatherMap API
                url = f"http://api.openweathermap.org/data/2.5/weather?q={self.location}&appid={self.api_key}&units=metric"
                response = requests.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    self.weather_data = {
                        "location": self.location,
                        "temperature": data["main"]["temp"],
                        "humidity": data["main"]["humidity"],
                        "wind_speed": data["wind"]["speed"],
                        "visibility": data["visibility"] / 1000,  # Convert to kilometers
                        "condition": data["weather"][0]["description"],
                        "icon_url": f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png",
                        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                else:
                    logger.error(f"Weather API returned status code {response.status_code}")
                    self._use_mock_weather()
            else:
                self._use_mock_weather()
                
            self.last_update = time.time()
        except Exception as e:
            logger.error(f"Error fetching weather data: {str(e)}")
            self._use_mock_weather()
    
    def _use_mock_weather(self):
        """Generate mock weather data for testing"""
        import random
        
        # Create realistic mock data
        self.weather_data = {
            "location": self.location,
            "temperature": 22.5 + random.uniform(-5.0, 5.0),
            "humidity": 65 + random.uniform(-10.0, 10.0),
            "wind_speed": 10.2 + random.uniform(-5.0, 5.0),
            "visibility": 8.5 + random.uniform(-3.0, 3.0),  # kilometers
            "condition": random.choice(["Clear", "Partly Cloudy", "Cloudy", "Light Rain", "Heavy Rain", "Foggy"]),
            "icon_url": "https://openweathermap.org/img/wn/02d@2x.png",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Ensure values are in valid ranges
        self.weather_data["humidity"] = max(0, min(100, self.weather_data["humidity"]))
        self.weather_data["wind_speed"] = max(0, self.weather_data["wind_speed"])
        self.weather_data["visibility"] = max(0.1, self.weather_data["visibility"])
    
    def _load_api_key(self):
        """Load API key from file"""
        try:
            if WEATHER_API_KEY_FILE.exists():
                with open(WEATHER_API_KEY_FILE, 'r') as file:
                    api_key = file.read().strip()
                    if not api_key or len(api_key) < 16:
                        logger.error("Weather API key is invalid or too short. Please check api_key.txt file.")
                        return None
                    return api_key
            else:
                logger.error(f"Weather API key file not found at {WEATHER_API_KEY_FILE}. Please create this file with your OpenWeather API key.")
                # Try to create the file with a placeholder
                with open(WEATHER_API_KEY_FILE, 'w') as file:
                    file.write("YOUR_OPENWEATHER_API_KEY_HERE")
                logger.info(f"Created placeholder api_key.txt file. Please edit it with your actual OpenWeather API key.")
                return None
        except Exception as e:
            logger.error(f"Error loading API key: {str(e)}")
            return None
    
    def set_refresh_interval(self, city, interval_minutes):
        """Set the refresh interval for a specific city"""
        if interval_minutes < 5:
            logger.warning(f"Refresh interval too short, setting to minimum of 5 minutes for {city}")
            interval_minutes = 5
            
        self.refresh_intervals[city] = interval_minutes * 60  # Convert to seconds
        logger.info(f"Weather refresh interval for {city} set to {interval_minutes} minutes")
        return True
    
    def get_refresh_interval(self, city):
        """Get the current refresh interval for a city"""
        return self.refresh_intervals.get(city, self.default_refresh_interval) // 60  # Convert to minutes
    
    def get_default_refresh_interval(self):
        """Get the default refresh interval in minutes"""
        return self.default_refresh_interval // 60
    
    def set_default_refresh_interval(self, interval_minutes):
        """Set the default refresh interval for all cities"""
        if interval_minutes < 5:
            logger.warning("Default refresh interval too short, setting to minimum of 5 minutes")
            interval_minutes = 5
            
        self.default_refresh_interval = interval_minutes * 60  # Convert to seconds
        logger.info(f"Default weather refresh interval set to {interval_minutes} minutes")
        return True
    
    def get_weather(self, city):
        """Get weather data for a city, using cache if available and not expired"""
        
        # Use Manila as default city if none or empty provided
        if not city:
            city = "Manila,PH"
            
        # Special case for AIC, Philippines - use Manila
        if city.lower() == "aic, philippines":
            logger.info("Converting 'AIC, Philippines' to 'Manila,PH' for better API recognition")
            city = "Manila,PH"
            
        # Check if we have cached data and it's not too old
        current_time = time.time()
        refresh_interval = self.refresh_intervals.get(city, self.default_refresh_interval)
        
        if city in self.weather_cache and city in self.last_fetch_time:
            time_since_last_fetch = current_time - self.last_fetch_time[city]
            if time_since_last_fetch < refresh_interval:
                logger.debug(f"Using cached weather data for {city}, age: {int(time_since_last_fetch/60)} minutes")
                return self.weather_cache[city]
                
        # If no cache or expired, fetch new data
        logger.info(f"Fetching weather data for {city}")
        
        try:
            # Make API request
            params = {
                "q": city,
                "appid": self.api_key,
                "units": "metric"
            }
            
            response = requests.get(self.base_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Process data into simpler format
                weather_data = self._process_weather_data(data)
                
                # Cache the data
                self.weather_cache[city] = weather_data
                self.last_fetch_time[city] = current_time
                
                # Log for debugging
                minutes_until_refresh = refresh_interval // 60
                logger.info(f"Weather data fetched successfully for {city}, next refresh in {minutes_until_refresh} minutes")
                
                return weather_data
            else:
                logger.error(f"Error fetching weather data: {response.status_code} - {response.text}")
                
                # If we have cached data, use it even though it's expired
                if city in self.weather_cache:
                    logger.info(f"Using expired cached weather data for {city}")
                    return self.weather_cache[city]
                    
                # Otherwise return default data
                return self._get_default_weather_data()
                
        except Exception as e:
            logger.error(f"Error in get_weather: {str(e)}")
            
            # If we have cached data, use it even though it's expired
            if city in self.weather_cache:
                logger.info(f"Using expired cached weather data for {city} after error")
                return self.weather_cache[city]
                
            # Otherwise return default data
            return self._get_default_weather_data()
    
    def _process_weather_data(self, data):
        """Process raw weather data into a simpler format"""
        try:
            # Extract weather condition
            condition = "Unknown"
            if "weather" in data and len(data["weather"]) > 0:
                condition = data["weather"][0].get("main", "Unknown")
            
            # Handle sunrise and sunset times properly
            sunrise_timestamp = data.get("sys", {}).get("sunrise", 0)
            sunset_timestamp = data.get("sys", {}).get("sunset", 0)
            
            # Use datetime.fromtimestamp directly from the datetime class
            from datetime import datetime as dt
            sunrise_time = dt.fromtimestamp(sunrise_timestamp).strftime("%H:%M") if sunrise_timestamp else "06:00"
            sunset_time = dt.fromtimestamp(sunset_timestamp).strftime("%H:%M") if sunset_timestamp else "18:00"
                
            # Create simplified weather data structure
            weather_data = {
                "temperature": data.get("main", {}).get("temp", 0),
                "humidity": data.get("main", {}).get("humidity", 0),
                "pressure": data.get("main", {}).get("pressure", 0),
                "wind_speed": data.get("wind", {}).get("speed", 0),
                "wind_direction": data.get("wind", {}).get("deg", 0),
                "clouds": data.get("clouds", {}).get("all", 0),
                "visibility": data.get("visibility", 10000) / 1000,  # Convert to km
                "condition": condition,
                "description": data.get("weather", [{}])[0].get("description", ""),
                "icon": data.get("weather", [{}])[0].get("icon", ""),
                "city": data.get("name", ""),
                "country": data.get("sys", {}).get("country", ""),
                "timestamp": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sunrise": sunrise_time,
                "sunset": sunset_time
            }
            return weather_data
        except Exception as e:
            logger.error(f"Error processing weather data: {str(e)}")
            return self._get_default_weather_data()
    
    def _get_default_weather_data(self):
        """Return default weather data when API fails"""
        return {
            "temperature": 25,
            "humidity": 80,
            "pressure": 1013,
            "wind_speed": 1.5,
            "wind_direction": 0,
            "clouds": 50,
            "visibility": 10,
            "condition": "Unknown",
            "description": "No data available",
            "icon": "50d",
            "city": "Unknown",
            "country": "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sunrise": "06:00",
            "sunset": "18:00"
        }
        
    def clear_cache(self, city=None):
        """Clear weather cache for a specific city or all cities"""
        if city:
            if city in self.weather_cache:
                del self.weather_cache[city]
                if city in self.last_fetch_time:
                    del self.last_fetch_time[city]
                logger.info(f"Cleared weather cache for {city}")
        else:
            self.weather_cache = {}
            self.last_fetch_time = {}
            logger.info("Cleared all weather cache")
        return True 