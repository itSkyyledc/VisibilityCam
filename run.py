#!/usr/bin/env python
import os
import sys
from pathlib import Path
import logging
import time

# Add the project root directory to the Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Configure basic logging first for early errors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('visibilitycam.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("VisibilityCam")

# Check for required directories
for directory in ['data', 'recordings', 'highlights', 'logs']:
    path = project_root / directory
    if not path.exists():
        logger.info(f"Creating required directory: {directory}")
        path.mkdir(exist_ok=True)

# Verify API key file exists
api_key_file = project_root / 'api_key.txt'
if not api_key_file.exists():
    logger.warning("API key file not found. Creating placeholder...")
    with open(api_key_file, 'w') as f:
        f.write("YOUR_OPENWEATHER_API_KEY_HERE")
    logger.warning("Please edit api_key.txt with your actual OpenWeather API key")

try:
    # Import and run the main application
    from src.main import main
    
    if __name__ == "__main__":
        logger.info("Starting VisibilityCam...")
        main()
except ImportError as e:
    logger.error(f"Failed to import required module: {e}")
    logger.error("Please make sure all dependencies are installed:")
    logger.error("pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    logger.error(f"Error starting application: {e}", exc_info=True)
    logger.error("Check the log file for details")
    sys.exit(1) 