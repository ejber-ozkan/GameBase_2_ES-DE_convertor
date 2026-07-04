#!/bin/bash
# ==================================================
#   GameBase to ES-DE Metadata Converter (Unix)
# ==================================================

# Exit immediately if a command exits with a non-zero status
set -e

# Change to the script's directory
cd "$(dirname "$0")"

echo "=================================================="
echo "  GameBase to ES-DE Metadata Converter (Linux/Mac)"
echo "=================================================="
echo

# 1. Check if Python 3 is installed
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 was not found on your system."
    echo "Please install Python 3.x using your package manager (apt, brew, etc.)."
    exit 1
fi

# 2. Set up virtual environment
if [ ! -d "venv" ]; then
    echo "[INFO] Python virtual environment 'venv' not found. Creating one..."
    python3 -m venv venv
    
    echo "[INFO] Virtual environment created."
    echo "[INFO] Installing required dependencies (access-parser)..."
    ./venv/bin/pip install access-parser
    echo "[INFO] Dependencies installed successfully."
    echo
fi

# 3. Run the converter script
echo "[INFO] Running converter script..."
./venv/bin/python convert_gamebase.py "$@"

echo
echo "[INFO] Process completed successfully!"
echo
