#!/bin/bash
pip install --no-cache-dir -r requirements.txt
gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app
