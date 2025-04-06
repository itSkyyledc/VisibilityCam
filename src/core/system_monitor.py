import os
import time
import logging
import threading
import json
import psutil
from datetime import datetime

from ..database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class SystemMonitor:
    """
    System monitoring module to track performance metrics
    and store them in the database.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Implement singleton pattern"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SystemMonitor, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
            
    def __init__(self):
        """Initialize the system monitor"""
        if self._initialized:
            return
            
        logger.info("Initializing SystemMonitor")
        
        # Configuration
        self.metrics_interval = 60  # seconds between metrics collection
        self.retention_period = 7   # days to keep metrics
        self.enabled = True
        self.db_manager = DatabaseManager()
        
        # Metrics tracking
        self.camera_managers = {}
        self.last_metrics_time = 0
        self.network_interfaces = {}
        self.previous_net_io = {}
        self.error_count = 0
        self.connection_failures = 0
        self.total_frames_processed = 0
        
        # Initialize network interfaces for monitoring
        self._init_network_interfaces()
        
        # Start monitoring thread
        self.monitor_thread = None
        self._stop_event = threading.Event()
        
        self._initialized = True
        
    def _init_network_interfaces(self):
        """Initialize network interfaces to monitor"""
        try:
            net_io = psutil.net_io_counters(pernic=True)
            self.network_interfaces = {
                iface: {"bytes_sent": 0, "bytes_recv": 0, "speed": 0}
                for iface in net_io.keys() if iface != 'lo'
            }
            self.previous_net_io = net_io
        except Exception as e:
            logger.error(f"Failed to initialize network interfaces: {str(e)}")
            
    def start(self):
        """Start the monitoring thread"""
        if self.monitor_thread is not None and self.monitor_thread.is_alive():
            logger.warning("SystemMonitor is already running")
            return
            
        logger.info("Starting SystemMonitor thread")
        self._stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
    def stop(self):
        """Stop the monitoring thread"""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            return
            
        logger.info("Stopping SystemMonitor thread")
        self._stop_event.set()
        self.monitor_thread.join(timeout=5)
        
    def set_camera_managers(self, camera_managers):
        """Set the camera managers to monitor"""
        self.camera_managers = camera_managers
        
    def register_connection_failure(self):
        """Register a connection failure"""
        self.connection_failures += 1
        
    def register_error(self):
        """Register an error"""
        self.error_count += 1
        
    def reset_counters(self):
        """Reset error counters"""
        self.error_count = 0
        self.connection_failures = 0
        
    def _monitoring_loop(self):
        """Main monitoring loop that collects and stores metrics"""
        logger.info("Monitoring loop started")
        
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                
                # Check if it's time to collect metrics
                if current_time - self.last_metrics_time >= self.metrics_interval:
                    self._collect_and_store_metrics()
                    self.last_metrics_time = current_time
                    
                # Cleanup old metrics once a day
                if datetime.now().hour == 2 and datetime.now().minute < 5:  # 2:00-2:05 AM
                    self._cleanup_old_metrics()
                    
                # Sleep for a bit to avoid consuming too much CPU
                time.sleep(5)
                    
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                time.sleep(30)  # Sleep longer after an error
                
        logger.info("Monitoring loop stopped")
                
    def _collect_and_store_metrics(self):
        """Collect system metrics and store them in the database"""
        try:
            # Collect system metrics
            metrics = self._collect_metrics()
            
            # Store in database
            self.db_manager.log_performance_metrics(metrics)
            
            logger.debug(f"Collected and stored system metrics: CPU {metrics['cpu_usage']:.1f}%, Memory {metrics['memory_usage']:.1f}MB")
            
        except Exception as e:
            logger.error(f"Failed to collect or store metrics: {str(e)}")
            self.error_count += 1
            
    def _collect_metrics(self):
        """Collect system performance metrics"""
        metrics = {
            'cpu_usage': 0,
            'memory_usage': 0,
            'disk_usage': 0,
            'network_speed': 0,
            'frames_processed': 0,
            'processing_time': 0,
            'camera_count': 0,
            'active_rois': 0,
            'error_count': self.error_count,
            'connection_failures': self.connection_failures,
            'system_info': '{}'
        }
        
        try:
            # CPU usage (average across all cores)
            metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
            
            # Memory usage (MB)
            memory = psutil.virtual_memory()
            metrics['memory_usage'] = memory.used / (1024 * 1024)  # Convert to MB
            
            # Disk usage (percentage)
            disk = psutil.disk_usage('/')
            metrics['disk_usage'] = disk.percent
            
            # Network speed (Mbps)
            net_io = psutil.net_io_counters(pernic=True)
            total_bytes_sent = 0
            total_bytes_recv = 0
            
            for iface, prev_io in self.previous_net_io.items():
                if iface in net_io and iface in self.network_interfaces:
                    # Calculate bytes sent/received since last check
                    bytes_sent = net_io[iface].bytes_sent - prev_io.bytes_sent
                    bytes_recv = net_io[iface].bytes_recv - prev_io.bytes_recv
                    
                    total_bytes_sent += bytes_sent
                    total_bytes_recv += bytes_recv
                    
                    # Update previous values
                    self.network_interfaces[iface] = {
                        "bytes_sent": bytes_sent,
                        "bytes_recv": bytes_recv,
                        "speed": (bytes_sent + bytes_recv) / (self.metrics_interval * 125000)  # Mbps
                    }
            
            # Update previous network IO counters
            self.previous_net_io = net_io
            
            # Calculate total network speed in Mbps (bytes per second / 125000)
            metrics['network_speed'] = (total_bytes_sent + total_bytes_recv) / (self.metrics_interval * 125000)
            
            # Camera metrics
            active_cameras = 0
            total_frames = 0
            total_processing_time = 0
            total_rois = 0
            
            for camera_id, cm in self.camera_managers.items():
                if cm.is_connected():
                    active_cameras += 1
                    
                status = cm.get_status()
                camera_data = cm.get_camera_data()
                
                # Count frames processed
                frames = getattr(cm, 'frames_processed', 0)
                total_frames += frames
                
                # Average processing time
                proc_time = getattr(cm, 'avg_processing_time', 0)
                if proc_time > 0:
                    total_processing_time += proc_time
                    
                # Count ROIs
                rois = len(getattr(cm, 'roi_regions', []))
                total_rois += rois
            
            metrics['frames_processed'] = total_frames - self.total_frames_processed
            self.total_frames_processed = total_frames
            
            metrics['processing_time'] = total_processing_time / max(active_cameras, 1)
            metrics['camera_count'] = active_cameras
            metrics['active_rois'] = total_rois
            
            # System info as JSON
            system_info = {
                'python_version': os.sys.version.split()[0],
                'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown',
                'platform': os.sys.platform,
                'cpu_count': psutil.cpu_count(),
                'total_memory': psutil.virtual_memory().total / (1024 * 1024 * 1024),  # GB
                'total_disk': psutil.disk_usage('/').total / (1024 * 1024 * 1024),  # GB
                'uptime': time.time() - psutil.boot_time()
            }
            
            metrics['system_info'] = json.dumps(system_info)
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {str(e)}")
            
        return metrics
        
    def _cleanup_old_metrics(self):
        """Clean up old metrics from the database"""
        try:
            # Clean up metrics older than retention_period days
            result = self.db_manager.cleanup_old_metrics(days_to_keep=self.retention_period)
            if result:
                logger.info(f"Successfully cleaned up performance metrics older than {self.retention_period} days")
            else:
                logger.warning("Failed to clean up old performance metrics")
        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {str(e)}")
            
    def get_current_metrics(self):
        """Get the most recently collected metrics"""
        metrics = self._collect_metrics()
        return metrics
        
    def get_metrics_history(self, hours=24):
        """Get metrics history for the specified time period"""
        return self.db_manager.get_performance_history(hours) 