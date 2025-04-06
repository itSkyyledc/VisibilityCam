import sqlite3
import logging
import datetime
import os
import threading
import queue
from pathlib import Path
from ..config.settings import DATA_DIR

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Implement singleton pattern for database connections"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Initialize the database manager with a connection pool"""
        if self._initialized:
            return
            
        self.db_path = DATA_DIR / "visibility_cam.db"
        self.db_path.parent.mkdir(exist_ok=True)
        
        # Connection pool settings
        self.max_connections = 5
        self.connection_pool = queue.Queue(maxsize=self.max_connections)
        self.active_connections = 0
        self.pool_lock = threading.Lock()
        
        # Initialize connection pool
        self._init_connection_pool()
        
        # Initialize the database schema
        self.setup_database()
        
        self._initialized = True
    
    def _init_connection_pool(self):
        """Initialize the connection pool with some connections"""
        logger.info("Initializing database connection pool")
        try:
            for _ in range(min(2, self.max_connections)):  # Start with a few connections
                connection = self._create_connection()
                if connection:
                    self.connection_pool.put(connection)
                    self.active_connections += 1
            logger.info(f"Connection pool initialized with {self.active_connections} connections")
        except Exception as e:
            logger.error(f"Error initializing connection pool: {str(e)}")
    
    def _create_connection(self):
        """Create a new database connection"""
        try:
            # Enable foreign keys and set timeout
            connection = sqlite3.connect(
                str(self.db_path), 
                timeout=30.0,
                isolation_level=None,  # Enable autocommit mode
                check_same_thread=False  # Allow connections to be used across threads
            )
            
            # Set pragmas for better performance
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA cache_size = 10000")  # 10MB cache
            
            return connection
        except Exception as e:
            logger.error(f"Error creating database connection: {str(e)}")
            return None
    
    def get_connection(self):
        """Get a database connection from the pool or create a new one"""
        connection = None
        
        try:
            # Try to get a connection from the pool first
            try:
                connection = self.connection_pool.get(block=False)
                logger.debug("Retrieved connection from pool")
                return connection
            except queue.Empty:
                # Pool is empty, create a new connection if under the limit
                with self.pool_lock:
                    if self.active_connections < self.max_connections:
                        connection = self._create_connection()
                        if connection:
                            self.active_connections += 1
                            logger.debug(f"Created new connection. Active: {self.active_connections}")
                            return connection
                    
                # Wait for a connection if at the limit
                logger.debug("Waiting for connection from pool")
                connection = self.connection_pool.get(block=True, timeout=10)
                return connection
        except Exception as e:
            logger.error(f"Error getting database connection: {str(e)}")
            # Last resort: create a new connection even if over the limit
            try:
                connection = self._create_connection()
                logger.warning("Created emergency connection outside of pool limits")
                return connection
            except Exception as e2:
                logger.error(f"Critical error creating database connection: {str(e2)}")
                raise
    
    def release_connection(self, connection):
        """Return a connection to the pool"""
        if connection is None:
            return
            
        try:
            # Try to add the connection back to the pool
            try:
                self.connection_pool.put(connection, block=False)
                logger.debug("Connection returned to pool")
            except queue.Full:
                # Pool is full, close the connection
                connection.close()
                with self.pool_lock:
                    self.active_connections -= 1
                logger.debug(f"Closed connection due to full pool. Active: {self.active_connections}")
        except Exception as e:
            logger.error(f"Error releasing database connection: {str(e)}")
            # Make sure we close the connection
            try:
                connection.close()
                with self.pool_lock:
                    self.active_connections -= 1
            except:
                pass
    
    def cleanup(self):
        """Clean up all database connections"""
        logger.info("Cleaning up database connections")
        try:
            # Empty the pool and close all connections
            while not self.connection_pool.empty():
                try:
                    connection = self.connection_pool.get(block=False)
                    if connection:
                        connection.close()
                except Exception:
                    pass
            
            self.active_connections = 0
            logger.info("All database connections closed")
        except Exception as e:
            logger.error(f"Error during database cleanup: {str(e)}")
    
    def setup_database(self):
        """Initialize the SQLite database for analytics storage"""
        conn = None
        try:
            conn = self.get_connection()
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
            
            # Create performance metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    cpu_usage REAL,
                    memory_usage REAL,
                    disk_usage REAL,
                    network_speed REAL,
                    frames_processed INTEGER,
                    processing_time REAL,
                    camera_count INTEGER,
                    active_rois INTEGER,
                    error_count INTEGER,
                    connection_failures INTEGER,
                    system_info TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_visibility_metrics_camera_timestamp ON visibility_metrics(camera_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_stats_camera_date ON daily_stats(camera_id, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_weather_data_city_timestamp ON weather_data(city, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_camera_timestamp ON events(camera_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp)")
            
            conn.commit()
            logger.info("Database setup completed successfully")
            
        except Exception as e:
            logger.error(f"Database setup failed: {str(e)}")
            raise
        finally:
            self.release_connection(conn)
    
    def log_brightness_sample(self, camera_id, timestamp, brightness, is_corrupted, is_poor_visibility):
        """Log a brightness sample with error handling"""
        try:
            conn = self.get_connection()
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
            self.release_connection(conn)
    
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
            conn = self.get_connection()
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
            self.release_connection(conn)
    
    def save_weather_data(self, city, weather_data):
        """Save weather data to database"""
        try:
            if not weather_data:
                return
            
            conn = self.get_connection()
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
            self.release_connection(conn)
    
    def log_highlight_event(self, camera_id, timestamp, file_path):
        """Log highlight event to database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO events (camera_id, event_type, timestamp, file_path)
                VALUES (?, 'highlight', ?, ?)
            """, (camera_id, timestamp, file_path))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error logging highlight event: {str(e)}")
        finally:
            self.release_connection(conn)
    
    def get_historical_stats(self, camera_id, days=7):
        """Get historical statistics for a camera"""
        try:
            conn = self.get_connection()
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
            self.release_connection(conn)
    
    def backup_database(self):
        """Create a backup of the database"""
        try:
            backup_dir = DATA_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"visibility_cam_backup_{timestamp}.db"
            
            # Temporarily pause any active connections for backup
            logger.info("Starting database backup...")
            
            # Get a dedicated connection for backup
            conn = self._create_connection()
            if not conn:
                logger.error("Failed to create connection for backup")
                return False
                
            try:
            # Create backup
                backup_conn = sqlite3.connect(str(backup_path))
                conn.execute("BEGIN IMMEDIATE")  # Lock database
                conn.backup(backup_conn)
                backup_conn.close()
                logger.info(f"Database backup created at {backup_path}")
                
                # Delete old backups (keep last 5)
                backup_files = sorted(list(backup_dir.glob("visibility_cam_backup_*.db")))
                if len(backup_files) > 5:
                    for old_file in backup_files[:-5]:
                        try:
                            old_file.unlink()
                            logger.info(f"Deleted old backup: {old_file}")
                        except Exception as e:
                            logger.error(f"Failed to delete old backup {old_file}: {str(e)}")
                
                return True
            finally:
                conn.execute("COMMIT")  # Release lock
                conn.close()  # Close the dedicated connection
                
        except Exception as e:
            logger.error(f"Database backup failed: {str(e)}")
            return False
    
    def execute_with_transaction(self, query, params=None):
        """Execute a query within a transaction with proper error handling"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("BEGIN TRANSACTION")
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            
            return cursor.lastrowid
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Transaction failed: {str(e)}")
            raise
        finally:
            self.release_connection(conn)
    
    def fetch_all(self, query, params=None):
        """Execute a query and fetch all results with proper error handling"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
                
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            return []
        finally:
            self.release_connection(conn)
    
    def fetch_one(self, query, params=None):
        """Execute a query and fetch one result with proper error handling"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
                
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            return None
        finally:
            self.release_connection(conn)
    
    def log_performance_metrics(self, metrics):
        """Log system performance metrics
        
        Args:
            metrics (dict): Dictionary containing performance metrics:
                - cpu_usage: CPU usage percentage
                - memory_usage: Memory usage in MB
                - disk_usage: Disk usage percentage
                - network_speed: Network speed in Mbps
                - frames_processed: Number of frames processed
                - processing_time: Processing time in ms
                - camera_count: Number of active cameras
                - active_rois: Number of active ROIs
                - error_count: Number of errors
                - connection_failures: Number of connection failures
                - system_info: JSON string with system information
        """
        if not metrics:
            logger.warning("No performance metrics provided")
            return
            
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("BEGIN TRANSACTION")
            
            cursor.execute("""
                INSERT INTO performance_metrics (
                    timestamp, cpu_usage, memory_usage, disk_usage, 
                    network_speed, frames_processed, processing_time,
                    camera_count, active_rois, error_count, 
                    connection_failures, system_info
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.datetime.now(),
                metrics.get('cpu_usage', 0),
                metrics.get('memory_usage', 0),
                metrics.get('disk_usage', 0),
                metrics.get('network_speed', 0),
                metrics.get('frames_processed', 0),
                metrics.get('processing_time', 0),
                metrics.get('camera_count', 0),
                metrics.get('active_rois', 0),
                metrics.get('error_count', 0),
                metrics.get('connection_failures', 0),
                metrics.get('system_info', '{}')
            ))
            
            conn.commit()
            logger.debug("Performance metrics logged successfully")
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error logging performance metrics: {str(e)}")
        finally:
            self.release_connection(conn)
            
    def get_performance_history(self, hours=24):
        """Get performance metrics history for the specified time period
        
        Args:
            hours (int): Number of hours to look back
            
        Returns:
            list: List of performance metric records
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            time_threshold = datetime.datetime.now() - datetime.timedelta(hours=hours)
            
            cursor.execute("""
                SELECT 
                    timestamp, cpu_usage, memory_usage, frames_processed, 
                    processing_time, camera_count, error_count
                FROM 
                    performance_metrics
                WHERE 
                    timestamp > ?
                ORDER BY 
                    timestamp ASC
            """, (time_threshold,))
            
            results = cursor.fetchall()
            
            # Convert to list of dictionaries
            metrics_history = []
            for row in results:
                metrics_history.append({
                    'timestamp': row[0],
                    'cpu_usage': row[1],
                    'memory_usage': row[2],
                    'frames_processed': row[3],
                    'processing_time': row[4],
                    'camera_count': row[5],
                    'error_count': row[6]
                })
                
            return metrics_history
            
        except Exception as e:
            logger.error(f"Error retrieving performance history: {str(e)}")
            return []
        finally:
            self.release_connection(conn)
    
    def cleanup_old_metrics(self, days_to_keep=7):
        """Remove performance metrics older than the specified number of days
        
        Args:
            days_to_keep (int): Number of days of data to keep
        
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Calculate cutoff date
            import datetime
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_to_keep)
            
            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # Delete old metrics
            cursor.execute("""
                DELETE FROM performance_metrics
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            # Get number of deleted rows
            deleted_count = cursor.rowcount
            
            # Commit transaction
            conn.commit()
            
            # Vacuum database to reclaim space (must be outside transaction)
            conn.execute("VACUUM")
            
            logger.info(f"Cleaned up {deleted_count} old performance metrics records")
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error cleaning up old metrics: {str(e)}")
            return False 
            
        finally:
            self.release_connection(conn) 