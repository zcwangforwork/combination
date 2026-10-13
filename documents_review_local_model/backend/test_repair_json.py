"""测试 _repair_malformed_json 对无效反斜杠转义的修复"""
import json
import sys
import os

# 添加 backend 目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from doc_processor import _repair_malformed_json


def test_invalid_escape_windows_path():
    """测试1: 模拟 LLM 输出含 Windows 路径的无效转义"""
    # LLM 输出的 JSON 字符串中包含 \m \t 等无效转义（原始字符）
    bad_json = r'{"title": "1. 模型路径 E:\model\test", "start_line": 1, "end_line": 5}'
    print("=== Test 1: Windows 路径无效转义 ===")
    print("Input :", repr(bad_json))
    repaired = _repair_malformed_json(bad_json)
    print("Fixed :", repr(repaired))
    try:
        data = json.loads(repaired)
        print("Parse : OK ->", data)
        assert "title" in data
        print("Result: PASS")
        return True
    except (json.JSONDecodeError, AssertionError) as e:
        print("Result: FAIL ->", e)
        return False


def test_invalid_escape_mixed():
    r"""测试2: 混合无效转义 \x \d \ 空格 \中文"""
    bad_json = r'{"desc": "line\xbreak", "code": "\d123", "space": "\ end", "cn": "\中文"}'
    print()
    print("=== Test 2: 混合无效转义 ===")
    print("Input :", repr(bad_json))
    repaired = _repair_malformed_json(bad_json)
    print("Fixed :", repr(repaired))
    try:
        data = json.loads(repaired)
        print("Parse : OK ->", data)
        print("Result: PASS")
        return True
    except json.JSONDecodeError as e:
        print("Result: FAIL ->", e)
        return False


def test_valid_json_unchanged():
    """测试3: 合法 JSON 不应被改动（恒等变换）"""
    good_json = r'{"title": "1.1 产品名称", "start_line": 51, "path": "E:\\model\\xxx"}'
    print()
    print("=== Test 3: 合法 JSON 恒等变换 ===")
    print("Input :", repr(good_json))
    repaired = _repair_malformed_json(good_json)
    print("Fixed :", repr(repaired))
    print("Equal :", good_json == repaired)
    try:
        data = json.loads(repaired)
        print("Parse : OK ->", data)
        assert good_json == repaired, "合法 JSON 被改动"
        print("Result: PASS")
        return True
    except (json.JSONDecodeError, AssertionError) as e:
        print("Result: FAIL ->", e)
        return False


def test_valid_escape_preserved():
    r"""测试4: 合法转义 \" \\ \n \t 应被保留"""
    good_json = r'{"text": "line1\nline2\ttab\\backslash\"quote"}'
    print()
    print("=== Test 4: 合法转义保留 ===")
    print("Input :", repr(good_json))
    repaired = _repair_malformed_json(good_json)
    print("Fixed :", repr(repaired))
    try:
        data = json.loads(repaired)
        print("Parse : OK ->", repr(data))
        print("Result: PASS")
        return True
    except json.JSONDecodeError as e:
        print("Result: FAIL ->", e)
        return False


def test_real_world_failure_case():
    """测试5: 模拟用户实际遇到的错误场景
    错误: Invalid \escape: line 118 column 52 (char 7753)
    通常是 LLM 在 JSON 字符串中输出了无效转义
    """
    # 模拟一个 chapters JSON，title 中含 Windows 路径或文件名带反斜杠
    bad_json = r'''{
  "chapters": [
    {
      "title": "1. 模型配置 E:\model\MinerU",
      "start_line": 64,
      "end_line": 76,
      "subsections": [
        {"title": "1.1 路径 C:\Users\test", "start_line": 66, "end_line": 66}
      ]
    }
  ]
}'''
    print()
    print("=== Test 5: 模拟用户实际错误场景 ===")
    print("Input :", repr(bad_json[:100]), "...")
    repaired = _repair_malformed_json(bad_json)
    print("Fixed :", repr(repaired[:100]), "...")
    try:
        data = json.loads(repaired)
        print("Parse : OK -> chapters count:", len(data.get("chapters", [])))
        print("Result: PASS")
        return True
    except json.JSONDecodeError as e:
        print("Result: FAIL ->", e)
        return False


if __name__ == "__main__":
    results = []
    results.append(test_invalid_escape_windows_path())
    results.append(test_invalid_escape_mixed())
    results.append(test_valid_json_unchanged())
    results.append(test_valid_escape_preserved())
    results.append(test_real_world_failure_case())

    print()
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Total: {passed}/{total} passed")
    if all(results):
        print("===ALL_TESTS_OK===")
    else:
        print("===SOME_TESTS_FAILED===")
        sys.exit(1)
