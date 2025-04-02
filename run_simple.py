#!/usr/bin/env python
import os
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Import and run the main application
from src.main import main

if __name__ == "__main__":
    main() 