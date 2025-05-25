"""
Utility functions for the JICAP Vendor Classification System
"""

import pandas as pd
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from .config import Config
from .logger_config import get_logger

class DataValidator:
    """Utility class for data validation"""
    
    def __init__(self):
        self.logger = get_logger('data_validator')
    
    def validate_siren(self, siren: str) -> bool:
        """
        Validate SIREN number format
        
        Args:
            siren: SIREN number to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Handle None and pandas NA values
        if siren is None:
            return False
        
        # Handle pandas NA values explicitly
        try:
            if pd.isna(siren):
                return False
        except (TypeError, ValueError):
            # In case pd.isna fails with certain types
            pass
        
        # Convert to string and check if empty
        siren_str = str(siren).strip()
        if not siren_str or siren_str == 'nan' or siren_str == '<NA>':
            return False
        
        # Basic format validation (should be digits, typically 9 digits for French SIREN)
        if not siren_str.isdigit():
            return False
        
        # Length validation (flexible for different countries)
        if len(siren_str) < 6 or len(siren_str) > 15:
            return False
        
        return True
    
    def validate_country_code(self, country: str) -> bool:
        """
        Validate country code
        
        Args:
            country: Country code to validate
            
        Returns:
            True if valid and supported, False otherwise
        """
        if not country or pd.isna(country):
            return False
        
        return Config.is_supported_country(str(country).strip())
    
    def clean_company_name(self, name: str) -> str:
        """
        Clean and standardize company name
        
        Args:
            name: Raw company name
            
        Returns:
            Cleaned company name
        """
        if not name or pd.isna(name) or name == "N/A":
            return "N/A"
        
        # Remove extra whitespace and quotes
        cleaned = str(name).strip().replace('"', '').replace("'", "'")
        
        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned
    
    def clean_activity_code(self, code: str) -> str:
        """
        Clean and standardize activity code
        
        Args:
            code: Raw activity code
            
        Returns:
            Cleaned activity code
        """
        if not code or pd.isna(code) or code == "N/A":
            return "N/A"
        
        # Remove whitespace and standardize format
        cleaned = str(code).strip()
        
        # Common patterns: "12.34", "1234", "12-34"
        # Standardize to dot notation if it looks like a code
        if re.match(r'^\d{2,3}[-.]?\d{2,3}$', cleaned):
            cleaned = re.sub(r'[-]', '.', cleaned)
        
        return cleaned

class FileUtils:
    """Utility class for file operations"""
    
    @staticmethod
    def ensure_directory(directory_path: str) -> bool:
        """
        Ensure directory exists, create if it doesn't
        
        Args:
            directory_path: Path to directory
            
        Returns:
            True if directory exists or was created successfully
        """
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_file_size_mb(file_path: str) -> float:
        """
        Get file size in megabytes
        
        Args:
            file_path: Path to file
            
        Returns:
            File size in MB
        """
        try:
            return os.path.getsize(file_path) / (1024 * 1024)
        except Exception:
            return 0.0
    
    @staticmethod
    def is_file_accessible(file_path: str) -> bool:
        """
        Check if file is accessible for reading
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is accessible
        """
        try:
            return os.path.isfile(file_path) and os.access(file_path, os.R_OK)
        except Exception:
            return False

class ProgressTracker:
    """Utility class for tracking processing progress"""
    
    def __init__(self, total_items: int):
        self.total_items = total_items
        self.processed_items = 0
        self.start_time = datetime.now()
        self.errors = 0
        self.successes = 0
    
    def update(self, processed: int = 1, error: bool = False):
        """Update progress counters"""
        self.processed_items += processed
        if error:
            self.errors += processed
        else:
            self.successes += processed
    
    def get_progress_percentage(self) -> float:
        """Get progress as percentage"""
        if self.total_items == 0:
            return 100.0
        return (self.processed_items / self.total_items) * 100
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.processed_items == 0:
            return 0.0
        return (self.successes / self.processed_items) * 100
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def get_estimated_remaining_time(self) -> Optional[float]:
        """Get estimated remaining time in seconds"""
        if self.processed_items == 0:
            return None
        
        elapsed = self.get_elapsed_time()
        rate = self.processed_items / elapsed
        remaining_items = self.total_items - self.processed_items
        
        if rate > 0:
            return remaining_items / rate
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive progress statistics"""
        return {
            'total_items': self.total_items,
            'processed_items': self.processed_items,
            'remaining_items': self.total_items - self.processed_items,
            'progress_percentage': self.get_progress_percentage(),
            'success_rate': self.get_success_rate(),
            'errors': self.errors,
            'successes': self.successes,
            'elapsed_time_seconds': self.get_elapsed_time(),
            'estimated_remaining_seconds': self.get_estimated_remaining_time()
        }

class RetryHelper:
    """Utility class for implementing retry logic"""
    
    @staticmethod
    def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        """
        Calculate exponential backoff delay
        
        Args:
            attempt: Current attempt number (starting from 0)
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            
        Returns:
            Delay in seconds
        """
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)
    
    @staticmethod
    def should_retry(exception: Exception, attempt: int, max_attempts: int) -> bool:
        """
        Determine if an operation should be retried
        
        Args:
            exception: The exception that occurred
            attempt: Current attempt number
            max_attempts: Maximum number of attempts
            
        Returns:
            True if should retry, False otherwise
        """
        if attempt >= max_attempts:
            return False
        
        # Don't retry for certain types of errors
        if isinstance(exception, (ValueError, TypeError, KeyError)):
            return False
        
        # Retry for network-related errors
        if "timeout" in str(exception).lower():
            return True
        if "connection" in str(exception).lower():
            return True
        if "network" in str(exception).lower():
            return True
        
        return True

def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human-readable string
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        return f"{hours}h {remaining_minutes}m"

def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable string
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = "unnamed_file"
    
    return sanitized
