# -*- coding: utf-8 -*-
"""审核后端测试配置：把 backend/（平铺模块根）加入 sys.path，
使 tests/ 内可以直接 `import review_auth` / `import main`"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
