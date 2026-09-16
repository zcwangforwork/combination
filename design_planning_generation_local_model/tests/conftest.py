"""pytest配置 - Agent测试"""
import sys
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def pytest_configure(config):
    """配置pytest"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
