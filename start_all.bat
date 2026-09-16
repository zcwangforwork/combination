@echo off
chcp 65001 >nul
title combination - 一键启动（3 个服务窗口）
echo ============================================
echo  combination 启动：体系管理后端 :8080
echo                  体系管理前端 :3000
echo                  Agent 服务   :8002（占用时自动回退 8003/8004）
echo  前置：PostgreSQL 已运行；Ollama :11435 已就绪（qwen3.5:122b）
echo ============================================
pause

start "UM-Backend-8080"  cmd /k "cd /d %~dp0user_management\backend && mvn spring-boot:run"

start "UM-Frontend-3000" cmd /k "cd /d %~dp0user_management\frontend && npx http-server -p 3000 -c-1"

start "Agent-8002"       cmd /k "cd /d %~dp0design_planning_generation_local_model && call E:\anaconda\anaconda_content\Scripts\activate.bat env_01 && python run.py"

echo.
echo 三个窗口已启动。等待就绪后访问 http://localhost:3000
echo 首次验收请按 combination\SMOKE-TEST.md 逐项检查。
