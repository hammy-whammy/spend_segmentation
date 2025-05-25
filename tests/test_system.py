"""
Basic tests for the JICAP Vendor Classification System
"""

import pytest
import pandas as pd
import os
import sys
import tempfile
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.config import Config
from src.database_manager import DatabaseManager
from src.file_handler import FileHandler
from src.utils import DataValidator, format_duration, format_file_size

class TestConfig:
    """Test configuration settings"""
    
    def test_supported_countries(self):
        """Test supported countries configuration"""
        assert Config.is_supported_country('FR')
        assert Config.is_supported_country('BE')
        assert Config.is_supported_country('DK')
        assert not Config.is_supported_country('US')
        assert not Config.is_supported_country('XX')
    
    def test_api_urls(self):
        """Test API URL generation"""
        fr_url = Config.get_api_url('FR', '123456789')
        assert '123456789' in fr_url
        assert 'recherche-entreprises.api.gouv.fr' in fr_url
        
        be_url = Config.get_api_url('BE', '987654321')
        assert '987654321' in be_url
        assert 'kbopub.economie.fgov.be' in be_url
        
        dk_url = Config.get_api_url('DK', '456789123')
        assert '456789123' in dk_url
        assert 'datacvr.virk.dk' in dk_url

class TestDataValidator:
    """Test data validation utilities"""
    
    def setup_method(self):
        self.validator = DataValidator()
    
    def test_siren_validation(self):
        """Test SIREN number validation"""
        # Valid SIRENs
        assert self.validator.validate_siren('123456789')
        assert self.validator.validate_siren('987654321')
        assert self.validator.validate_siren('000000001')
        
        # Invalid SIRENs
        assert not self.validator.validate_siren('')
        assert not self.validator.validate_siren('12345')  # Too short
        assert not self.validator.validate_siren('1234567890123456')  # Too long
        assert not self.validator.validate_siren('12345678a')  # Contains letters
        assert not self.validator.validate_siren(None)
        assert not self.validator.validate_siren(pd.NA)
    
    def test_country_validation(self):
        """Test country code validation"""
        assert self.validator.validate_country_code('FR')
        assert self.validator.validate_country_code('BE')
        assert self.validator.validate_country_code('DK')
        assert self.validator.validate_country_code('fr')  # Case insensitive
        
        assert not self.validator.validate_country_code('US')
        assert not self.validator.validate_country_code('XX')
        assert not self.validator.validate_country_code('')
        assert not self.validator.validate_country_code(None)
    
    def test_company_name_cleaning(self):
        """Test company name cleaning"""
        assert self.validator.clean_company_name('Test Company') == 'Test Company'
        assert self.validator.clean_company_name('"Test Company"') == 'Test Company'
        assert self.validator.clean_company_name('  Test   Company  ') == 'Test Company'
        assert self.validator.clean_company_name('') == 'N/A'
        assert self.validator.clean_company_name(None) == 'N/A'
        assert self.validator.clean_company_name('N/A') == 'N/A'

class TestFileHandler:
    """Test file handling operations"""
    
    def setup_method(self):
        self.file_handler = FileHandler()
    
    def test_sample_template(self):
        """Test sample template generation"""
        template = self.file_handler.create_sample_template()
        assert isinstance(template, pd.DataFrame)
        assert 'Vendor Country' in template.columns
        assert 'Company SIREN' in template.columns
        assert len(template) > 0
    
    def test_csv_export(self):
        """Test CSV export functionality"""
        df = pd.DataFrame({
            'Column1': ['A', 'B', 'C'],
            'Column2': [1, 2, 3]
        })
        
        csv_bytes = self.file_handler.export_dataframe(df, 'csv')
        assert isinstance(csv_bytes, bytes)
        assert b'Column1' in csv_bytes
        assert b'Column2' in csv_bytes
    
    def test_excel_export(self):
        """Test Excel export functionality"""
        df = pd.DataFrame({
            'Column1': ['A', 'B', 'C'],
            'Column2': [1, 2, 3]
        })
        
        excel_bytes = self.file_handler.export_dataframe(df, 'xlsx')
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

class TestDatabaseManager:
    """Test database management operations"""
    
    def setup_method(self):
        # Create a temporary database file for testing
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        self.temp_file.close()
        
        # Create a sample database
        sample_data = {
            'Vendor Country': ['FR', 'BE', 'DK'],
            'Company SIREN': ['123456789', '987654321', '456789123'],
            'Company Name': ['Test FR', 'Test BE', 'Test DK'],
            'Local Activity Code': ['12.34', '56.78', '90.12'],
            'Local Activity Code Description': ['Desc 1', 'Desc 2', 'Desc 3'],
            'L1 Classification': [None, None, None],
            'L2 Classification': [None, None, None],
            'L3 Classification': [None, None, None]
        }
        df = pd.DataFrame(sample_data)
        df.to_excel(self.temp_file.name, index=False)
        
        self.db_manager = DatabaseManager(self.temp_file.name)
    
    def teardown_method(self):
        # Clean up temporary file
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    def test_database_loading(self):
        """Test database loading"""
        assert len(self.db_manager.db_df) == 3
        assert 'Vendor Country' in self.db_manager.db_df.columns
        assert self.db_manager.get_record_count() == 3
    
    def test_unique_sirens(self):
        """Test unique SIREN retrieval"""
        unique_sirens = self.db_manager.get_unique_sirens()
        assert '123456789' in unique_sirens
        assert '987654321' in unique_sirens
        assert '456789123' in unique_sirens
        assert len(unique_sirens) == 3
    
    def test_existing_records_check(self):
        """Test existing records check"""
        test_sirens = ['123456789', '999999999', '987654321', '888888888']
        existing, new = self.db_manager.check_existing_records(test_sirens)
        
        assert '123456789' in existing
        assert '987654321' in existing
        assert '999999999' in new
        assert '888888888' in new
    
    def test_add_records(self):
        """Test adding new records"""
        new_records = [
            {
                'Vendor Country': 'FR',
                'Company SIREN': '111111111',
                'Company Name': 'New Company',
                'Local Activity Code': '99.99',
                'Local Activity Code Description': 'New Activity'
            }
        ]
        
        results = self.db_manager.add_records(new_records)
        assert results['added'] == 1
        assert results['errors'] == 0
        assert self.db_manager.get_record_count() == 4

class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_format_duration(self):
        """Test duration formatting"""
        assert format_duration(30) == "30 seconds"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3661) == "1h 1m"
    
    def test_format_file_size(self):
        """Test file size formatting"""
        assert format_file_size(512) == "512.0 B"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(1073741824) == "1.0 GB"

# Integration test
def test_sample_workflow():
    """Test a basic workflow"""
    # Create sample input data
    input_data = pd.DataFrame({
        'Country': ['FR', 'BE', 'DK'],
        'SIREN': ['123456789', '987654321', '456789123'],
        'Extra': ['Data1', 'Data2', 'Data3']
    })
    
    # Test column mapping
    column_mapping = {'country': 'Country', 'siren': 'SIREN'}
    
    # Validate the mapping makes sense
    assert 'Country' in input_data.columns
    assert 'SIREN' in input_data.columns
    
    # Test data validation
    validator = DataValidator()
    for _, row in input_data.iterrows():
        assert validator.validate_country_code(row['Country'])
        assert validator.validate_siren(row['SIREN'])

if __name__ == "__main__":
    pytest.main([__file__])
