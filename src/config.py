"""
Configuration settings for the JICAP Vendor Classification System
"""

import os
from typing import Dict, Any

class Config:
    """Configuration class for the application"""
    
    # Database settings
    DATABASE_FILE = "JICAP Company Dataset.xlsx"
    BACKUP_DIR = "backups"
    LOG_DIR = "logs"
    
    # API settings
    FRENCH_API_URL = "https://recherche-entreprises.api.gouv.fr/search?q={siren}"
    BELGIAN_BASE_URL = "https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html"
    DANISH_BASE_URL = "https://datacvr.virk.dk/enhed/virksomhed/{company_id}"
    
    # Processing settings
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_TIMEOUT = 30
    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_CONCURRENT_REQUESTS = 3
    MAX_CONSECUTIVE_FAILURES = 5
    
    # File upload settings
    MAX_FILE_SIZE_MB = 100
    SUPPORTED_FILE_TYPES = ['xlsx', 'xlsb', 'csv']
    
    # Country mappings
    SUPPORTED_COUNTRIES = {
        'FR': 'France',
        'BE': 'Belgium',
        'DK': 'Denmark'
    }
    
    # Column mappings for database
    DB_COLUMNS = [
        'Vendor Country',
        'Company SIREN',
        'Company Name',
        'Local Activity Code',
        'Local Activity Code Description',
        'L1 Classification',
        'L2 Classification',
        'L3 Classification'
    ]
    
    # Required columns in input files
    REQUIRED_INPUT_COLUMNS = ['country', 'siren']
    
    # Web scraping settings
    PLAYWRIGHT_SETTINGS = {
        'headless': True,
        'timeout': 30000,
        'wait_until': 'networkidle'
    }
    
    # Logging settings
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    @classmethod
    def get_api_url(cls, country: str, company_id: str = None) -> str:
        """Get the appropriate API URL for a country"""
        country = country.upper()
        
        if country == 'FR':
            return cls.FRENCH_API_URL.format(siren=company_id)
        elif country == 'BE':
            return f"{cls.BELGIAN_BASE_URL}?nummer={company_id}&actionLu=Search"
        elif country == 'DK':
            return cls.DANISH_BASE_URL.format(company_id=company_id)
        else:
            raise ValueError(f"Unsupported country: {country}")
    
    @classmethod
    def is_supported_country(cls, country: str) -> bool:
        """Check if a country is supported"""
        return country.upper() in cls.SUPPORTED_COUNTRIES
    
    @classmethod
    def ensure_directories(cls):
        """Ensure required directories exist"""
        os.makedirs(cls.BACKUP_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)
    
    @classmethod
    def get_processing_config(cls) -> Dict[str, Any]:
        """Get default processing configuration"""
        return {
            'batch_size': cls.DEFAULT_BATCH_SIZE,
            'timeout': cls.DEFAULT_TIMEOUT,
            'retry_attempts': cls.DEFAULT_RETRY_ATTEMPTS,
            'concurrent_requests': cls.DEFAULT_CONCURRENT_REQUESTS,
            'max_consecutive_failures': cls.MAX_CONSECUTIVE_FAILURES
        }
