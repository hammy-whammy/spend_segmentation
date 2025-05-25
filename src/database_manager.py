"""
Database management for the JICAP Vendor Classification System
"""

import pandas as pd
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from .config import Config
from .logger_config import get_logger
from .file_handler import FileHandler

class DatabaseManager:
    """Manage the JICAP Company Database operations"""
    
    def __init__(self, db_file_path: str = None):
        self.logger = get_logger('database_manager')
        self.db_file_path = db_file_path or Config.DATABASE_FILE
        self.file_handler = FileHandler()
        
        # Ensure directories exist
        Config.ensure_directories()
        
        # Load database
        self.db_df = self._load_database()
        
    def _load_database(self) -> pd.DataFrame:
        """Load the JICAP database from file"""
        try:
            if os.path.exists(self.db_file_path):
                self.logger.info(f"Loading database from {self.db_file_path}")
                df = self.file_handler.read_file(self.db_file_path)
                
                # Validate database structure
                self._validate_database_structure(df)
                
                # Ensure all required columns exist
                for col in Config.DB_COLUMNS:
                    if col not in df.columns:
                        df[col] = None
                
                # Reorder columns to match expected structure
                df = df[Config.DB_COLUMNS]
                
                self.logger.info(f"Database loaded successfully. Records: {len(df)}")
                return df
            else:
                self.logger.warning(f"Database file not found: {self.db_file_path}")
                self.logger.info("Creating new empty database")
                return self._create_empty_database()
                
        except Exception as e:
            self.logger.error(f"Error loading database: {str(e)}")
            self.logger.info("Creating new empty database as fallback")
            return self._create_empty_database()
    
    def _create_empty_database(self) -> pd.DataFrame:
        """Create an empty database with the correct structure"""
        return pd.DataFrame(columns=Config.DB_COLUMNS)
    
    def _validate_database_structure(self, df: pd.DataFrame):
        """Validate that the database has the expected structure"""
        missing_columns = [col for col in Config.DB_COLUMNS if col not in df.columns]
        if missing_columns:
            self.logger.warning(f"Database missing columns: {missing_columns}")
            # Don't raise error, we'll add them later
    
    def create_backup(self) -> str:
        """Create a backup of the current database"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"JICAP_Database_Backup_{timestamp}.xlsx"
            backup_path = os.path.join(Config.BACKUP_DIR, backup_filename)
            
            if os.path.exists(self.db_file_path):
                shutil.copy2(self.db_file_path, backup_path)
                self.logger.info(f"Database backup created: {backup_path}")
                return backup_path
            else:
                self.logger.warning("No database file to backup")
                return None
                
        except Exception as e:
            self.logger.error(f"Error creating backup: {str(e)}")
            return None
    
    def get_record_count(self) -> int:
        """Get the total number of records in the database"""
        return len(self.db_df)
    
    def get_unique_sirens(self) -> set:
        """Get set of unique SIREN numbers in the database"""
        return set(self.db_df['Company SIREN'].dropna().astype(str))
    
    def check_existing_records(self, siren_list: List[str]) -> Tuple[List[str], List[str]]:
        """
        Check which SIREN numbers already exist in the database
        
        Args:
            siren_list: List of SIREN numbers to check
            
        Returns:
            Tuple of (existing_sirens, new_sirens)
        """
        existing_sirens_set = self.get_unique_sirens()
        siren_set = set(str(siren) for siren in siren_list)
        
        existing = list(siren_set.intersection(existing_sirens_set))
        new = list(siren_set - existing_sirens_set)
        
        self.logger.info(f"SIREN check complete. Existing: {len(existing)}, New: {len(new)}")
        return existing, new
    
    def add_records(self, new_records: List[Dict]) -> Dict[str, int]:
        """
        Add new records to the database
        
        Args:
            new_records: List of dictionaries containing record data
            
        Returns:
            Dictionary with counts of added/updated records
        """
        results = {
            'added': 0,
            'updated': 0,
            'errors': 0
        }
        
        try:
            for record in new_records:
                try:
                    # Check if record already exists
                    siren = str(record.get('Company SIREN', ''))
                    existing_mask = self.db_df['Company SIREN'].astype(str) == siren
                    
                    if existing_mask.any():
                        # Update existing record (preserve L1, L2, L3 classifications)
                        existing_idx = self.db_df[existing_mask].index[0]
                        
                        # Only update fields that are not classification fields
                        update_fields = [
                            'Vendor Country',
                            'Company Name',
                            'Local Activity Code',
                            'Local Activity Code Description'
                        ]
                        
                        for field in update_fields:
                            if field in record and record[field] is not None:
                                self.db_df.loc[existing_idx, field] = record[field]
                        
                        results['updated'] += 1
                        self.logger.debug(f"Updated existing record for SIREN: {siren}")
                        
                    else:
                        # Add new record
                        new_row = {col: record.get(col) for col in Config.DB_COLUMNS}
                        self.db_df = pd.concat([self.db_df, pd.DataFrame([new_row])], ignore_index=True)
                        results['added'] += 1
                        self.logger.debug(f"Added new record for SIREN: {siren}")
                        
                except Exception as e:
                    self.logger.error(f"Error processing record {record}: {str(e)}")
                    results['errors'] += 1
            
            self.logger.info(f"Record addition complete. Added: {results['added']}, Updated: {results['updated']}, Errors: {results['errors']}")
            
        except Exception as e:
            self.logger.error(f"Error adding records to database: {str(e)}")
            results['errors'] += len(new_records)
        
        return results
    
    def save_database(self) -> bool:
        """Save the current database to file"""
        try:
            # Create backup before saving
            self.create_backup()
            
            # Save updated database
            self.db_df.to_excel(self.db_file_path, index=False)
            self.logger.info(f"Database saved successfully to {self.db_file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving database: {str(e)}")
            return False
    
    def export_database(self, file_format: str = 'xlsx') -> bytes:
        """
        Export database for download
        
        Args:
            file_format: Export format ('xlsx' or 'csv')
            
        Returns:
            Bytes content of the exported file
        """
        try:
            return self.file_handler.export_dataframe(self.db_df, file_format)
        except Exception as e:
            self.logger.error(f"Error exporting database: {str(e)}")
            raise
    
    def get_database_stats(self) -> Dict[str, any]:
        """Get statistics about the current database"""
        try:
            stats = {
                'total_records': len(self.db_df),
                'unique_sirens': len(self.get_unique_sirens()),
                'countries': {}
            }
            
            # Count by country
            if 'Vendor Country' in self.db_df.columns:
                country_counts = self.db_df['Vendor Country'].value_counts()
                stats['countries'] = country_counts.to_dict()
            
            # Classification completeness
            classification_columns = ['L1 Classification', 'L2 Classification', 'L3 Classification']
            for col in classification_columns:
                if col in self.db_df.columns:
                    filled_count = self.db_df[col].notna().sum()
                    stats[f'{col.lower().replace(" ", "_")}_filled'] = int(filled_count)
                    stats[f'{col.lower().replace(" ", "_")}_percentage'] = round(
                        (filled_count / len(self.db_df)) * 100, 2
                    ) if len(self.db_df) > 0 else 0
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting database stats: {str(e)}")
            return {'error': str(e)}
    
    def search_records(self, country: str = None, siren: str = None, 
                      company_name: str = None) -> pd.DataFrame:
        """
        Search for records in the database
        
        Args:
            country: Filter by country
            siren: Filter by SIREN number
            company_name: Filter by company name (partial match)
            
        Returns:
            Filtered DataFrame
        """
        try:
            df = self.db_df.copy()
            
            if country:
                df = df[df['Vendor Country'].str.upper() == country.upper()]
            
            if siren:
                df = df[df['Company SIREN'].astype(str) == str(siren)]
            
            if company_name:
                df = df[df['Company Name'].str.contains(company_name, case=False, na=False)]
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error searching records: {str(e)}")
            return pd.DataFrame()
    
    def validate_data_integrity(self) -> Dict[str, any]:
        """Validate the integrity of the database"""
        issues = {
            'duplicate_sirens': [],
            'missing_required_fields': [],
            'invalid_countries': [],
            'data_type_issues': []
        }
        
        try:
            # Check for duplicate SIRENs
            siren_counts = self.db_df['Company SIREN'].value_counts()
            duplicates = siren_counts[siren_counts > 1].index.tolist()
            if duplicates:
                issues['duplicate_sirens'] = duplicates
            
            # Check for missing required fields
            required_fields = ['Vendor Country', 'Company SIREN']
            for field in required_fields:
                missing_count = self.db_df[field].isna().sum()
                if missing_count > 0:
                    issues['missing_required_fields'].append({
                        'field': field,
                        'missing_count': int(missing_count)
                    })
            
            # Check for invalid countries
            if 'Vendor Country' in self.db_df.columns:
                valid_countries = set(Config.SUPPORTED_COUNTRIES.keys())
                unique_countries = set(self.db_df['Vendor Country'].dropna().unique())
                invalid = unique_countries - valid_countries
                if invalid:
                    issues['invalid_countries'] = list(invalid)
            
            return issues
            
        except Exception as e:
            self.logger.error(f"Error validating data integrity: {str(e)}")
            return {'error': str(e)}
