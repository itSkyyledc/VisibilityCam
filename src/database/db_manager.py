import sqlite3
import logging
import datetime
import os
from pathlib import Path
from ..config.settings import DATA_DIR

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_path = DATA_DIR / "visibility_cam.db"
        self.db_path.parent.mkdir(exist_ok=True)
    
    def setup_database(self):
        """Initialize the SQLite database for analytics storage"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS visibility_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    brightness REAL NOT NULL,
                    is_corrupted BOOLEAN NOT NULL,
                    is_poor_visibility BOOLEAN NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    min_brightness REAL,
                    max_brightness REAL,
                    avg_brightness REAL,
                    total_samples INTEGER,
                    visibility_duration INTEGER,
                    max_visibility_duration INTEGER,
                    reconnect_count INTEGER,
                    corruption_count INTEGER,
                    uptime_percentage REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(camera_id, date)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weather_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    temperature REAL,
                    humidity INTEGER,
                    condition TEXT,
                    wind_speed REAL,
                    pressure INTEGER,
                    visibility INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    file_path TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_visibility_metrics_camera_timestamp ON visibility_metrics(camera_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_stats_camera_date ON daily_stats(camera_id, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_weather_data_city_timestamp ON weather_data(city, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_camera_timestamp ON events(camera_id, timestamp)")
            
            conn.commit()
            logger.info("Database setup completed successfully")
            
        except Exception as e:
            logger.error(f"Database setup failed: {str(e)}")
            raise
        finally:
            conn.close()
    
    def log_brightness_sample(self, camera_id, timestamp, brightness, is_corrupted, is_poor_visibility):
        """Log a brightness sample with error handling"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Insert the sample
            cursor.execute("""
                INSERT INTO visibility_metrics
                (camera_id, timestamp, brightness, is_corrupted, is_poor_visibility)
                VALUES (?, ?, ?, ?, ?)
            """, (camera_id, timestamp, brightness, is_corrupted, is_poor_visibility))
            
            # Update daily stats
            date = timestamp.date()
            cursor.execute("""
                INSERT OR REPLACE INTO daily_stats
                (camera_id, date, min_brightness, max_brightness, avg_brightness,
                 total_samples, visibility_duration, max_visibility_duration,
                 reconnect_count, corruption_count, uptime_percentage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                camera_id, date,
                min(brightness, self._get_daily_min(cursor, camera_id, date)),
                max(brightness, self._get_daily_max(cursor, camera_id, date)),
                self._calculate_daily_avg(cursor, camera_id, date),
                self._get_daily_samples(cursor, camera_id, date) + 1,
                self._calculate_visibility_duration(cursor, camera_id, date),
                self._get_max_visibility_duration(cursor, camera_id, date),
                self._get_reconnect_count(cursor, camera_id, date),
                self._get_corruption_count(cursor, camera_id, date) + (1 if is_corrupted else 0),
                self._calculate_uptime_percentage(cursor, camera_id, date)
            ))
            
            conn.commit()
            
        except sqlite3.Error as e:
            logger.error(f"Database error while logging brightness sample: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
        except Exception as e:
            logger.error(f"Unexpected error while logging brightness sample: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _get_daily_min(self, cursor, camera_id, date):
        """Get minimum brightness for a day"""
        cursor.execute("""
            SELECT MIN(brightness) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else float('inf')
    
    def _get_daily_max(self, cursor, camera_id, date):
        """Get maximum brightness for a day"""
        cursor.execute("""
            SELECT MAX(brightness) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _calculate_daily_avg(self, cursor, camera_id, date):
        """Calculate average brightness for a day"""
        cursor.execute("""
            SELECT AVG(brightness) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _get_daily_samples(self, cursor, camera_id, date):
        """Get number of samples for a day"""
        cursor.execute("""
            SELECT COUNT(*) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _calculate_visibility_duration(self, cursor, camera_id, date):
        """Calculate visibility duration for a day"""
        cursor.execute("""
            SELECT COUNT(*) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ? AND is_poor_visibility = 0
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _get_max_visibility_duration(self, cursor, camera_id, date):
        """Get maximum visibility duration for a day"""
        cursor.execute("""
            SELECT MAX(visibility_duration) FROM daily_stats
            WHERE camera_id = ? AND date = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _get_reconnect_count(self, cursor, camera_id, date):
        """Get reconnect count for a day"""
        cursor.execute("""
            SELECT reconnect_count FROM daily_stats
            WHERE camera_id = ? AND date = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _get_corruption_count(self, cursor, camera_id, date):
        """Get corruption count for a day"""
        cursor.execute("""
            SELECT corruption_count FROM daily_stats
            WHERE camera_id = ? AND date = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    
    def _calculate_uptime_percentage(self, cursor, camera_id, date):
        """Calculate uptime percentage for a day"""
        cursor.execute("""
            SELECT COUNT(*) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ?
        """, (camera_id, date))
        result = cursor.fetchone()
        total_samples = result[0] if result and result[0] is not None else 0
        
        if total_samples == 0:
            return 100.0
            
        cursor.execute("""
            SELECT COUNT(*) FROM visibility_metrics
            WHERE camera_id = ? AND date(timestamp) = ? AND is_corrupted = 0
        """, (camera_id, date))
        result = cursor.fetchone()
        valid_samples = result[0] if result and result[0] is not None else 0
        
        return (valid_samples / total_samples) * 100.0 if total_samples > 0 else 100.0
    
    def save_daily_stats(self, camera_id, stats):
        """Save daily statistics to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if stats exist for the date
            cursor.execute("""
                SELECT id FROM daily_stats 
                WHERE camera_id = ? AND date = ?
            """, (camera_id, stats['date']))
            
            result = cursor.fetchone()
            
            if result:
                # Update existing stats
                cursor.execute("""
                    UPDATE daily_stats SET
                    min_brightness = ?,
                    max_brightness = ?,
                    avg_brightness = ?,
                    total_samples = ?,
                    visibility_duration = ?,
                    max_visibility_duration = ?,
                    reconnect_count = ?,
                    corruption_count = ?,
                    uptime_percentage = ?
                    WHERE camera_id = ? AND date = ?
                """, (
                    stats['min_brightness'],
                    stats['max_brightness'],
                    stats['avg_brightness'],
                    stats['total_samples'],
                    stats['visibility_duration'],
                    stats['max_visibility_duration'],
                    stats['reconnect_count'],
                    stats['corruption_count'],
                    stats['uptime_percentage'],
                    camera_id,
                    stats['date']
                ))
            else:
                # Insert new stats
                cursor.execute("""
                    INSERT INTO daily_stats 
                    (camera_id, date, min_brightness, max_brightness, avg_brightness,
                     total_samples, visibility_duration, max_visibility_duration,
                     reconnect_count, corruption_count, uptime_percentage)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    camera_id,
                    stats['date'],
                    stats['min_brightness'],
                    stats['max_brightness'],
                    stats['avg_brightness'],
                    stats['total_samples'],
                    stats['visibility_duration'],
                    stats['max_visibility_duration'],
                    stats['reconnect_count'],
                    stats['corruption_count'],
                    stats['uptime_percentage']
                ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error saving daily stats: {str(e)}")
        finally:
            conn.close()
    
    def save_weather_data(self, city, weather_data):
        """Save weather data to database"""
        try:
            if not weather_data:
                return
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO weather_data 
                (city, timestamp, temperature, humidity, condition, wind_speed, pressure, visibility)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                city,
                weather_data['timestamp'],
                weather_data['temperature'],
                weather_data['humidity'],
                weather_data['condition'],
                weather_data['wind_speed'],
                weather_data['pressure'],
                weather_data['visibility']
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error saving weather data: {str(e)}")
        finally:
            conn.close()
    
    def log_highlight_event(self, camera_id, timestamp, file_path):
        """Log highlight event to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO events (camera_id, event_type, timestamp, file_path)
                VALUES (?, 'highlight', ?, ?)
            """, (camera_id, timestamp, file_path))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error logging highlight event: {str(e)}")
        finally:
            conn.close()
    
    def get_historical_stats(self, camera_id, days=7):
        """Get historical statistics for a camera"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get daily stats for the specified period
            cursor.execute("""
                SELECT date, min_brightness, max_brightness, avg_brightness,
                       total_samples, visibility_duration, max_visibility_duration,
                       reconnect_count, corruption_count, uptime_percentage
                FROM daily_stats
                WHERE camera_id = ? AND date >= date('now', ?)
                ORDER BY date DESC
            """, (camera_id, f'-{days} days'))
            
            results = cursor.fetchall()
            
            if not results:
                return []
            
            # Format the results
            historical_data = []
            for row in results:
                historical_data.append({
                    'date': row[0],
                    'min_brightness': row[1],
                    'max_brightness': row[2],
                    'avg_brightness': row[3],
                    'total_samples': row[4],
                    'visibility_duration': row[5],
                    'max_visibility_duration': row[6],
                    'reconnect_count': row[7],
                    'corruption_count': row[8],
                    'uptime_percentage': row[9]
                })
            
            return historical_data
            
        except sqlite3.Error as e:
            logger.error(f"Database error while getting historical stats: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error while getting historical stats: {str(e)}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()
    
    def backup_database(self):
        """Create a backup of the database"""
        try:
            if not self.db_path.exists():
                logger.warning("No database file found to backup")
                return False
            
            backup_dir = DATA_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"visibility_cam_backup_{timestamp}.db"
            
            # Create backup
            with open(self.db_path, 'rb') as source:
                with open(backup_path, 'wb') as target:
                    target.write(source.read())
            
            # Remove old backups (keep last 5)
            backups = sorted(backup_dir.glob("visibility_cam_backup_*.db"))
            if len(backups) > 5:
                for old_backup in backups[:-5]:
                    old_backup.unlink()
            
            logger.info(f"Database backup created: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Database backup failed: {str(e)}")
            return False 