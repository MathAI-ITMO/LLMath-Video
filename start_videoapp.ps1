# Start VideoApp with CORS support
Write-Host "Starting VideoApp on http://localhost:5001..." -ForegroundColor Green

# Check if virtual environment exists
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please create it first: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Check if Flask-CORS is installed
$corsInstalled = & .\.venv\Scripts\pip.exe list | Select-String "Flask-CORS"
if (-not $corsInstalled) {
    Write-Host "Installing Flask-CORS..." -ForegroundColor Yellow
    & .\.venv\Scripts\pip.exe install Flask-CORS
}

# Start the app
Write-Host "VideoApp is starting..." -ForegroundColor Cyan
Write-Host "Access at: http://localhost:5001" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

& .\.venv\Scripts\python.exe app.py
