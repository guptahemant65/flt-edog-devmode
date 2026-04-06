@ECHO OFF
REM EDOG Browser Launcher — wraps Edge with remote debugging for agent-browser
SET EDGE_PATH=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
IF NOT EXIST "%EDGE_PATH%" SET EDGE_PATH=C:\Program Files\Microsoft\Edge\Application\msedge.exe
START "" "%EDGE_PATH%" --remote-debugging-port=9222 --auto-select-certificate-for-urls=* %*
