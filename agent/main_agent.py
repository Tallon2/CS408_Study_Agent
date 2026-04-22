"""
agent/main_agent.py — LangGraph Agent 对外统一入口

职责（Phase 3 精简后）：
  - 暴露 LangGraphAgent 的公共接口：chat() / chat_stream() / chat_stream_async()
  - 负责对话历史管理与 LangGraph 图的调用调度
  - 不包含会话生命周期管理（由 agent/runtime.py 负责）
  - 不包含旧版 LearningAgent（已迁移至 agent/legacy_agent.py）

设计约束：
  - 不得直接操作文件系统或数据库
  - 不得直接实例化 ZhipuAI（必须通过 get_llm_client()）
  - AgentState 初始化使用 runtime.build_initial_state()
  - 记忆同步使用 runtime.sync_memory_snapshot()
  - 会话结束使用 runtime.handle_session_end()
"""

import logging
from typing import AsyncGenerator, Generator

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from memory.l1_session import SessionManager
from memory.retrieval import build_memory_context
from agent.runtime import (
    build_initial_state,
    sync_memory_snapshot,
    handle_session_end,
    load_initial_memory,
    SYSTEM_PROMPT,
)

# 向后兼容：外部代码可能 from agent.main_agent import LearningAgent
from agent.legacy_agent import LearningAgent  # noqa: F401

logger = logging.getLogger(__name__)

# ============================================================
# LangGraph Agent — 对外统一入口
# ============================================================

class LangGraphAgent:
    """
    408 学习助手 Agent 的对外统一入口。

    使用方式：
        agent = LangGraphAgent(user_id="user_001")
        response = agent.chat("解释一下 KMP 算法")
        async for chunk in agent.chat_stream_async("出一道操作系统题"):
            yield chunk

    设计说明：
        - AgentState 初始化委托给 runtime.build_initial_state()
        - 记忆快照同步委托给 runtime.sync_memory_snapshot()
        - 会话结束钩子委托给 runtime.handle_session_end()
    """

    def __init__(self, user_id: str = "student_001") -> None:
        self.user_id = user_id
        self.session = SessionManager(user_id)

        # 加载初始记忆快照（L2 任务状态 + L4 用户画像）
        self._memory_l2: dict
        self._memory_l4: dict
        self._memory_l2, self._memory_l4 = load_initial_memory()
        self._current_quiz_answer: str = ""

        # 编译 LangGraph 状态图
        from agent.graph.graph import get_graph, get_prep_graph
        self._graph = get_graph()
        self._prep_graph = get_prep_graph()

        # 初始化对话历史，注入系统提示 + 历史记忆上下文
        memory_ctx = build_memory_context(user_id)
        system_content = SYSTEM_PROMPT + (f"\n\n{memory_ctx}" if memory_ctx else "")
        self._messages: list = [SystemMessage(content=system_content)]

        logger.info("LangGraphAgent 初始化完成 user_id=%s", user_id)

    # ──────────────────────────────────────────────────────────
    # 公共接口
    # ──────────────────────────────────────────────────────────

    def chat(self, user_message: str, session_id: str = "", user_id: str | None = None) -> str:
        """
        同步对话，返回完整回复字符串。

        Args:
            user_message: 用户输入文本
            session_id:   保留参数，兼容 API 层调用签名
            user_id:      保留参数，兼容 API 层调用签名
        """
        self.session.log_user_message(user_message)
        self._messages.append(HumanMessage(content=user_message))

        initial_state = build_initial_state(
            messages=self._messages,
            memory_l2=self._memory_l2,
            memory_l4=self._memory_l4,
            current_quiz_answer=self._current_quiz_answer,
        )

        try:
            result = self._graph.invoke(initial_state)
            reply: str = result.get("final_response", "")

            sync_memory_snapshot(self, result)

            self._messages.append(AIMessage(content=reply))
            self.session.log_assistant_message(reply)
            return reply

        except Exception as exc:
            err_msg = f"[系统错误] {exc}"
            logger.error("chat 执行失败 user_id=%s: %s", self.user_id, exc)
            self.session.log_assistant_message(err_msg)
            return err_msg

    async def chat_stream_async(
        self,
        user_message: str,
        session_id: str = "",
        on_rag_trace: object | None = None,
    ):
        """
        异步流式对话（async generator）— 供 FastAPI SSE 端点使用。

        架构：asyncio.Queue + 后台 Task（准备图 + LLM 流式）
          1. 后台 worker 在线程池中运行 LangGraph 前半段（intent→rag→tool），
             通过 call_soon_threadsafe 实时将 pipeline 事件推入队列
          2. 拿到中间 state 后调用 response_generator_stream() 逐 token 推入队列
          3. 最后在线程池中运行 memory_update 节点更新记忆
          4. 主循环持续从队列取事件并 yield

        Args:
            user_message: 用户输入文本
            session_id:   保留参数，兼容 API 层调用签名
            on_rag_trace: 保留参数，可选 RAG 追踪回调

        Yields:
            dict：
              {"type": "token",    "content": str}     — 增量 token
              {"type": "pipeline", "stage": str, ...}  — RAG 管线事件
              {"type": "done",     "content": str}     — 完成信号
              {"type": "error",    "content": str}     — 错误信号
        """
        import asyncio
        from agent.graph.nodes.response_generator import response_generator_stream
        from agent.graph.nodes.memory_update import memory_update_node

        self.session.log_user_message(user_message)
        self._messages.append(HumanMessage(content=user_message))

        initial_state = build_initial_state(
            messages=self._messages,
            memory_l2=self._memory_l2,
            memory_l4=self._memory_l4,
            current_quiz_answer=self._current_quiz_answer,
        )

        output_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        final_reply = ""

        async def _graph_worker() -> None:
            nonlocal final_reply
            try:
                # ── Phase 1: 线程池中运行 LangGraph 前半段（不含 response_generator）──
                def _run_graph_sync():
                    last_state = None
                    rag_trace_emitted = False

                    for step in self._prep_graph.stream(initial_state, stream_mode="values"):
                        last_state = step

                        if step.get("intent") and step["intent"] != "unknown" and not step.get("final_response"):
                            loop.call_soon_threadsafe(output_queue.put_nowait, {
                                "type": "pipeline", "stage": "intent",
                                "intent": step["intent"], "tool": step.get("tool_name", ""),
                            })

                        if step.get("rag_context") and not step.get("final_response"):
                            trace = step.get("rag_pipeline_trace", [])
                            if trace and not rag_trace_emitted:
                                for t in trace:
                                    loop.call_soon_threadsafe(output_queue.put_nowait, {
                                        "type": "pipeline", "stage": f"rag:{t['step']}", **t,
                                    })
                                rag_trace_emitted = True
                            loop.call_soon_threadsafe(output_queue.put_nowait, {
                                "type": "pipeline", "stage": "rag",
                                "context_preview": step["rag_context"][:100],
                            })

                        if step.get("tool_result") and not step.get("final_response"):
                            loop.call_soon_threadsafe(output_queue.put_nowait, {
                                "type": "pipeline", "stage": "tool",
                                "tool_name": step.get("tool_name", ""),
                                "result_preview": step["tool_result"][:80],
                            })

                    return last_state

                last_state = await loop.run_in_executor(None, _run_graph_sync)

                if not last_state:
                    await output_queue.put({"type": "error", "content": "图执行未返回任何状态"})
                    return

                # 前半段已包含完整 final_response（同步节点处理完毕）
                if last_state.get("final_response"):
                    final_reply = last_state["final_response"]
                    sync_memory_snapshot(self, last_state)
                    for char in final_reply:
                        await output_queue.put({"type": "token", "content": char})
                    await output_queue.put({"type": "done", "content": final_reply})
                    return

                # ── Phase 2: 发送"LLM 生成中"管线事件 ──
                await output_queue.put({"type": "pipeline", "stage": "llm_gen"})

                # ── Phase 3: 线程池中流式调用 LLM，逐 token 推入队列 ──
                def _run_stream_llm():
                    done_signal = None
                    for item in response_generator_stream(last_state):
                        if isinstance(item, dict) and item.get("__done__"):
                            done_signal = item
                        else:
                            loop.call_soon_threadsafe(
                                output_queue.put_nowait,
                                {"type": "token", "content": item},
                            )
                    return done_signal

                done_signal = await loop.run_in_executor(None, _run_stream_llm)

                if done_signal:
                    final_reply = done_signal["full_response"]
                    self._current_quiz_answer = done_signal.get(
                        "quiz_answer", self._current_quiz_answer
                    )
                    await output_queue.put({"type": "done", "content": final_reply})
                else:
                    await output_queue.put({"type": "done", "content": ""})

                # ── Phase 4: 线程池中运行 memory_update 节点 ──
                try:
                    mem_result = await loop.run_in_executor(
                        None, memory_update_node, {**last_state, "final_response": final_reply}
                    )
                    sync_memory_snapshot(self, mem_result)
                except Exception as exc:
                    logger.warning("memory_update 执行失败 user_id=%s: %s", self.user_id, exc)

            except Exception as exc:
                final_reply = f"[系统错误] {exc}"
                logger.error("chat_stream_async worker 失败 user_id=%s: %s", self.user_id, exc)
                await output_queue.put({"type": "error", "content": final_reply})
            finally:
                await output_queue.put(None)  # 哨兵：通知主循环 worker 已完成

        worker_task = asyncio.create_task(_graph_worker())

        try:
            while True:
                event = await output_queue.get()
                if event is None:
                    break
                yield event
        except GeneratorExit:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            raise
        finally:
            if not worker_task.done():
                worker_task.cancel()

        if final_reply:
            self._messages.append(AIMessage(content=final_reply))
            self.session.log_assistant_message(final_reply)

    def chat_stream(self, user_message: str, session_id: str = "") -> Generator[dict, None, None]:
        """
        同步流式对话（保留向后兼容）。

        注意：新的 SSE 端点应优先使用 chat_stream_async()。
        此方法仅保留给旧版同步场景（如 Gradio）使用。

        Yields:
            dict：{"type": "pipeline"|"token"|"done"|"error", ...}
        """
        import re

        self.session.log_user_message(user_message)
        self._messages.append(HumanMessage(content=user_message))

        initial_state = build_initial_state(
            messages=self._messages,
            memory_l2=self._memory_l2,
            memory_l4=self._memory_l4,
            current_quiz_answer=self._current_quiz_answer,
        )

        final_reply = ""
        rag_trace_emitted = False

        try:
            for step in self._graph.stream(initial_state, stream_mode="values"):
                if step.get("intent") and step["intent"] != "unknown" and not step.get("final_response"):
                    yield {"type": "pipeline", "stage": "intent",
                           "intent": step["intent"], "tool": step.get("tool_name", "")}

                if step.get("rag_context") and not step.get("final_response"):
                    trace = step.get("rag_pipeline_trace", [])
                    if trace and not rag_trace_emitted:
                        for t in trace:
                            yield {"type": "pipeline", "stage": f"rag:{t['step']}", **t}
                        rag_trace_emitted = True
                    yield {"type": "pipeline", "stage": "rag",
                           "context_preview": step["rag_context"][:100]}

                if step.get("tool_result") and not step.get("final_response"):
                    yield {"type": "pipeline", "stage": "tool",
                           "tool_name": step.get("tool_name", ""),
                           "result_preview": step["tool_result"][:80]}

                if step.get("final_response"):
                    final_reply = step["final_response"]
                    sync_memory_snapshot(self, step)
                    sentences = re.split(r'(?<=[。！？\n])', final_reply)
                    accumulated = ""
                    for sentence in sentences:
                        accumulated += sentence
                        yield {"type": "token", "content": accumulated}
                    yield {"type": "done", "content": final_reply}
                    break

        except Exception as exc:
            final_reply = f"[系统错误] {exc}"
            logger.error("chat_stream 执行失败 user_id=%s: %s", self.user_id, exc)
            yield {"type": "error", "content": final_reply}

        if final_reply:
            self._messages.append(AIMessage(content=final_reply))
            self.session.log_assistant_message(final_reply)

    async def on_session_end(self, session_id: str = "") -> None:
        """
        会话结束回调，触发 L1-L4 全量持久化。

        Args:
            session_id: 保留参数，兼容 API 层调用签名
        """
        handle_session_end(self)
