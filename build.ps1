$ErrorActionPreference = "Stop"

Write-Host "=== Media iCopy Build Script ===" -ForegroundColor Cyan

# Ensure dependencies are installed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt | Out-Null

# Run tests
Write-Host "Running tests..." -ForegroundColor Yellow
pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tests failed! Build aborted." -ForegroundColor Red
    exit 1
}

# Run PyInstaller
Write-Host "Building executable with PyInstaller..." -ForegroundColor Yellow
pyinstaller --noconfirm media-icopy.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "Executable is located at: dist\MediaiCopy.exe" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
} else {
    Write-Host "Build failed." -ForegroundColor Red
    exit 1
}
