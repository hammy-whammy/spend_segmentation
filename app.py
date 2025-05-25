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
        if 'column_mapping' not in st.session_state:
            st.session_state.column_mapping = {}
        if 'processing_results' not in st.session_state:
            st.session_state.processing_results = None
        if 'log_file_path' not in st.session_state:
            st.session_state.log_file_path = None

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
            help="Supported formats: Excel (.xlsx, .xlsb) and CSV (.csv). Maximum file size: 50MB"
        )
        
        if uploaded_file is not None:
            # Validate file size
            if uploaded_file.size > 50 * 1024 * 1024:  # 50MB
                st.error("❌ File size exceeds 50MB limit. Please upload a smaller file.")
                return None
                
            # Save uploaded file to session state
            st.session_state.uploaded_file = uploaded_file
            
            # Display file info
            st.success(f"✅ File uploaded successfully: {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")
            
            # Preview file content
            try:
                df = self.file_handler.read_file(uploaded_file)
                st.markdown("### 👀 File Preview")
                st.dataframe(df.head(10), use_container_width=True)
                return df
            except Exception as e:
                st.error(f"❌ Error reading file: {str(e)}")
                return None
        
        return None

    def render_column_mapping(self, df: pd.DataFrame):
        """Render the column mapping interface"""
        st.markdown("## 🔗 Step 2: Column Mapping")
        st.markdown("Select which columns contain the vendor country and SIREN number:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🌍 Vendor Country Column")
            country_column = st.selectbox(
                "Select the column containing vendor countries:",
                options=[''] + list(df.columns),
                key="country_column",
                help="This column should contain country codes like 'BE', 'DK', 'FR'"
            )
            
            if country_column:
                # Show sample values
                sample_values = df[country_column].dropna().unique()[:10]
                st.info(f"Sample values: {', '.join(map(str, sample_values))}")
        
        with col2:
            st.markdown("### 🏢 SIREN Number Column")
            siren_column = st.selectbox(
                "Select the column containing SIREN/company numbers:",
                options=[''] + list(df.columns),
                key="siren_column",
                help="This column should contain unique company identification numbers"
            )
            
            if siren_column:
                # Show sample values
                sample_values = df[siren_column].dropna().unique()[:10]
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
            
            # Show supported countries
            countries_in_data = df[country_column].dropna().unique()
            supported = []
            unsupported = []
            
            for country in countries_in_data:
                if str(country).upper() in ['BE', 'DK', 'FR']:
                    supported.append(country)
                else:
                    unsupported.append(country)
            
            col1, col2 = st.columns(2)
            with col1:
                if supported:
                    st.success(f"✅ Supported countries: {', '.join(supported)}")
            with col2:
                if unsupported:
                    st.warning(f"⚠️ Unsupported countries: {', '.join(unsupported)}")
            
            return st.session_state.column_mapping
        
        return None

    def render_processing_section(self, df: pd.DataFrame, column_mapping: Dict[str, str]):
        """Render the processing section"""
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
        
        # Estimate processing time
        total_records = len(df)
        estimated_time = self.estimate_processing_time(total_records, concurrent_requests)
        st.info(f"📊 Processing {total_records} records. Estimated time: {estimated_time}")
        
        # Start processing button
        if st.button("🚀 Start Processing", type="primary", use_container_width=True):
            self.process_vendor_data(df, column_mapping, {
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
            2. **Map** columns for country and SIREN
            3. **Process** data automatically
            4. **Download** updated database and logs
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
            - **Size**: Max 50MB
            - **Columns**: Country, SIREN number
            """)
            
            st.markdown("## ℹ️ About")
            st.markdown("""
            **Version**: 1.0  
            **Last Updated**: May 2025  
            
            This system automates vendor classification by cross-referencing with the JICAP database and fetching missing data from government sources.
            """)

    def run(self):
        """Main application entry point"""
        try:
            # Render header
            self.render_header()
            
            # Render sidebar
            self.render_sidebar()
            
            # Main workflow
            df = self.render_file_upload()
            
            if df is not None:
                column_mapping = self.render_column_mapping(df)
                
                if column_mapping:
                    self.render_processing_section(df, column_mapping)
            
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
