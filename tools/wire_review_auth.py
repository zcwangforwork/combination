# -*- coding: utf-8 -*-
"""
wire_review_auth.py — 将用户鉴权接线进文档审核 Agent 后端（combination 副本，幂等可重跑）。

编辑目标:
  ../documents_review_local_model/backend/main.py（3 处: import / 路由依赖 / CORS）

路由依赖规则（全部机械化）:
  路径含 conversation / segment / history → dependencies=[Depends(require_session_access)]
  其余 /api/**                            → dependencies=[Depends(require_user)]
  /health /info / /agent /static 不动（/health 供前端端口探测，必须保持无鉴权）

幂等守卫: import 用标记注释；路由依赖以全文是否已含 Depends(require_user) 判断
（一次性全量替换，无部分状态）；CORS 用标记注释。
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MAINPY = os.path.normpath(os.path.join(
    HERE, '..', 'documents_review_local_model', 'backend', 'main.py'))

IMPORT_MARKER = '# [COMBINATION-PORT] 用户鉴权'
CORS_MARKER = '# [COMBINATION-PORT] 跨源 CORS'


def wire_imports(text):
    if IMPORT_MARKER in text:
        print('SKIP (already wired): main.py +auth imports')
        return text
    anchor = 'from pydantic import BaseModel, Field'
    assert text.count(anchor) == 1, 'pydantic import anchor not unique'
    block = (
        anchor + '\n'
        '\n'
        + IMPORT_MARKER + '（combination 移植新增）：体系管理系统 JWT 验签 + 会话归属\n'
        'from fastapi import Depends\n'
        'from review_auth import require_user, require_session_access'
    )
    return text.replace(anchor, block)


def wire_route_deps(text):
    if 'Depends(require_user)' in text:
        print('SKIP (already wired): main.py +route dependencies')
        return text
    n = 0

    def _sub(m):
        nonlocal n
        method, path = m.group(1), m.group(2)
        if any(k in path for k in ('conversation', 'segment', 'history')):
            dep = 'require_session_access'
        else:
            dep = 'require_user'
        n += 1
        return '@app.%s("%s", dependencies=[Depends(%s)]' % (method, path, dep)

    text = re.sub(r'@app\.(get|post)\("(/api/[^"]+)"', _sub, text)
    assert n > 0, 'no /api routes matched'
    print('WIRED: main.py +route dependencies (%d routes)' % n)
    return text


def wire_cors(text):
    if CORS_MARKER in text:
        print('SKIP (already wired): main.py +cors origins')
        return text
    anchor = '    allow_origins=["*"],'
    assert text.count(anchor) == 1, 'cors anchor not unique (%d)' % text.count(anchor)
    repl = (
        '    ' + CORS_MARKER + ': 允许体系文档管理系统前端(:3000)访问本服务\n'
        '    #（原 allow_origins=["*"]；前端凭证走 Authorization 头而非 cookie）\n'
        '    allow_origins=[\n'
        '        "http://localhost:3000",\n'
        '        "http://127.0.0.1:3000",\n'
        '    ],'
    )
    return text.replace(anchor, repl)


def main():
    with io.open(MAINPY, 'r', encoding='utf-8', newline='') as f:
        text = f.read()
    text = wire_imports(text)
    text = wire_route_deps(text)
    text = wire_cors(text)
    with io.open(MAINPY, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    print('=== wire_review_auth OK ===')


if __name__ == '__main__':
    main()
