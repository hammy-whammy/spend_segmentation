"""
File handling utilities for the JICAP Vendor Classification System
"""

import pandas as pd
import io
from typing import Union, Optional
import streamlit as st
from pathlib import Path

from .config import Config
from .logger_config import get_logger

class FileHandler:
    """Handle file upload, validation, and processing"""
    
    def __init__(self):
        self.logger = get_logger('file_handler')
        
    def read_file(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile]) -> pd.DataFrame:
        """
        Read file from various sources and return as DataFrame
        
        Args:
            file_input: File path string or Streamlit uploaded file
            
        Returns:
            pandas DataFrame
            
        Raises:
            ValueError: If file format is not supported
            Exception: If file reading fails
        """
        try:
            if isinstance(file_input, str):
                # File path string
                file_path = Path(file_input)
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_input}")
                
                return self._read_file_by_extension(file_path)
                
            else:
                # Streamlit uploaded file
                return self._read_uploaded_file(file_input)
                
        except Exception as e:
            self.logger.error(f"Error reading file: {str(e)}")
            raise
    
    def _read_file_by_extension(self, file_path: Path) -> pd.DataFrame:
        """Read file based on its extension"""
        extension = file_path.suffix.lower()
        
        if extension == '.csv':
            # Try different encodings for CSV
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    return pd.read_csv(file_path, encoding=encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError("Could not decode CSV file with any supported encoding")
            
        elif extension in ['.xlsx', '.xlsb']:
            return pd.read_excel(file_path)
            
        else:
            raise ValueError(f"Unsupported file format: {extension}")
    
    def _read_uploaded_file(self, uploaded_file) -> pd.DataFrame:
        """Read Streamlit uploaded file"""
        file_extension = Path(uploaded_file.name).suffix.lower()
        
        if file_extension == '.csv':
            # For CSV, try different encodings
            content = uploaded_file.getvalue()
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    return pd.read_csv(io.StringIO(content.decode(encoding)))
                except UnicodeDecodeError:
                    continue
            raise ValueError("Could not decode CSV file with any supported encoding")
            
        elif file_extension in ['.xlsx', '.xlsb']:
            return pd.read_excel(uploaded_file)
            
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
    
    def validate_file(self, uploaded_file) -> dict:
        """
        Validate uploaded file
        
        Args:
            uploaded_file: Streamlit uploaded file object
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'file_info': {}
        }
        
        try:
            # Check file size
            file_size_mb = uploaded_file.size / (1024 * 1024)
            validation_result['file_info']['size_mb'] = round(file_size_mb, 2)
            
            if file_size_mb > Config.MAX_FILE_SIZE_MB:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"File size ({file_size_mb:.2f} MB) exceeds maximum allowed size ({Config.MAX_FILE_SIZE_MB} MB)"
                )
            
            # Check file extension
            file_extension = Path(uploaded_file.name).suffix.lower().replace('.', '')
            validation_result['file_info']['extension'] = file_extension
            
            if file_extension not in Config.SUPPORTED_FILE_TYPES:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"File type '{file_extension}' is not supported. Supported types: {', '.join(Config.SUPPORTED_FILE_TYPES)}"
                )
            
            # Try to read file structure
            if validation_result['is_valid']:
                try:
                    df = self.read_file(uploaded_file)
                    validation_result['file_info']['rows'] = len(df)
                    validation_result['file_info']['columns'] = len(df.columns)
                    validation_result['file_info']['column_names'] = list(df.columns)
                    
                    # Reset file pointer for subsequent reads
                    uploaded_file.seek(0)
                    
                    # Warnings for potential issues
                    if len(df) == 0:
                        validation_result['warnings'].append("File appears to be empty")
                    
                    if len(df.columns) < 2:
                        validation_result['warnings'].append("File has fewer than 2 columns, ensure it contains country and SIREN columns")
                    
                    # Check for common column patterns
                    column_names_lower = [col.lower() for col in df.columns]
                    has_country_like = any('country' in col or 'nation' in col for col in column_names_lower)
                    has_id_like = any(term in col for col in column_names_lower for term in ['siren', 'id', 'number', 'code'])
                    
                    if not has_country_like:
                        validation_result['warnings'].append("No obvious country column found - ensure you have a column with country information")
                    
                    if not has_id_like:
                        validation_result['warnings'].append("No obvious ID/SIREN column found - ensure you have a column with company identifiers")
                        
                except Exception as e:
                    validation_result['is_valid'] = False
                    validation_result['errors'].append(f"Could not read file content: {str(e)}")
            
        except Exception as e:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"File validation failed: {str(e)}")
        
        return validation_result
    
    def export_dataframe(self, df: pd.DataFrame, file_format: str = 'xlsx') -> bytes:
        """
        Export DataFrame to bytes for download
        
        Args:
            df: DataFrame to export
            file_format: Export format ('xlsx', 'csv')
            
        Returns:
            Bytes content of the file
        """
        try:
            if file_format.lower() == 'xlsx':
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='JICAP_Database')
                return output.getvalue()
                
            elif file_format.lower() == 'csv':
                return df.to_csv(index=False).encode('utf-8')
                
            else:
                raise ValueError(f"Unsupported export format: {file_format}")
                
        except Exception as e:
            self.logger.error(f"Error exporting DataFrame: {str(e)}")
            raise
    
    def get_excel_sheet_names(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile]) -> list:
        """
        Get all sheet names from an Excel file
        
        Args:
            file_input: File path string or Streamlit uploaded file
            
        Returns:
            List of sheet names
            
        Raises:
            ValueError: If file is not an Excel file
            Exception: If file reading fails
        """
        try:
            if isinstance(file_input, str):
                # File path string
                file_path = Path(file_input)
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_input}")
                
                extension = file_path.suffix.lower()
                if extension not in ['.xlsx', '.xlsb']:
                    raise ValueError(f"File is not an Excel file: {extension}")
                
                excel_file = pd.ExcelFile(file_path)
                return excel_file.sheet_names
                
            else:
                # Streamlit uploaded file
                file_extension = Path(file_input.name).suffix.lower()
                if file_extension not in ['.xlsx', '.xlsb']:
                    raise ValueError(f"File is not an Excel file: {file_extension}")
                
                excel_file = pd.ExcelFile(file_input)
                return excel_file.sheet_names
                
        except Exception as e:
            self.logger.error(f"Error getting Excel sheet names: {str(e)}")
            raise
    
    def read_excel_sheet(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile], 
                        sheet_name: str) -> pd.DataFrame:
        """
        Read a specific sheet from an Excel file
        
        Args:
            file_input: File path string or Streamlit uploaded file
            sheet_name: Name of the sheet to read
            
        Returns:
            pandas DataFrame
            
        Raises:
            ValueError: If file is not an Excel file or sheet doesn't exist
            Exception: If file reading fails
        """
        try:
            if isinstance(file_input, str):
                # File path string
                file_path = Path(file_input)
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_input}")
                
                extension = file_path.suffix.lower()
                if extension not in ['.xlsx', '.xlsb']:
                    raise ValueError(f"File is not an Excel file: {extension}")
                
                return pd.read_excel(file_path, sheet_name=sheet_name)
                
            else:
                # Streamlit uploaded file
                file_extension = Path(file_input.name).suffix.lower()
                if file_extension not in ['.xlsx', '.xlsb']:
                    raise ValueError(f"File is not an Excel file: {file_extension}")
                
                return pd.read_excel(file_input, sheet_name=sheet_name)
                
        except Exception as e:
            self.logger.error(f"Error reading Excel sheet '{sheet_name}': {str(e)}")
            raise

    def is_excel_file(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile]) -> bool:
        """
        Check if the file is an Excel file
        
        Args:
            file_input: File path string or Streamlit uploaded file
            
        Returns:
            True if file is Excel, False otherwise
        """
        try:
            if isinstance(file_input, str):
                extension = Path(file_input).suffix.lower()
            else:
                extension = Path(file_input.name).suffix.lower()
            
            return extension in ['.xlsx', '.xlsb']
        except:
            return False

    def create_sample_template(self) -> pd.DataFrame:
        """Create a sample template DataFrame for user reference"""
        sample_data = {
            'Vendor Country': ['FR', 'BE', 'DK', 'FR', 'BE'],
            'Company SIREN': ['123456789', '987654321', '456789123', '789123456', '321654987'],
            'Additional Column 1': ['Value 1', 'Value 2', 'Value 3', 'Value 4', 'Value 5'],
            'Additional Column 2': ['Data A', 'Data B', 'Data C', 'Data D', 'Data E']
        }
        return pd.DataFrame(sample_data)
