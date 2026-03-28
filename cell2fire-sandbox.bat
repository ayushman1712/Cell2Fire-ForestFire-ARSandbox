@echo off
echo ============================================================
echo    Cell2Fire AR Sandbox — Projection Map System
echo ============================================================
echo.
echo Controls:
echo   SPACE      - Capture terrain from Kinect
echo   F          - Precompute fire simulation (saves to disk)
echo   P          - Play precomputed simulation
echo   Click      - Set custom ignition point
echo   Arrows     - Wind direction
echo   +/-        - Wind speed
echo   R          - Reset fire
echo   ESC        - Quit
echo.
python -m cell2fire.sandbox
pause
