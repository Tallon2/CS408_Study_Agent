"""
chat.py — 对话路由（SSE 流式输出）

POST   /api/v1/chat/stream    流式对话（SSE）
POST   /api/v1/chat/sync      同步对话（普通 JSON 响应）
GET    /api/v1/chat/history   获取当前会话历史
DELETE /api/v1/chat/session   重置会话（触发 on_session_end）
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dao.models import User
from api.deps import get_current_user, get_agent

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/chat", tags=["对话"])


def _sse_line(event: str, data: str) -> str:
    """格式化一条 SSE 消息：event: xxx\ndata: xxx\n\n"""
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent=Depends(get_agent),
):
    """
    流式对话端点（Server-Sent Events）— 真正逐 token 流式输出。
    
    架构：使用 agent.chat_stream_async() 异步生成器，
    LangGraph 节点的 pipeline 事件和 LLM 的 token 事件通过 asyncio.Queue 交织输出。
    
    支持客户端 AbortController 中断：前端断开连接后，
    GeneratorExit 会传播到 agent，自动取消后台任务。
    """

    async def event_generator():
        try:
            # 发送开始事件
            yield _sse_line("start", json.dumps({"message": "开始处理..."}, ensure_ascii=False))

            # 判断 agent 类型：LangGraphAgent 使用异步流式，LearningAgent 使用同步流式
            if hasattr(agent, 'chat_stream_async'):
                # ── 新版：真正的异步逐 token 流式 ──
                full_reply = ""
                has_done = False
                async for chunk in agent.chat_stream_async(req.message):
                    evt_type = chunk.get("type", "token")
                    if evt_type == "pipeline":
                        yield _sse_line("pipeline", json.dumps(chunk, ensure_ascii=False, default=str))
                    elif evt_type == "token":
                        # 增量 token：content 是每次的新片段，前端需要累加
                        token_content = chunk.get("content", "")
                        full_reply += token_content
                        yield _sse_line("token", json.dumps({"content": token_content, "accumulated": full_reply}, ensure_ascii=False))
                    elif evt_type == "done":
                        full_reply = chunk.get("content", full_reply)
                        yield _sse_line("done", json.dumps({"content": full_reply}, ensure_ascii=False))
                        has_done = True
                    elif evt_type == "error":
                        yield _sse_line("error", json.dumps({"error": chunk.get("content", "未知错误")}, ensure_ascii=False))

                # 补发完成事件（安全兜底）
                if not has_done:
                    yield _sse_line("done", json.dumps({"content": full_reply}, ensure_ascii=False))
            else:
                # ── 旧版兼容：LearningAgent 同步流式 ──
                full_reply = ""
                chunk = None
                for chunk in agent.chat_stream(req.message):
                    if isinstance(chunk, dict):
                        evt_type = chunk.get("type", "token")
                        if evt_type == "pipeline":
                            yield _sse_line("pipeline", json.dumps(chunk, ensure_ascii=False, default=str))
                        elif evt_type == "token":
                            full_reply = chunk.get("content", "")
                            yield _sse_line("token", json.dumps({"content": full_reply}, ensure_ascii=False))
                        elif evt_type == "done":
                            full_reply = chunk.get("content", full_reply)
                            yield _sse_line("done", json.dumps({"content": full_reply}, ensure_ascii=False))
                        elif evt_type == "error":
                            yield _sse_line("error", json.dumps({"error": chunk.get("content", "未知错误")}, ensure_ascii=False))
                    else:
                        full_reply = str(chunk)
                        yield _sse_line("token", json.dumps({"content": full_reply}, ensure_ascii=False))

                if not (isinstance(chunk, dict) and chunk.get("type") == "done"):
                    yield _sse_line("done", json.dumps({"content": full_reply}, ensure_ascii=False))

        except GeneratorExit:
            # 客户端断开连接（AbortController.abort()），正常退出
            raise
        except Exception as e:
            yield _sse_line("error", json.dumps({"error": str(e)}, ensure_ascii=False))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sync")
def chat_sync(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent=Depends(get_agent),
):
    """同步对话端点，返回完整 JSON 响应"""
    reply = agent.chat(req.message)
    return {"reply": reply, "user_id": str(current_user.id)}


@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    agent=Depends(get_agent),
):
    """获取当前 agent session 的消息历史"""
    messages_text = agent.session.get_messages_text()
    lines = messages_text.strip().split("\n") if messages_text.strip() else []
    messages = []
    for line in lines:
        if line.startswith("用户:"):
            messages.append({"role": "user", "content": line[3:].strip()})
        elif line.startswith("助手:"):
            messages.append({"role": "assistant", "content": line[3:].strip()})
    return {"messages": messages, "count": len(messages)}


@router.delete("/session")
def reset_session(
    current_user: User = Depends(get_current_user),
    agent=Depends(get_agent),
):
    """重置会话：触发 on_session_end()，清除 agent 缓存"""
    agent.on_session_end()
    # 清除缓存，强制下次重新初始化
    from api.deps import _agent_cache
    uid = str(current_user.id)
    if uid in _agent_cache:
        del _agent_cache[uid]
    return {"message": "会话已重置，学习记录已保存"}
