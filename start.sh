#!/bin/bash
echo "Starting Ultra Safe Add Bot..."

# Update pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Run Flask + Bot
python ultra_safe_add.py
