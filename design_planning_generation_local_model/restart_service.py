"""
便捷脚本：重启服务
"""

import os
import sys
import subprocess
import time
import signal
from pathlib import Path


def find_and_kill_processes():
    """查找并杀死占用8001端口的进程"""
    print("正在查找8001端口进程...")

    try:
        # Windows 使用 netstat
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )

        pids = set()
        for line in result.stdout.split('\n'):
            if ':8001' in line and 'LISTENING' in line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid and pid.isdigit():
                        pids.add(pid)

        if pids:
            print(f"找到进程: {', '.join(pids)}")
            for pid in pids:
                try:
                    subprocess.run(['taskkill', '/F', '/PID', pid],
                                 capture_output=True)
                    print(f"  已杀死进程 {pid}")
                except Exception as e:
                    print(f"  杀死进程 {pid} 失败: {e}")
        else:
            print("没有找到占用8001端口的进程")

        time.sleep(1)
        return True

    except Exception as e:
        print(f"查找进程失败: {e}")
        return False


def start_service():
    """启动服务"""
    print("\n正在启动服务...")

    project_root = Path(__file__).parent

    # 使用 conda 环境
    conda_path = r"E:\anaconda\anaconda_content\Scripts\conda.exe"
    env_name = "env_01"

    cmd = f'"{conda_path}" run -n {env_name} python run.py'

    print(f"启动命令: {cmd}")
    print(f"工作目录: {project_root}")
    print("\n服务正在启动... 按 Ctrl+C 停止\n")

    try:
        os.chdir(project_root)
        # 使用 subprocess.Popen 启动
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(project_root)
        )

        # 等待一段时间让服务启动
        time.sleep(3)

        # 检查进程是否还在运行
        if process.poll() is None:
            print("\n✅ 服务启动成功！")
            print("   访问: http://localhost:8001")
            print(f"   进程 PID: {process.pid}")
            return process
        else:
            print("\n❌ 服务启动失败！")
            return None

    except KeyboardInterrupt:
        print("\n收到停止信号")
        return None
    except Exception as e:
        print(f"\n启动服务失败: {e}")
        return None


def main():
    print("=" * 60)
    print("服务重启工具")
    print("=" * 60)

    # 1. 清理旧进程
    find_and_kill_processes()

    # 2. 启动新服务
    process = start_service()

    if process:
        try:
            # 等待用户中断
            process.wait()
        except KeyboardInterrupt:
            print("\n正在停止服务...")
            process.terminate()
            process.wait()
            print("服务已停止")


if __name__ == "__main__":
    main()
