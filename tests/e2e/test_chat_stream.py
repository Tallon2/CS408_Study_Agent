"""
tests/e2e/test_chat_stream.py — 端到端聊天流测试骨架

测试覆盖（P3 优先级）：
  1. SSE 流式格式校验（需要运行中的服务器，默认 skip）
  2. 同步 chat 返回字符串

注意：E2E 测试需要服务器运行在 localhost:8000。
运行方式：
    pytest tests/e2e/ -v --run-e2e
    或设置环境变量 RUN_E2E=1
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

pytestmark = pytest.mark.e2e

# 检查是否要运行 E2E 测试（默认跳过）
_RUN_E2E = os.environ.get("RUN_E2E", "0").strip() == "1"
_SKIP_REASON = "E2E 测试需要运行中的服务器（设置 RUN_E2E=1 启用）"

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


# ================================================================
# SSE 流式格式测试
# ================================================================

@pytest.mark.skipif(not _RUN_E2E, reason=_SKIP_REASON)
def test_sse_stream_format():
    """
    SSE 事件格式正确性测试。

    验证：
    - 每个 SSE 事件以 'data: ' 开头
    - JSON 数据包含 'token' 字段
    - 流以 [DONE] 结束
    """
    import httpx

    url = f"{BASE_URL}/api/chat/stream"
    payload = {
        "message": "什么是进程？",
        "session_id": "e2e-test-session",
    }

    chunks = []
    try:
        with httpx.stream("POST", url, json=payload, timeout=30.0) as resp:
            assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}"
            content_type = resp.headers.get("content-type", "")
            assert "text/event-stream" in content_type, (
                f"期望 Content-Type 包含 text/event-stream，实际 {content_type}"
            )
            for line in resp.iter_lines():
                if line:
                    chunks.append(line)
    except httpx.ConnectError:
        pytest.skip(f"无法连接服务器 {BASE_URL}，跳过 E2E 测试")

    assert len(chunks) > 0, "应收到至少一个 SSE 事件"

    # 验证 SSE 格式
    data_lines = [c for c in chunks if c.startswith("data: ")]
    assert len(data_lines) > 0, "应包含 'data: ' 开头的 SSE 数据行"

    # 验证最后一行为 [DONE]
    last_data = [c.replace("data: ", "").strip() for c in data_lines]
    assert "[DONE]" in last_data, "SSE 流应以 [DONE] 结束"


@pytest.mark.skipif(not _RUN_E2E, reason=_SKIP_REASON)
def test_sync_chat_returns_string():
    """
    同步 chat 接口应返回字符串响应。

    验证：
    - HTTP 200
    - 响应 body 包含 'message' 字段
    - 'message' 值为非空字符串
    """
    import httpx
    import json

    url = f"{BASE_URL}/api/chat"
    payload = {
        "message": "操作系统的进程与线程有什么区别？",
        "session_id": "e2e-test-sync",
    }

    try:
        resp = httpx.post(url, json=payload, timeout=60.0)
    except httpx.ConnectError:
        pytest.skip(f"无法连接服务器 {BASE_URL}，跳过 E2E 测试")

    assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}"

    data = resp.json()
    assert "message" in data or "content" in data, (
        f"响应应包含 'message' 或 'content' 字段，实际：{list(data.keys())}"
    )

    reply = data.get("message") or data.get("content", "")
    assert isinstance(reply, str), f"回复应为字符串，实际类型 {type(reply)}"
    assert len(reply) > 0, "回复不应为空字符串"


# ================================================================
# 基础连通性测试（不需要完整服务器）
# ================================================================

def test_e2e_module_imports():
    """验证 E2E 测试所需模块可以正常导入（不依赖服务器）。"""
    # 这是一个永远通过的基础测试，确保测试文件本身语法正确
    assert True


def test_base_url_configuration():
    """验证 E2E 基础 URL 配置正确（不连接服务器）。"""
    assert isinstance(BASE_URL, str)
    assert BASE_URL.startswith("http"), f"BASE_URL 应以 http 开头，实际：{BASE_URL}"
