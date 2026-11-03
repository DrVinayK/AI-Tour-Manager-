@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo Creating virtual environment...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"
pip install -r requirements.txt

echo Starting Flask frontend on http://127.0.0.1:5000
echo This frontend uses FASTAPI_BASE_URL from .env
python app.py
