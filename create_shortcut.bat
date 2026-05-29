@echo off
setlocal

set "APP_DIR=%~dp0"
set "LAUNCHER=%APP_DIR%run_gui.vbs"
set "SHORTCUT_NAME=Danbooru Downloader.lnk"

if not exist "%LAUNCHER%" (
    echo run_gui.vbs not found: "%LAUNCHER%"
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $shortcut = $ws.CreateShortcut((Join-Path $desktop '%SHORTCUT_NAME%')); $shortcut.TargetPath = 'wscript.exe'; $shortcut.Arguments = '""%LAUNCHER%""'; $shortcut.WorkingDirectory = '%APP_DIR%'; $shortcut.Description = 'Danbooru Downloader'; $shortcut.Save()"

echo Shortcut created on Desktop: %SHORTCUT_NAME%
pause
