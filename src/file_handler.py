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

    def get_sheet_info_lightweight(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile], 
                                  sheet_name: str) -> dict:
        """
        Get lightweight information about a sheet (rows, columns, sample data) without loading full DataFrame
        
        Args:
            file_input: File path string or Streamlit uploaded file
            sheet_name: Name of the sheet to analyze
            
        Returns:
            Dictionary with sheet info (rows, columns, column_names, sample_data)
        """
        try:
            # Read only first 10 rows for preview
            if isinstance(file_input, str):
                sample_df = pd.read_excel(file_input, sheet_name=sheet_name, nrows=10)
                # Get total row count by reading only the first column
                full_df_col = pd.read_excel(file_input, sheet_name=sheet_name, usecols=[0])
                total_rows = len(full_df_col)
            else:
                sample_df = pd.read_excel(file_input, sheet_name=sheet_name, nrows=10)
                # Reset and read first column only for count
                file_input.seek(0)
                full_df_col = pd.read_excel(file_input, sheet_name=sheet_name, usecols=[0])
                total_rows = len(full_df_col)
                file_input.seek(0)  # Reset for subsequent operations
            
            return {
                'rows': total_rows,
                'columns': len(sample_df.columns),
                'column_names': list(sample_df.columns),
                'sample_data': sample_df
            }
        except Exception as e:
            self.logger.error(f"Error getting sheet info for '{sheet_name}': {str(e)}")
            return {
                'rows': 0,
                'columns': 0,
                'column_names': [],
                'sample_data': pd.DataFrame(),
                'error': str(e)
            }

    def get_column_sample_values(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile], 
                                sheet_name: str, column_name: str, sample_size: int = 10) -> list:
        """
        Get sample values from a specific column without loading the full DataFrame
        
        Args:
            file_input: File path string or Streamlit uploaded file
            sheet_name: Name of the sheet (None for CSV files)
            column_name: Name of the column to sample
            sample_size: Number of sample values to return
            
        Returns:
            List of sample values
        """
        try:
            if isinstance(file_input, str):
                if sheet_name:
                    # Excel file
                    df = pd.read_excel(file_input, sheet_name=sheet_name, usecols=[column_name], nrows=1000)
                else:
                    # CSV file
                    df = pd.read_csv(file_input, usecols=[column_name], nrows=1000)
            else:
                if sheet_name:
                    # Excel file
                    df = pd.read_excel(file_input, sheet_name=sheet_name, usecols=[column_name], nrows=1000)
                    file_input.seek(0)
                else:
                    # CSV file
                    df = pd.read_csv(file_input, usecols=[column_name], nrows=1000)
                    file_input.seek(0)
            
            # Get unique values and return sample
            unique_values = df[column_name].dropna().unique()
            return list(unique_values[:sample_size])
            
        except Exception as e:
            self.logger.error(f"Error getting column samples for '{column_name}': {str(e)}")
            return []

    def validate_columns_lightweight(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile], 
                                   sheet_name: str, country_column: str, siren_column: str) -> dict:
        """
        Validate column mapping by analyzing a sample of data without loading full DataFrame
        
        Args:
            file_input: File path string or Streamlit uploaded file
            sheet_name: Name of the sheet (None for CSV files)
            country_column: Name of the country column
            siren_column: Name of the SIREN column
            
        Returns:
            Dictionary with validation results
        """
        try:
            columns_to_read = [country_column, siren_column]
            
            if isinstance(file_input, str):
                if sheet_name:
                    df = pd.read_excel(file_input, sheet_name=sheet_name, usecols=columns_to_read, nrows=1000)
                else:
                    df = pd.read_csv(file_input, usecols=columns_to_read, nrows=1000)
            else:
                if sheet_name:
                    df = pd.read_excel(file_input, sheet_name=sheet_name, usecols=columns_to_read, nrows=1000)
                    file_input.seek(0)
                else:
                    df = pd.read_csv(file_input, usecols=columns_to_read, nrows=1000)
                    file_input.seek(0)
            
            # Analyze country column
            countries_in_data = df[country_column].dropna().unique()
            supported_countries = []
            unsupported_countries = []
            
            for country in countries_in_data:
                if str(country).upper() in ['BE', 'DK', 'FR']:
                    supported_countries.append(str(country).upper())
                else:
                    unsupported_countries.append(str(country))
            
            # Analyze SIREN column
            siren_sample = df[siren_column].dropna().unique()[:10]
            
            return {
                'supported_countries': supported_countries,
                'unsupported_countries': unsupported_countries,
                'siren_samples': list(siren_sample),
                'total_sample_rows': len(df)
            }
            
        except Exception as e:
            self.logger.error(f"Error validating columns: {str(e)}")
            return {
                'supported_countries': [],
                'unsupported_countries': [],
                'siren_samples': [],
                'total_sample_rows': 0,
                'error': str(e)
            }

    def load_filtered_dataframe_optimized(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile], 
                                         sheet_name: Optional[str], country_column: str, siren_column: str) -> pd.DataFrame:
        """
        Load only the required columns and apply filtering immediately for maximum performance
        
        Args:
            file_input: File path string or Streamlit uploaded file
            sheet_name: Name of the sheet to read (None for CSV files)
            country_column: Name of the country column
            siren_column: Name of the SIREN column
            
        Returns:
            Filtered pandas DataFrame with only relevant records
        """
        try:
            from .config import Config
            
            self.logger.info(f"Loading optimized filtered DataFrame (sheet: {sheet_name})")
            
            # Load only the required columns to save memory
            required_columns = [country_column, siren_column]
            
            # Load data with only required columns
            if sheet_name:
                # Excel file with specific sheet
                if isinstance(file_input, str):
                    df = pd.read_excel(file_input, sheet_name=sheet_name, usecols=required_columns)
                else:
                    df = pd.read_excel(file_input, sheet_name=sheet_name, usecols=required_columns)
                    file_input.seek(0)
            else:
                # CSV file
                if isinstance(file_input, str):
                    df = pd.read_csv(file_input, usecols=required_columns)
                else:
                    file_input.seek(0)
                    df = pd.read_csv(file_input, usecols=required_columns)
                    file_input.seek(0)
            
            # Standardize column names for processing
            df_filtered = pd.DataFrame({
                'Vendor Country': df[country_column],
                'Company SIREN': df[siren_column]
            })
            
            # Apply same filtering logic as _prepare_data() but early
            initial_count = len(df_filtered)
            self.logger.info(f"Initial records loaded: {initial_count}")
            
            # Clean and validate data
            df_filtered = df_filtered.dropna(subset=['Vendor Country', 'Company SIREN'])
            df_filtered['Company SIREN'] = df_filtered['Company SIREN'].astype(str).str.strip()
            df_filtered['Vendor Country'] = df_filtered['Vendor Country'].astype(str).str.strip().str.upper()
            
            # Filter to supported countries IMMEDIATELY
            supported_mask = df_filtered['Vendor Country'].apply(Config.is_supported_country)
            unsupported_count = (~supported_mask).sum()
            
            if unsupported_count > 0:
                unsupported_countries = df_filtered[~supported_mask]['Vendor Country'].unique()
                self.logger.info(f"Filtering out {unsupported_count} records from unsupported countries: {list(unsupported_countries)}")
            
            df_filtered = df_filtered[supported_mask]
            
            # Remove duplicates by SIREN
            df_filtered = df_filtered.drop_duplicates(subset=['Company SIREN'])
            final_count = len(df_filtered)
            
            if initial_count != final_count:
                self.logger.info(f"Filtered data: {initial_count} → {final_count} records "
                               f"(removed {initial_count - final_count} records)")
            
            self.logger.info(f"Successfully loaded and filtered {final_count} records for processing")
            return df_filtered
                
        except Exception as e:
            self.logger.error(f"Error loading filtered DataFrame: {str(e)}")
            raise

    def load_full_dataframe_on_demand(self, file_input: Union[str, st.runtime.uploaded_file_manager.UploadedFile], 
                                     sheet_name: Optional[str] = None) -> pd.DataFrame:
        """
        Load the complete DataFrame when actually needed for processing
        
        Args:
            file_input: File path string or Streamlit uploaded file
            sheet_name: Name of the sheet to read (None for CSV files)
            
        Returns:
            Complete pandas DataFrame
        """
        try:
            self.logger.info(f"Loading full DataFrame for processing (sheet: {sheet_name})")
            
            if sheet_name:
                # Excel file with specific sheet
                return self.read_excel_sheet(file_input, sheet_name)
            else:
                # CSV file or Excel file without sheet specification
                return self.read_file(file_input)
                
        except Exception as e:
            self.logger.error(f"Error loading full DataFrame: {str(e)}")
            raise

    def create_sample_template(self) -> pd.DataFrame:
        """Create a sample template DataFrame for user reference"""
        sample_data = {
            'Vendor Country': ['FR', 'BE', 'DK', 'FR', 'BE'],
            'Company SIREN': ['123456789', '987654321', '456789123', '789123456', '321654987'],
            'Additional Column 1': ['Value 1', 'Value 2', 'Value 3', 'Value 4', 'Value 5'],
            'Additional Column 2': ['Data A', 'Data B', 'Data C', 'Data D', 'Data E']
        }
        return pd.DataFrame(sample_data)

    def estimate_filtered_record_count(self, file_input, sheet_name: Optional[str], 
                                      country_column: str, siren_column: str, 
                                      sample_size: int = 10000) -> dict:
        """
        Efficiently estimate the number of records that will actually be processed
        after applying country filtering and SIREN deduplication
        
        Args:
            file_input: Uploaded file object
            sheet_name: Excel sheet name (None for CSV)
            country_column: Name of the country column
            siren_column: Name of the SIREN column
            sample_size: Size of sample to analyze for estimation
            
        Returns:
            Dictionary with estimation details
        """
        try:
            from .config import Config
            
            # Get total record count first
            if sheet_name:
                sheet_info = self.get_sheet_info_lightweight(file_input, sheet_name)
                total_records = sheet_info['rows']
            else:
                file_input.seek(0)
                total_records = sum(1 for line in file_input) - 1  # Subtract header
                file_input.seek(0)
            
            # If file is small, analyze the whole thing
            analyze_size = min(sample_size, total_records)
            
            # Load sample for analysis
            if sheet_name:
                # Excel file - read first N rows
                df_sample = pd.read_excel(file_input, sheet_name=sheet_name, nrows=analyze_size)
            else:
                # CSV file - read first N rows
                file_input.seek(0)
                df_sample = pd.read_csv(file_input, nrows=analyze_size)
                file_input.seek(0)
            
            # Apply same filtering logic as _prepare_data()
            if country_column not in df_sample.columns or siren_column not in df_sample.columns:
                raise ValueError(f"Required columns not found: {country_column}, {siren_column}")
            
            # Create working copy with just the needed columns
            sample_filtered = pd.DataFrame({
                'Vendor Country': df_sample[country_column],
                'Company SIREN': df_sample[siren_column]
            })
            
            # Clean and validate data (same as _prepare_data)
            sample_filtered = sample_filtered.dropna(subset=['Vendor Country', 'Company SIREN'])
            sample_filtered['Company SIREN'] = sample_filtered['Company SIREN'].astype(str).str.strip()
            sample_filtered['Vendor Country'] = sample_filtered['Vendor Country'].astype(str).str.strip().str.upper()
            
            # Filter to supported countries only
            supported_mask = sample_filtered['Vendor Country'].apply(Config.is_supported_country)
            sample_filtered = sample_filtered[supported_mask]
            
            # Remove duplicates (same as _prepare_data)
            sample_filtered = sample_filtered.drop_duplicates(subset=['Company SIREN'])
            
            # Calculate ratios for estimation
            original_sample_size = len(df_sample)
            filtered_sample_size = len(sample_filtered)
            
            if original_sample_size == 0:
                filter_ratio = 0
            else:
                filter_ratio = filtered_sample_size / original_sample_size
            
            # Estimate final count
            estimated_filtered_count = int(total_records * filter_ratio)
            
            # Calculate country breakdown from sample
            country_breakdown = sample_filtered['Vendor Country'].value_counts().to_dict()
            country_percentages = {}
            if len(sample_filtered) > 0:
                for country, count in country_breakdown.items():
                    country_percentages[country] = (count / len(sample_filtered)) * 100
            
            result = {
                'total_records': total_records,
                'estimated_filtered_count': estimated_filtered_count,
                'filter_ratio': filter_ratio,
                'sample_size': analyze_size,
                'sample_filtered_size': filtered_sample_size,
                'country_breakdown': country_breakdown,
                'country_percentages': country_percentages,
                'supported_countries_only': True
            }
            
            self.logger.info(f"Estimated filtering: {total_records} → {estimated_filtered_count} records "
                           f"(ratio: {filter_ratio:.3f}, sample: {analyze_size})")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error estimating filtered record count: {str(e)}")
            # Return conservative estimate
            return {
                'total_records': total_records if 'total_records' in locals() else 0,
                'estimated_filtered_count': total_records if 'total_records' in locals() else 0,
                'filter_ratio': 1.0,
                'sample_size': 0,
                'sample_filtered_size': 0,
                'country_breakdown': {},
                'country_percentages': {},
                'supported_countries_only': False,
                'error': str(e)
            }
