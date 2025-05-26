"""
JICAP Vendor Classification Automation System
Main Streamlit Application

This application automates vendor classification by processing uploaded vendor lists,
cross-referencing with the JICAP Company Database, and automatically fetching missing
company information from government APIs and web scraping sources.
"""

import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
import logging
from typing import Tuple, Optional, List, Dict
import tempfile
import traceback

# Import custom modules
from src.data_processor import DataProcessor
from src.database_manager import DatabaseManager
from src.country_scrapers import CountryScraperFactory
from src.file_handler import FileHandler
from src.logger_config import setup_logging
from src.config import Config

# Configure page
st.set_page_config(
    page_title="JICAP Vendor Classification System",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 3rem;
    }
    .metric-container {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .upload-zone {
        border: 2px dashed #1f77b4;
        border-radius: 10px;
        padding: 2rem;
        text-align: center;
        background-color: #f8f9fa;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class JICAPApp:
    def __init__(self):
        self.setup_session_state()
        self.logger = setup_logging()
        self.config = Config()
        self.file_handler = FileHandler()
        self.db_manager = DatabaseManager()
        
    def setup_session_state(self):
        """Initialize session state variables"""
        if 'processing_complete' not in st.session_state:
            st.session_state.processing_complete = False
        if 'uploaded_file' not in st.session_state:
            st.session_state.uploaded_file = None
        if 'selected_sheet' not in st.session_state:
            st.session_state.selected_sheet = None
        if 'available_sheets' not in st.session_state:
            st.session_state.available_sheets = []
        if 'column_mapping' not in st.session_state:
            st.session_state.column_mapping = {}
        if 'processing_results' not in st.session_state:
            st.session_state.processing_results = None
        if 'log_file_path' not in st.session_state:
            st.session_state.log_file_path = None
        # New session state for lightweight processing
        if 'file_data_info' not in st.session_state:
            st.session_state.file_data_info = None

    def render_header(self):
        """Render the application header"""
        st.markdown('<h1 class="main-header">🏢 JICAP Vendor Classification System</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Automate vendor classification with government APIs and web scraping</p>', unsafe_allow_html=True)
        
        # Display system status
        with st.expander("📊 System Status", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Database Records", self.db_manager.get_record_count())
            with col2:
                st.metric("Supported Countries", "3")
            with col3:
                st.metric("System Status", "✅ Online")

    def render_file_upload(self):
        """Render the file upload section"""
        st.markdown("## 📁 Step 1: Upload Vendor List")
        
        uploaded_file = st.file_uploader(
            "Choose your vendor list file",
            type=['xlsx', 'xlsb', 'csv'],
            help="Supported formats: Excel (.xlsx, .xlsb) and CSV (.csv). Maximum file size: 100MB"
        )
        
        if uploaded_file is not None:
            # Validate file size
            if uploaded_file.size > Config.MAX_FILE_SIZE_MB * 1024 * 1024:  # Use config value
                st.error(f"❌ File size exceeds {Config.MAX_FILE_SIZE_MB}MB limit. Please upload a smaller file.")
                return None
                
            # Save uploaded file to session state
            st.session_state.uploaded_file = uploaded_file
            
            # Display file info
            st.success(f"✅ File uploaded successfully: {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")
            
            # Check if it's an Excel file and handle sheet selection
            if self.file_handler.is_excel_file(uploaded_file):
                return self.render_sheet_selection(uploaded_file)
            else:
                # For CSV files, get lightweight info only
                try:
                    # Read only first 10 rows for preview
                    preview_df = pd.read_csv(uploaded_file, nrows=10)
                    
                    # Get total row count efficiently
                    uploaded_file.seek(0)
                    total_rows = sum(1 for line in uploaded_file) - 1  # Subtract header
                    uploaded_file.seek(0)
                    
                    # Show preview info
                    st.markdown("### 👀 File Preview")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Rows", total_rows)
                    with col2:
                        st.metric("Columns", len(preview_df.columns))
                    
                    # Show sample data
                    st.dataframe(preview_df, use_container_width=True)
                    
                    # Return lightweight info for column mapping
                    return {'columns': list(preview_df.columns), 'sheet_name': None, 'lightweight': True}
                    
                except Exception as e:
                    st.error(f"❌ Error reading file: {str(e)}")
                    return None
        
        return None

    def render_sheet_selection(self, uploaded_file):
        """Render sheet selection for Excel files - OPTIMIZED for performance"""
        try:
            # Get available sheets
            available_sheets = self.file_handler.get_excel_sheet_names(uploaded_file)
            st.session_state.available_sheets = available_sheets
            
            if len(available_sheets) == 1:
                # Only one sheet, select it automatically
                selected_sheet = available_sheets[0]
                st.session_state.selected_sheet = selected_sheet
                st.info(f"📄 Found 1 sheet: **{selected_sheet}** (automatically selected)")
                
                # Get lightweight sheet info without loading full DataFrame
                sheet_info = self.file_handler.get_sheet_info_lightweight(uploaded_file, selected_sheet)
                
                # Display basic info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Rows", sheet_info['rows'])
                with col2:
                    st.metric("Columns", sheet_info['columns'])
                with col3:
                    st.metric("Sheet", selected_sheet)
                
                # Show lightweight preview
                if not sheet_info['sample_data'].empty:
                    st.dataframe(sheet_info['sample_data'], use_container_width=True)
                
                # Return column names only for column mapping (no full DataFrame yet)
                return {'columns': sheet_info['column_names'], 'sheet_name': selected_sheet, 'lightweight': True}
                
            else:
                # Multiple sheets, let user choose
                st.markdown("### 📄 Sheet Selection")
                st.info(f"📊 Found {len(available_sheets)} sheets in the Excel file. Please select which sheet to process:")
                
                # Create columns for better layout
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    selected_sheet = st.selectbox(
                        "Select the sheet to process:",
                        options=available_sheets,
                        key="sheet_selector",
                        help="Choose the sheet that contains your vendor data"
                    )
                
                with col2:
                    # Show sheet info button
                    if st.button("📋 Preview Sheets", help="Preview the first few rows of each sheet"):
                        self.show_sheet_preview_lightweight(uploaded_file, available_sheets)
                
                st.session_state.selected_sheet = selected_sheet
                
                # Get lightweight info for selected sheet
                if selected_sheet:
                    sheet_info = self.file_handler.get_sheet_info_lightweight(uploaded_file, selected_sheet)
                    
                    # Show sheet info
                    st.markdown(f"### 👀 Preview of Sheet: **{selected_sheet}**")
                    
                    # Display sheet statistics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Rows", sheet_info['rows'])
                    with col2:
                        st.metric("Columns", sheet_info['columns'])
                    with col3:
                        st.metric("Sheet", selected_sheet)
                    
                    # Show lightweight preview
                    if not sheet_info['sample_data'].empty:
                        st.dataframe(sheet_info['sample_data'], use_container_width=True)
                    
                    # Return column names only for column mapping (no full DataFrame yet)
                    return {'columns': sheet_info['column_names'], 'sheet_name': selected_sheet, 'lightweight': True}
            
        except Exception as e:
            st.error(f"❌ Error processing Excel file: {str(e)}")
            return None
        
        return None

    def show_sheet_preview_lightweight(self, uploaded_file, sheet_names):
        """Show a lightweight preview of all sheets in the Excel file"""
        st.markdown("### 📊 Sheet Previews (Lightweight)")
        
        for sheet_name in sheet_names:
            sheet_info = self.file_handler.get_sheet_info_lightweight(uploaded_file, sheet_name)
            
            if 'error' in sheet_info:
                with st.expander(f"❌ {sheet_name} (Error reading sheet)"):
                    st.error(f"Could not read sheet: {sheet_info['error']}")
            else:
                with st.expander(f"📄 {sheet_name} ({sheet_info['rows']} rows, {sheet_info['columns']} columns)"):
                    if not sheet_info['sample_data'].empty:
                        st.dataframe(sheet_info['sample_data'], use_container_width=True)
                        
                        # Show column info
                        st.markdown("**Columns:**")
                        cols_display = ", ".join(sheet_info['column_names'][:10])
                        if len(sheet_info['column_names']) > 10:
                            cols_display += f" ... (+{len(sheet_info['column_names']) - 10} more)"
                        st.text(cols_display)
                    else:
                        st.warning("This sheet appears to be empty.")

    def show_sheet_preview(self, uploaded_file, sheet_names):
        """Show a preview of all sheets in the Excel file"""
        st.markdown("### 📊 Sheet Previews")
        
        for sheet_name in sheet_names:
            try:
                df = self.file_handler.read_excel_sheet(uploaded_file, sheet_name)
                
                with st.expander(f"📄 {sheet_name} ({len(df)} rows, {len(df.columns)} columns)"):
                    if len(df) > 0:
                        st.dataframe(df.head(5), use_container_width=True)
                        
                        # Show column info
                        st.markdown("**Columns:**")
                        cols_display = ", ".join(df.columns[:10])
                        if len(df.columns) > 10:
                            cols_display += f" ... (+{len(df.columns) - 10} more)"
                        st.text(cols_display)
                    else:
                        st.warning("This sheet appears to be empty.")
                        
            except Exception as e:
                with st.expander(f"❌ {sheet_name} (Error reading sheet)"):
                    st.error(f"Could not read sheet: {str(e)}")
        
        # Reset file pointer for subsequent operations
        uploaded_file.seek(0)

    def render_column_mapping(self, data_info):
        """Render the column mapping interface - OPTIMIZED for performance"""
        st.markdown("## 🔗 Step 2: Column Mapping")
        st.markdown("Select which columns contain the vendor country and SIREN number:")
        
        # Handle both lightweight data info and full DataFrame
        if isinstance(data_info, dict) and 'lightweight' in data_info:
            # Lightweight mode - only column names available
            columns = data_info['columns']
            sheet_name = data_info['sheet_name']
            is_excel = sheet_name is not None
        else:
            # Full DataFrame mode (legacy support)
            columns = list(data_info.columns)
            sheet_name = st.session_state.get('selected_sheet')
            is_excel = sheet_name is not None
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🌍 Vendor Country Column")
            country_column = st.selectbox(
                "Select the column containing vendor countries:",
                options=[''] + columns,
                key="country_column",
                help="This column should contain country codes like 'BE', 'DK', 'FR'"
            )
            
            if country_column:
                # Get sample values efficiently
                if is_excel and sheet_name:
                    sample_values = self.file_handler.get_column_sample_values(
                        st.session_state.uploaded_file, sheet_name, country_column
                    )
                else:
                    sample_values = self.file_handler.get_column_sample_values(
                        st.session_state.uploaded_file, None, country_column
                    )
                st.info(f"Sample values: {', '.join(map(str, sample_values))}")
        
        with col2:
            st.markdown("### 🏢 SIREN Number Column")
            siren_column = st.selectbox(
                "Select the column containing SIREN/company numbers:",
                options=[''] + columns,
                key="siren_column",
                help="This column should contain unique company identification numbers"
            )
            
            if siren_column:
                # Get sample values efficiently
                if is_excel and sheet_name:
                    sample_values = self.file_handler.get_column_sample_values(
                        st.session_state.uploaded_file, sheet_name, siren_column
                    )
                else:
                    sample_values = self.file_handler.get_column_sample_values(
                        st.session_state.uploaded_file, None, siren_column
                    )
                st.info(f"Sample values: {', '.join(map(str, sample_values))}")
        
        # Validate mapping
        if country_column and siren_column:
            if country_column == siren_column:
                st.error("❌ Country and SIREN columns cannot be the same!")
                return None
            
            # Store mapping
            st.session_state.column_mapping = {
                'country': country_column,
                'siren': siren_column
            }
            
            # Show validation summary
            st.success("✅ Column mapping configured successfully!")
            
            # Validate columns with lightweight method
            if is_excel and sheet_name:
                validation_result = self.file_handler.validate_columns_lightweight(
                    st.session_state.uploaded_file, sheet_name, country_column, siren_column
                )
            else:
                validation_result = self.file_handler.validate_columns_lightweight(
                    st.session_state.uploaded_file, None, country_column, siren_column
                )
            
            # Show validation results
            col1, col2 = st.columns(2)
            with col1:
                if validation_result['supported_countries']:
                    st.success(f"✅ Supported countries: {', '.join(validation_result['supported_countries'])}")
            with col2:
                if validation_result['unsupported_countries']:
                    st.warning(f"⚠️ Unsupported countries: {', '.join(validation_result['unsupported_countries'])}")
            
            return st.session_state.column_mapping
        
        return None

    def render_processing_section(self, data_info: Dict, column_mapping: Dict[str, str]):
        """Render the processing section - OPTIMIZED to load data only when processing starts"""
        st.markdown("## ⚙️ Step 3: Process Vendor Data")
        
        # Processing configuration
        with st.expander("🔧 Processing Configuration", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                batch_size = st.number_input("Batch Size", min_value=10, max_value=1000, value=100, step=10)
                retry_attempts = st.number_input("Retry Attempts", min_value=1, max_value=5, value=3)
            with col2:
                timeout_seconds = st.number_input("Timeout (seconds)", min_value=10, max_value=120, value=30)
                concurrent_requests = st.number_input("Concurrent Requests", min_value=1, max_value=10, value=3)
        
        # Estimate processing time based on lightweight data info
        # For lightweight data, we need to get row count from the stored info
        if 'lightweight' in data_info and data_info['lightweight']:
            # This is lightweight data - we need to get row count from file info
            if st.session_state.uploaded_file and hasattr(st.session_state.uploaded_file, 'name'):
                try:
                    if st.session_state.selected_sheet:
                        # Excel file
                        sheet_info = self.file_handler.get_sheet_info_lightweight(
                            st.session_state.uploaded_file, 
                            st.session_state.selected_sheet
                        )
                        total_records = sheet_info['rows']
                    else:
                        # CSV file - get row count efficiently
                        st.session_state.uploaded_file.seek(0)
                        total_records = sum(1 for line in st.session_state.uploaded_file) - 1  # Subtract header
                        st.session_state.uploaded_file.seek(0)
                except:
                    total_records = 0
            else:
                total_records = 0
        else:
            # Legacy support for direct DataFrame
            total_records = len(data_info) if hasattr(data_info, '__len__') else 0
        
        estimated_time = self.estimate_processing_time(total_records, concurrent_requests)
        st.info(f"📊 Processing {total_records} records. Estimated time: {estimated_time}")
        
        # Start processing button
        if st.button("🚀 Start Processing", type="primary", use_container_width=True):
            self.process_vendor_data_lightweight(data_info, column_mapping, {
                'batch_size': batch_size,
                'retry_attempts': retry_attempts,
                'timeout_seconds': timeout_seconds,
                'concurrent_requests': concurrent_requests
            })

    def estimate_processing_time(self, total_records: int, concurrent_requests: int) -> str:
        """Estimate processing time based on record count and concurrency"""
        # Rough estimates based on API/scraping speeds
        avg_time_per_record = 2.5  # seconds
        total_seconds = (total_records * avg_time_per_record) / concurrent_requests
        
        if total_seconds < 60:
            return f"{int(total_seconds)} seconds"
        elif total_seconds < 3600:
            return f"{int(total_seconds // 60)} minutes {int(total_seconds % 60)} seconds"
        else:
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return f"{hours} hours {minutes} minutes"

    def process_vendor_data_lightweight(self, data_info: Dict, column_mapping: Dict[str, str], config: Dict):
        """Process vendor data - OPTIMIZED to load full DataFrame only when processing starts"""
        try:
            st.markdown("### 📂 Loading Full Data for Processing...")
            
            # Load the full DataFrame only now when we actually need it
            if 'lightweight' in data_info and data_info['lightweight']:
                # Load full DataFrame from stored file
                if st.session_state.uploaded_file:
                    if st.session_state.selected_sheet:
                        # Excel file with specific sheet
                        df = self.file_handler.load_full_dataframe_on_demand(
                            st.session_state.uploaded_file, 
                            st.session_state.selected_sheet
                        )
                    else:
                        # CSV file
                        df = self.file_handler.load_full_dataframe_on_demand(
                            st.session_state.uploaded_file
                        )
                else:
                    st.error("❌ File information not found. Please re-upload the file.")
                    return
            else:
                # Legacy support - data_info is already a DataFrame
                df = data_info
            
            st.success(f"✅ Successfully loaded {len(df)} records for processing")
            
            # Now proceed with the original processing logic
            self.process_vendor_data(df, column_mapping, config)
            
        except Exception as e:
            self.logger.error(f"Error loading data for processing: {str(e)}")
            st.error(f"❌ Error loading data for processing: {str(e)}")
            st.error("Please try uploading the file again.")

    def process_vendor_data(self, df: pd.DataFrame, column_mapping: Dict[str, str], config: Dict):
        """Process the vendor data"""
        try:
            # Initialize data processor
            processor = DataProcessor(
                db_manager=self.db_manager,
                logger=self.logger,
                config=config
            )
            
            # Create progress containers
            progress_container = st.container()
            with progress_container:
                st.markdown("### 📈 Processing Progress")
                progress_bar = st.progress(0)
                status_text = st.empty()
                metrics_container = st.container()
            
            # Create log container
            log_container = st.container()
            with log_container:
                st.markdown("### 📋 Processing Log")
                log_placeholder = st.empty()
            
            # Process data with real-time updates
            results = processor.process_vendor_list(
                df=df,
                column_mapping=column_mapping,
                progress_callback=lambda progress, status, metrics: self.update_progress_ui(
                    progress_bar, status_text, metrics_container, log_placeholder,
                    progress, status, metrics
                )
            )
            
            # Store results
            st.session_state.processing_results = results
            st.session_state.processing_complete = True
            st.session_state.log_file_path = results.get('log_file_path')
            
            # Show completion message
            st.success("🎉 Processing completed successfully!")
            
        except Exception as e:
            self.logger.error(f"Processing failed: {str(e)}")
            st.error(f"❌ Processing failed: {str(e)}")
            st.error("Please check the logs for more details.")

    def update_progress_ui(self, progress_bar, status_text, metrics_container, log_placeholder,
                          progress: float, status: str, metrics: Dict):
        """Update the progress UI elements"""
        progress_bar.progress(progress)
        status_text.text(status)
        
        with metrics_container:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Processed", metrics.get('processed', 0))
            with col2:
                st.metric("New Records", metrics.get('new_records', 0))
            with col3:
                st.metric("Errors", metrics.get('errors', 0))
            with col4:
                st.metric("Success Rate", f"{metrics.get('success_rate', 0):.1f}%")
        
        # Update log display
        if 'recent_logs' in metrics:
            log_text = '\n'.join(metrics['recent_logs'][-20:])  # Show last 20 log entries
            log_placeholder.text_area("Recent Log Entries", log_text, height=200)

    def render_results_section(self):
        """Render the results section"""
        if not st.session_state.processing_complete or not st.session_state.processing_results:
            return
        
        st.markdown("## 📊 Step 4: Processing Results")
        
        results = st.session_state.processing_results
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Processed", results.get('total_processed', 0))
        with col2:
            st.metric("New Records Added", results.get('new_records', 0))
        with col3:
            st.metric("Existing Records", results.get('existing_records', 0))
        with col4:
            st.metric("Errors", results.get('errors', 0))
        
        # Detailed results
        with st.expander("📋 Detailed Results", expanded=True):
            if 'country_breakdown' in results:
                st.markdown("### Results by Country")
                country_df = pd.DataFrame(results['country_breakdown']).T
                st.dataframe(country_df, use_container_width=True)
        
        # Download section
        st.markdown("### 📥 Downloads")
        col1, col2 = st.columns(2)
        
        with col1:
            # Download updated database
            if st.button("📊 Download Updated Database", use_container_width=True):
                updated_db = self.db_manager.export_database()
                st.download_button(
                    label="💾 Download JICAP Database",
                    data=updated_db,
                    file_name=f"JICAP_Database_Updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with col2:
            # Download log file
            if st.session_state.log_file_path and os.path.exists(st.session_state.log_file_path):
                with open(st.session_state.log_file_path, 'r') as f:
                    log_content = f.read()
                
                st.download_button(
                    label="📋 Download Processing Log",
                    data=log_content,
                    file_name=f"processing_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )

    def render_sidebar(self):
        """Render the sidebar with additional information and controls"""
        with st.sidebar:
            st.markdown("## 📖 Quick Guide")
            st.markdown("""
            1. **Upload** your vendor list file
            2. **Select sheet** (for Excel files with multiple sheets)
            3. **Map** columns for country and SIREN
            4. **Process** data automatically
            5. **Download** updated database and logs
            """)
            
            st.markdown("## 🌍 Supported Countries")
            st.markdown("""
            - 🇫🇷 **France**: Government API
            - 🇧🇪 **Belgium**: Web scraping
            - 🇩🇰 **Denmark**: Web scraping
            """)
            
            st.markdown("## 📋 File Requirements")
            st.markdown("""
            - **Format**: .xlsx, .xlsb, .csv
            - **Size**: Max 100MB
            - **Sheets**: Excel files support multiple sheets
            - **Columns**: Country, SIREN number
            """)
            
            st.markdown("## ℹ️ About")
            st.markdown("""
            **Version**: 1.0  
            **Last Updated**: May 2025  
            
            This system automates vendor classification by cross-referencing with the JICAP database and fetching missing data from government sources.
            """)

    def run(self):
        """Main application entry point - OPTIMIZED for lightweight processing"""
        try:
            # Render header
            self.render_header()
            
            # Render sidebar
            self.render_sidebar()
            
            # Main workflow - now uses lightweight data structures
            data_info = self.render_file_upload()
            
            if data_info is not None:
                column_mapping = self.render_column_mapping(data_info)
                
                if column_mapping:
                    self.render_processing_section(data_info, column_mapping)
            
            # Always render results section (will show if processing is complete)
            self.render_results_section()
            
            # Reset button
            if st.session_state.processing_complete:
                st.markdown("---")
                if st.button("🔄 Start New Processing", type="secondary"):
                    # Reset session state
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
                    
        except Exception as e:
            self.logger.error(f"Application error: {str(e)}")
            st.error(f"❌ Application error: {str(e)}")
            st.error("Please refresh the page and try again.")

def main():
    """Main function"""
    app = JICAPApp()
    app.run()

if __name__ == "__main__":
    main()
