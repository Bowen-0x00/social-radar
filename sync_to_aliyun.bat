@echo off
chcp 65001 >nul
title SocialRadar 同步到阿里云

echo ======================================================
echo    正在将 SocialRadar 同步到阿里云服务器 (aliyun)...
echo ======================================================

python "%~dp0sync_to_aliyun.py" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [错误] 同步过程中发生异常。
) else (
    echo.
    echo [完成] 同步成功！
)

echo.
pause
