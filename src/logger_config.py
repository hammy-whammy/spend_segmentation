"""
Logging configuration for the JICAP Vendor Classification System
"""

import logging
import os
from datetime import datetime
from typing import Optional

from .config import Config

def setup_logging(log_level: str = None, log_file: str = None) -> logging.Logger:
    """
    Set up logging configuration for the application
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    
    Returns:
        Configured logger instance
    """
    # Ensure log directory exists
    Config.ensure_directories()
    
    # Set log level
    if log_level is None:
        log_level = Config.LOG_LEVEL
    
    # Create log file if not specified
    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(Config.LOG_DIR, f"jicap_processing_{timestamp}.log")
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=Config.LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Get logger for this application
    logger = logging.getLogger('jicap_system')
    
    # Log startup message
    logger.info("JICAP Vendor Classification System - Logging initialized")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Log level: {log_level}")
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(f'jicap_system.{name}')

class ProcessingLogger:
    """Custom logger for processing operations with real-time updates"""
    
    def __init__(self, base_logger: logging.Logger):
        self.logger = base_logger
        self.log_entries = []
        self.error_count = 0
        self.warning_count = 0
        
    def info(self, message: str):
        """Log info message"""
        self.logger.info(message)
        self.log_entries.append(f"INFO: {message}")
        
    def warning(self, message: str):
        """Log warning message"""
        self.logger.warning(message)
        self.log_entries.append(f"WARNING: {message}")
        self.warning_count += 1
        
    def error(self, message: str):
        """Log error message"""
        self.logger.error(message)
        self.log_entries.append(f"ERROR: {message}")
        self.error_count += 1
        
    def debug(self, message: str):
        """Log debug message"""
        self.logger.debug(message)
        self.log_entries.append(f"DEBUG: {message}")
        
    def get_recent_logs(self, count: int = 20) -> list:
        """Get recent log entries"""
        return self.log_entries[-count:] if count > 0 else self.log_entries
        
    def get_stats(self) -> dict:
        """Get logging statistics"""
        return {
            'total_entries': len(self.log_entries),
            'errors': self.error_count,
            'warnings': self.warning_count
        }
        
    def save_log_file(self, file_path: str):
        """Save all log entries to a file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("JICAP Vendor Classification System - Processing Log\n")
                f.write("=" * 60 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Entries: {len(self.log_entries)}\n")
                f.write(f"Errors: {self.error_count}\n")
                f.write(f"Warnings: {self.warning_count}\n")
                f.write("=" * 60 + "\n\n")
                
                for entry in self.log_entries:
                    f.write(f"{entry}\n")
                    
            return file_path
        except Exception as e:
            self.error(f"Failed to save log file: {str(e)}")
            return None
