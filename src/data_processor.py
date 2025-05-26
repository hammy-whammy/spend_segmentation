"""
Data processing engine for the JICAP Vendor Classification System
"""

import pandas as pd
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Callable, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

from .config import Config
from .logger_config import get_logger, ProcessingLogger
from .database_manager import DatabaseManager
from .country_scrapers import CountryScraperFactory

class DataProcessor:
    """Main data processing engine"""
    
    def __init__(self, db_manager: DatabaseManager, logger, config: Dict[str, Any]):
        self.db_manager = db_manager
        self.base_logger = logger
        self.processing_logger = ProcessingLogger(logger)
        self.config = config
        self.logger = get_logger('data_processor')
        
        # Processing statistics
        self.stats = {
            'total_records': 0,
            'processed': 0,
            'new_records': 0,
            'existing_records': 0,
            'errors': 0,
            'success_rate': 0.0,
            'country_breakdown': {},
            'start_time': None,
            'end_time': None
        }
    
    def process_vendor_list(self, df: pd.DataFrame, column_mapping: Dict[str, str], 
                           progress_callback: Optional[Callable] = None, 
                           is_pre_filtered: bool = False) -> Dict[str, Any]:
        """
        Process the vendor list and update the database
        
        Args:
            df: Input DataFrame with vendor data
            column_mapping: Mapping of column names to expected fields
            progress_callback: Optional callback for progress updates
            is_pre_filtered: If True, skips country filtering and deduplication as data is already filtered
            
        Returns:
            Dictionary with processing results
        """
        try:
            self.stats['start_time'] = datetime.now()
            self.processing_logger.info("Starting vendor list processing")
            
            # Prepare data (conditionally filter based on is_pre_filtered flag)
            processed_df = self._prepare_data(df, column_mapping, is_pre_filtered)
            self.stats['total_records'] = len(processed_df)
            
            if len(processed_df) == 0:
                self.processing_logger.warning("No valid records to process")
                return self._create_results()
            
            # Check existing records
            existing_sirens, new_sirens = self.db_manager.check_existing_records(
                processed_df['Company SIREN'].tolist()
            )
            
            self.stats['existing_records'] = len(existing_sirens)
            self.processing_logger.info(f"Found {len(existing_sirens)} existing records, {len(new_sirens)} new records")
            
            # Process only new records
            new_records_df = processed_df[processed_df['Company SIREN'].isin(new_sirens)]
            
            if len(new_records_df) == 0:
                self.processing_logger.info("No new records to process")
                return self._create_results()
            
            # Group by country for efficient processing
            country_groups = new_records_df.groupby('Vendor Country')
            
            # Process each country group
            all_fetched_data = []
            
            for country, group in country_groups:
                if not Config.is_supported_country(country):
                    self.processing_logger.warning(f"Skipping unsupported country: {country}")
                    continue
                
                self.processing_logger.info(f"Processing {len(group)} records for country: {country}")
                
                # Fetch data for this country
                country_data = self._process_country_group(
                    country, group, progress_callback
                )
                
                all_fetched_data.extend(country_data)
            
            # Add records to database
            if all_fetched_data:
                add_results = self.db_manager.add_records(all_fetched_data)
                self.stats['new_records'] = add_results['added']
                self.stats['errors'] += add_results['errors']
                
                # Save database
                if self.db_manager.save_database():
                    self.processing_logger.info("Database saved successfully")
                else:
                    self.processing_logger.error("Failed to save database")
            
            # Finalize results
            self.stats['end_time'] = datetime.now()
            self.stats['processed'] = len(all_fetched_data)
            self.stats['success_rate'] = (
                (self.stats['processed'] - self.stats['errors']) / max(self.stats['processed'], 1) * 100
            )
            
            self.processing_logger.info("Processing completed successfully")
            
            return self._create_results()
            
        except Exception as e:
            self.processing_logger.error(f"Processing failed: {str(e)}")
            self.processing_logger.error(traceback.format_exc())
            raise
    
    def _prepare_data(self, df: pd.DataFrame, column_mapping: Dict[str, str], is_pre_filtered: bool = False) -> pd.DataFrame:
        """Prepare and validate input data"""
        try:
            # If data is already pre-filtered, skip expensive operations
            if is_pre_filtered:
                self.processing_logger.info(f"Using pre-filtered data with {len(df)} records (skipping filtering)")
                # Data is already in the correct format from load_filtered_dataframe_optimized
                return df
                
            # Create working copy
            processed_df = df.copy()
            
            # Map columns to standard names
            country_col = column_mapping['country']
            siren_col = column_mapping['siren']
            
            # Create standardized dataframe
            standardized_df = pd.DataFrame({
                'Vendor Country': processed_df[country_col],
                'Company SIREN': processed_df[siren_col]
            })
            
            # Clean and validate data
            standardized_df = standardized_df.dropna(subset=['Vendor Country', 'Company SIREN'])
            standardized_df['Company SIREN'] = standardized_df['Company SIREN'].astype(str).str.strip()
            standardized_df['Vendor Country'] = standardized_df['Vendor Country'].astype(str).str.strip().str.upper()
            
            # Remove duplicates
            initial_count = len(standardized_df)
            standardized_df = standardized_df.drop_duplicates(subset=['Company SIREN'])
            final_count = len(standardized_df)
            
            if initial_count != final_count:
                self.processing_logger.info(f"Removed {initial_count - final_count} duplicate SIREN records")
            
            # Filter supported countries
            supported_mask = standardized_df['Vendor Country'].apply(Config.is_supported_country)
            unsupported_count = (~supported_mask).sum()
            
            if unsupported_count > 0:
                unsupported_countries = standardized_df[~supported_mask]['Vendor Country'].unique()
                self.processing_logger.warning(
                    f"Filtering out {unsupported_count} records from unsupported countries: {list(unsupported_countries)}"
                )
            
            standardized_df = standardized_df[supported_mask]
            
            self.processing_logger.info(f"Prepared {len(standardized_df)} valid records for processing")
            return standardized_df
            
        except Exception as e:
            self.processing_logger.error(f"Error preparing data: {str(e)}")
            raise
    
    def _process_country_group(self, country: str, group_df: pd.DataFrame, 
                              progress_callback: Optional[Callable] = None) -> List[Dict]:
        """Process a group of records for a specific country"""
        try:
            # Create scraper for this country
            scraper = CountryScraperFactory.create_scraper(country)
            
            # Convert to list of company IDs
            company_ids = group_df['Company SIREN'].tolist()
            
            # Initialize country stats
            if country not in self.stats['country_breakdown']:
                self.stats['country_breakdown'][country] = {
                    'total': 0,
                    'processed': 0,
                    'errors': 0,
                    'success_rate': 0.0
                }
            
            self.stats['country_breakdown'][country]['total'] = len(company_ids)
            
            # Process records using asyncio for better performance
            fetched_data = asyncio.run(self._fetch_country_data_async(
                scraper, country, company_ids, progress_callback
            ))
            
            # Update country stats
            self.stats['country_breakdown'][country]['processed'] = len(fetched_data)
            error_count = sum(1 for data in fetched_data if data.get('Company Name') == 'N/A')
            self.stats['country_breakdown'][country]['errors'] = error_count
            self.stats['country_breakdown'][country]['success_rate'] = (
                (len(fetched_data) - error_count) / max(len(fetched_data), 1) * 100
            )
            
            return fetched_data
            
        except Exception as e:
            self.processing_logger.error(f"Error processing country group {country}: {str(e)}")
            return []
    
    async def _fetch_country_data_async(self, scraper, country: str, company_ids: List[str],
                                       progress_callback: Optional[Callable] = None) -> List[Dict]:
        """Fetch data for a country using async processing"""
        fetched_data = []
        batch_size = self.config.get('batch_size', Config.DEFAULT_BATCH_SIZE)
        concurrent_requests = self.config.get('concurrent_requests', Config.DEFAULT_CONCURRENT_REQUESTS)
        
        # Process in batches
        for i in range(0, len(company_ids), batch_size):
            batch = company_ids[i:i + batch_size]
            self.processing_logger.info(f"Processing batch {i//batch_size + 1} for {country}: {len(batch)} companies")
            
            # Create semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(concurrent_requests)
            
            async def fetch_with_semaphore(company_id):
                async with semaphore:
                    try:
                        result = await scraper.fetch_company_data(company_id)
                        result['Vendor Country'] = country
                        result['Company SIREN'] = company_id
                        return result
                    except Exception as e:
                        self.processing_logger.error(f"Error fetching data for {company_id}: {str(e)}")
                        return {
                            'Vendor Country': country,
                            'Company SIREN': company_id,
                            'Company Name': 'N/A',
                            'Local Activity Code': 'N/A',
                            'Local Activity Code Description': 'N/A'
                        }
            
            # Execute batch with concurrency control
            tasks = [fetch_with_semaphore(company_id) for company_id in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    self.processing_logger.error(f"Exception for company {batch[j]}: {str(result)}")
                    result = {
                        'Vendor Country': country,
                        'Company SIREN': batch[j],
                        'Company Name': 'N/A',
                        'Local Activity Code': 'N/A',
                        'Local Activity Code Description': 'N/A'
                    }
                
                fetched_data.append(result)
                
                # Update progress
                if progress_callback:
                    current_progress = (len(fetched_data) / len(company_ids)) * 100
                    progress_callback(
                        current_progress / 100,
                        f"Processing {country}: {len(fetched_data)}/{len(company_ids)}",
                        {
                            'processed': len(fetched_data),
                            'new_records': self.stats['new_records'],
                            'errors': self.stats['errors'],
                            'success_rate': (
                                (len(fetched_data) - sum(1 for d in fetched_data if d.get('Company Name') == 'N/A')) / 
                                max(len(fetched_data), 1) * 100
                            ),
                            'recent_logs': self.processing_logger.get_recent_logs()
                        }
                    )
            
            # Add delay between batches to be respectful to servers
            if i + batch_size < len(company_ids):
                await asyncio.sleep(1)
        
        return fetched_data
    
    def _create_results(self) -> Dict[str, Any]:
        """Create final results dictionary"""
        # Save processing log
        log_file_path = None
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file_path = f"logs/processing_log_{timestamp}.txt"
            self.processing_logger.save_log_file(log_file_path)
        except Exception as e:
            self.processing_logger.error(f"Failed to save log file: {str(e)}")
        
        # Calculate processing time
        processing_time = None
        if self.stats['start_time'] and self.stats['end_time']:
            processing_time = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        results = {
            'total_processed': self.stats['processed'],
            'new_records': self.stats['new_records'],
            'existing_records': self.stats['existing_records'],
            'errors': self.stats['errors'],
            'success_rate': self.stats['success_rate'],
            'country_breakdown': self.stats['country_breakdown'],
            'processing_time_seconds': processing_time,
            'log_file_path': log_file_path,
            'log_stats': self.processing_logger.get_stats()
        }
        
        return results
