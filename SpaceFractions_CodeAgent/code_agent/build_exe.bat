@echo off
rem Builds dist\CodeAgent.exe (single file, no Python needed on the target machine).
python -m pip install -r requirements.txt || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CodeAgent app.py || exit /b 1
echo Built dist\CodeAgent.exe
