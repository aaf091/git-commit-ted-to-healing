# Starts the backend: installs deps, generates demo data, runs the API on :8000
Set-Location "$PSScriptRoot/backend"
python -m pip install -r requirements.txt
if (-not (Test-Path "data/synthetic_patients.csv")) { python generate_data.py }
python -m uvicorn main:app --reload --port 8000
