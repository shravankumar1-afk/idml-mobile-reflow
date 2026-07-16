@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m pip install -e .
py -3.11 -m idml2mobile.gui
pause
