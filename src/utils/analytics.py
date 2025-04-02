import sqlite3
import logging
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from ..config.settings import DATA_DIR
import time
import json
import numpy as np

logger = logging.getLogger(__name__)

class AnalyticsManager:
    """Analytics manager for storing and retrieving camera metrics"""
    
    _instance = None
    
    def __new__(cls):
        # Singleton pattern to ensure only one database connection
        if cls._instance is None:
            cls._instance = super(AnalyticsManager, cls).__new__(cls)
            cls._instance.db_path = DATA_DIR / "analytics.db"
            cls._instance._init_db()
        return cls._instance
    
    def _init_db(self):
        """Initialize database and create tables if they don't exist"""
        try:
            # Check if initialization has already been performed
            if hasattr(self, '_db_initialized') and self._db_initialized:
                return
                
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Create camera_metrics table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS camera_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                brightness REAL,
                contrast REAL,
                sharpness REAL,
                visibility_score REAL,
                visibility_status TEXT,
                UNIQUE(camera_id, timestamp)
            )
            ''')
            
            # Drop and recreate daily_stats table to ensure correct schema
            try:
                cursor.execute("DROP TABLE IF EXISTS daily_stats")
                logger.info("Dropped existing daily_stats table to fix schema issues")
            except sqlite3.Error as e:
                logger.warning(f"Could not drop daily_stats table: {str(e)}")
            
            # Create daily_stats table with complete schema
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                date DATE NOT NULL,
                min_brightness REAL,
                max_brightness REAL,
                avg_brightness REAL,
                min_visibility_score REAL,
                max_visibility_score REAL,
                avg_visibility_score REAL,
                poor_visibility_count INTEGER DEFAULT 0,
                moderate_visibility_count INTEGER DEFAULT 0,
                good_visibility_count INTEGER DEFAULT 0,
                total_samples INTEGER DEFAULT 0,
                UNIQUE(camera_id, date)
            )
            ''')
            
            conn.commit()
            conn.close()
            
            # Mark as initialized to prevent multiple initializations
            self._db_initialized = True
            
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
    
    def update_daily_stats(self, camera_id, brightness=0, contrast=0, visibility_score=0, visibility_status="Unknown"):
        """Update daily statistics for camera"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Get current date and timestamp
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            
            # Insert current metrics
            cursor.execute('''
            INSERT OR REPLACE INTO camera_metrics (camera_id, timestamp, brightness, contrast, sharpness, visibility_score, visibility_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (camera_id, timestamp, brightness, contrast, 0, visibility_score, visibility_status))
            
            # Update daily stats
            # First, check if entry exists for today
            cursor.execute('''
            SELECT id FROM daily_stats WHERE camera_id = ? AND date = ?
            ''', (camera_id, today))
            
            result = cursor.fetchone()
            
            if result:
                # Update existing entry, safely handling columns that might be missing
                try:
                    cursor.execute('''
                    UPDATE daily_stats SET
                        min_brightness = CASE WHEN min_brightness > ? OR min_brightness IS NULL THEN ? ELSE min_brightness END,
                        max_brightness = CASE WHEN max_brightness < ? OR max_brightness IS NULL THEN ? ELSE max_brightness END,
                        avg_brightness = (avg_brightness * total_samples + ?) / (total_samples + 1),
                        min_visibility_score = CASE WHEN min_visibility_score > ? OR min_visibility_score IS NULL THEN ? ELSE min_visibility_score END,
                        max_visibility_score = CASE WHEN max_visibility_score < ? OR max_visibility_score IS NULL THEN ? ELSE max_visibility_score END,
                        avg_visibility_score = (avg_visibility_score * total_samples + ?) / (total_samples + 1),
                        poor_visibility_count = poor_visibility_count + CASE WHEN ? = 'Poor' THEN 1 ELSE 0 END,
                        moderate_visibility_count = moderate_visibility_count + CASE WHEN ? = 'Moderate' THEN 1 ELSE 0 END,
                        good_visibility_count = good_visibility_count + CASE WHEN ? = 'Good' THEN 1 ELSE 0 END,
                        total_samples = total_samples + 1
                    WHERE camera_id = ? AND date = ?
                    ''', (
                        brightness, brightness,
                        brightness, brightness,
                        brightness,
                        visibility_score, visibility_score,
                        visibility_score, visibility_score,
                        visibility_score,
                        visibility_status, visibility_status, visibility_status,
                        camera_id, today
                    ))
                except sqlite3.OperationalError as e:
                    # If error occurs, use a simpler update that avoids missing columns
                    logger.warning(f"Using fallback update method due to: {str(e)}")
                    cursor.execute('''
                    UPDATE daily_stats SET
                        min_brightness = CASE WHEN min_brightness > ? OR min_brightness IS NULL THEN ? ELSE min_brightness END,
                        max_brightness = CASE WHEN max_brightness < ? OR max_brightness IS NULL THEN ? ELSE max_brightness END,
                        avg_brightness = (avg_brightness * total_samples + ?) / (total_samples + 1),
                        poor_visibility_count = poor_visibility_count + CASE WHEN ? = 'Poor' THEN 1 ELSE 0 END,
                        moderate_visibility_count = moderate_visibility_count + CASE WHEN ? = 'Moderate' THEN 1 ELSE 0 END,
                        good_visibility_count = good_visibility_count + CASE WHEN ? = 'Good' THEN 1 ELSE 0 END,
                        total_samples = total_samples + 1
                    WHERE camera_id = ? AND date = ?
                    ''', (
                        brightness, brightness,
                        brightness, brightness,
                        brightness,
                        visibility_status, visibility_status, visibility_status,
                        camera_id, today
                    ))
            else:
                # Create new entry
                poor_count = 1 if visibility_status == 'Poor' else 0
                moderate_count = 1 if visibility_status == 'Moderate' else 0
                good_count = 1 if visibility_status == 'Good' else 0
                
                try:
                    cursor.execute('''
                    INSERT INTO daily_stats (
                        camera_id, date, min_brightness, max_brightness, avg_brightness,
                        min_visibility_score, max_visibility_score, avg_visibility_score,
                        poor_visibility_count, moderate_visibility_count, good_visibility_count, total_samples
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        camera_id, today, brightness, brightness, brightness,
                        visibility_score, visibility_score, visibility_score,
                        poor_count, moderate_count, good_count, 1
                    ))
                except sqlite3.OperationalError as e:
                    # If error occurs, use a simpler insert that avoids missing columns
                    logger.warning(f"Using fallback insert method due to: {str(e)}")
                    cursor.execute('''
                    INSERT INTO daily_stats (
                        camera_id, date, min_brightness, max_brightness, avg_brightness,
                        poor_visibility_count, moderate_visibility_count, good_visibility_count, total_samples
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        camera_id, today, brightness, brightness, brightness,
                        poor_count, moderate_count, good_count, 1
                    ))
            
            conn.commit()
            conn.close()
            logger.info(f"Updated daily stats for camera {camera_id}")
        except Exception as e:
            logger.error(f"Error updating daily stats: {str(e)}")
            if 'conn' in locals() and conn:
                conn.close()
    
    def get_historical_stats(self, camera_id, start_date, end_date):
        """Get historical statistics for camera"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Format dates
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")
            
            # Query metrics within date range
            cursor.execute('''
            SELECT timestamp, brightness, visibility_score, visibility_status
            FROM camera_metrics
            WHERE camera_id = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            ''', (camera_id, f"{start_date_str} 00:00:00", f"{end_date_str} 23:59:59"))
            
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return {}
            
            # Process results
            timestamps = []
            brightness_values = []
            visibility_scores = []
            visibility_statuses = []
            
            for row in results:
                timestamps.append(datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"))
                brightness_values.append(row[1])
                visibility_scores.append(row[2])
                visibility_statuses.append(row[3])
            
            return {
                'timestamps': timestamps,
                'brightness_values': brightness_values,
                'visibility_scores': visibility_scores,
                'visibility_statuses': visibility_statuses
            }
        except Exception as e:
            logger.error(f"Error retrieving historical stats: {str(e)}")
            return {}

    def add_visibility_data(self, camera_id, data):
        """Add visibility data for a camera"""
        if camera_id not in self.visibility_data:
            self.visibility_data[camera_id] = []
        
        # Add timestamp if not already present
        if 'timestamp' not in data:
            data['timestamp'] = time.time()
            
        # Add to memory
        self.visibility_data[camera_id].append(data)
        
        # Limit data in memory (keep last 1000 points)
        if len(self.visibility_data[camera_id]) > 1000:
            self.visibility_data[camera_id] = self.visibility_data[camera_id][-1000:]
            
        # Save to disk periodically (every 50 data points)
        if len(self.visibility_data[camera_id]) % 50 == 0:
            self._save_data(camera_id)
    
    def get_visibility_data(self, camera_id, limit=100, time_range=None):
        """Get visibility data for a camera"""
        if camera_id not in self.visibility_data:
            return []
            
        data = self.visibility_data[camera_id]
        
        # Filter by time range if provided
        if time_range:
            start_time = time.time() - time_range
            data = [d for d in data if d.get('timestamp', 0) >= start_time]
            
        # Return the last N points
        return data[-limit:]
    
    def get_visibility_stats(self, camera_id, time_range=None):
        """Get visibility statistics for a camera"""
        data = self.get_visibility_data(camera_id, limit=1000, time_range=time_range)
        
        if not data:
            return {}
            
        # Calculate statistics
        stats = {
            'avg_visibility_score': np.mean([d.get('visibility_score', 0) for d in data]),
            'min_visibility_score': min([d.get('visibility_score', 0) for d in data]),
            'max_visibility_score': max([d.get('visibility_score', 0) for d in data]),
            'avg_brightness': np.mean([d.get('brightness', 0) for d in data]),
            'avg_contrast': np.mean([d.get('contrast', 0) for d in data]),
            'data_points': len(data),
            'time_range': time_range
        }
        
        return stats
    
    def _save_data(self, camera_id):
        """Save visibility data to disk"""
        try:
            camera_data_dir = self.data_dir / camera_id
            camera_data_dir.mkdir(exist_ok=True)
            
            # Use current date for filename
            today = datetime.now().strftime("%Y-%m-%d")
            data_file = camera_data_dir / f"visibility_{today}.json"
            
            # Save to file
            with open(data_file, 'w') as f:
                json.dump(self.visibility_data[camera_id], f)
                
            logger.debug(f"Saved visibility data for camera {camera_id} to {data_file}")
        except Exception as e:
            logger.error(f"Error saving visibility data: {str(e)}") 