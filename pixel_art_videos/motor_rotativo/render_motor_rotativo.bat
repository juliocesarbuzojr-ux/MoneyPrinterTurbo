@echo off
chcp 65001 >nul
setlocal
REM ==== Render de "¿Como funciona un motor rotativo?" con Blender 5.3 ====
set "BLENDER=C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
if not exist "%BLENDER%" (
  for /d %%D in ("C:\Program Files\Blender Foundation\Blender*") do if exist "%%D\blender.exe" set "BLENDER=%%D\blender.exe"
)
if not exist "%BLENDER%" (
  echo No encontre blender.exe. Edita la linea BLENDER= de este archivo.
  pause
  exit /b 1
)
cd /d "%~dp0"
echo Usando: %BLENDER%
"%BLENDER%" --background --factory-startup --python "%~dp0motor_rotativo_blender.py" -- --out "%~dp0render" --engine EEVEE
echo.
echo Listo. Los cuadros quedaron en render\cuadros y el zip en render\cuadros_motor_rotativo.zip
pause
