#!/bin/bash

# JICAP Vendor Classification System - Startup Script
# This script sets up and runs the JICAP system

set -e  # Exit on any error

echo "🏢 JICAP Vendor Classification System - Setup & Start"
echo "=================================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "Please install Python 3.8 or higher and try again."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
playwright install chromium

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs
mkdir -p backups

# Check if database file exists
if [ ! -f "JICAP Company Dataset.xlsx" ]; then
    echo "⚠️ Warning: JICAP Company Dataset.xlsx not found."
    echo "The system will create a new empty database."
fi

# Run tests (optional)
if [ "$1" == "--test" ]; then
    echo "🧪 Running tests..."
    python -m pytest tests/ -v
    if [ $? -ne 0 ]; then
        echo "❌ Tests failed. Please check the output above."
        exit 1
    fi
    echo "✅ All tests passed!"
fi

# Start the application
echo ""
echo "🚀 Starting JICAP Vendor Classification System..."
echo "The application will open in your default web browser."
echo "If it doesn't open automatically, visit: http://localhost:8501"
echo ""
echo "To stop the application, press Ctrl+C"
echo ""

# Run Streamlit
streamlit run app.py
