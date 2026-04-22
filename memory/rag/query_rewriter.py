"""
query_rewriter.py — 独立的 Query 重写模块

支持三种重写策略：
1. expand（默认）：LLM 生成 N 个语义等价的改写，提升召回率
2. decompose：将复杂查询分解为子问题，适合 AND 型复合查询
3. hyde：HyDE（Hypothetical Document Embeddings）生成假设文档文本，
          用假设答案的向量去检索相似文档，适合知识型问答

降级策略：任何 LLM 调用失败时，返回原始查询并打 warning 日志，不抛出异常。

408 考研场景定制：Prompt 中明确限定数据结构/操作系统/计算机网络/计算机组成原理四科。
"""

import logging

from core.llm_client import get_llm_client

logger = logging.getLogger(__name__)


# ============================================================
# QueryRewriter 类
# ============================================================

class QueryRewriter:
    """
    独立的 Query 重写模块，支持多种重写策略。

    策略：
    1. expand（默认）：LLM 生成 N 个语义等价的改写（提升召回率）
    2. decompose：将复杂查询分解为子问题（适合 AND 型查询）
    3. hyde：HyDE（Hypothetical Document Embeddings）生成假设文档

    使用示例：
        rewriter = QueryRewriter()
        queries = rewriter.rewrite("进程调度算法有哪些", strategy="expand", n=3)
        # → ["进程调度算法有哪些", "CPU调度策略", "进程切换算法", "短作业优先算法"]

        sub_queries = rewriter.rewrite("进程和线程的区别及死锁条件", strategy="decompose")
        # → ["进程和线程的区别及死锁条件", "进程是什么", "线程是什么", "死锁的四个必要条件"]

        hyde_text = rewriter.hyde("快速排序的时间复杂度")
        # → "快速排序是一种基于分治策略的排序算法，平均时间复杂度为 O(nlogn)..."
    """

    def __init__(self):
        self._client = get_llm_client()

    # ----------------------------------------------------------
    # 公共入口
    # ----------------------------------------------------------

    def rewrite(self, query: str, strategy: str = "expand", n: int = 3) -> list[str]:
        """
        Query 重写统一入口。

        Args:
            query    : 原始查询字符串
            strategy : 重写策略，可选 "expand" | "decompose" | "hyde"
            n        : expand 策略下生成的改写数量（其他策略忽略此参数）

        Returns:
            [原始查询] + 改写后的查询列表（去重后），LLM 失败时只返回 [原始查询]。
        """
        if strategy == "expand":
            rewrites = self.expand(query, n=n)
        elif strategy == "decompose":
            rewrites = self.decompose(query)
        elif strategy == "hyde":
            hyde_text = self.hyde(query)
            # HyDE 返回一段假设文档，加入原始查询共同检索
            if hyde_text and hyde_text != query:
                return list(dict.fromkeys([query, hyde_text]))
            return [query]
        else:
            logger.warning(f"[QueryRewriter] 未知策略 '{strategy}'，降级为 expand")
            rewrites = self.expand(query, n=n)

        # 合并原始查询 + 改写，去重保序
        all_queries = [query] + [r for r in rewrites if r and r != query]
        return list(dict.fromkeys(all_queries))

    # ----------------------------------------------------------
    # 策略1：expand（语义等价改写，提升召回率）
    # ----------------------------------------------------------

    def expand(self, query: str, n: int = 3) -> list[str]:
        """
        生成 n 个语义等价的改写查询。

        适用场景：用户问"快排怎么写"，可以扩展为"快速排序算法"、
        "partition 函数实现"、"分治排序"等不同表达，提升检索召回率。

        Args:
            query : 原始查询
            n     : 生成的改写数量，默认 3

        Returns:
            改写后的查询列表（不含原始查询），失败时返回空列表
        """
        system_prompt = (
            "你是408考研搜索查询优化专家，专注于数据结构、操作系统、"
            "计算机网络、计算机组成原理四个科目。\n"
            "用户会给你一个考研学习相关的查询，请生成若干个语义相同但"
            "表述不同的搜索查询，用于提升知识库检索的召回率。\n"
            "要求：\n"
            f"1. 生成 {n} 个改写查询，每行一个\n"
            "2. 使用不同的术语、同义词或表达角度\n"
            "3. 保持与原查询相同的语义和考研知识点范围\n"
            "4. 直接输出查询文本，不要编号、不要解释、不要多余文字"
        )
        user_prompt = query

        try:
            resp = self._client.chat.completions.create(
                model=self._client.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=256,
            )
            lines = [
                line.strip()
                for line in resp.choices[0].message.content.strip().splitlines()
                if line.strip()
            ][:n]
            return lines
        except Exception as e:
            logger.warning(f"[QueryRewriter.expand] LLM 调用失败，返回原始查询：{e}")
            return []

    # ----------------------------------------------------------
    # 策略2：decompose（复合查询分解为子问题）
    # ----------------------------------------------------------

    def decompose(self, query: str) -> list[str]:
        """
        将复合查询分解为多个子问题。

        适用场景：
            "进程和线程的区别" → ["进程是什么", "线程是什么", "进程与线程的对比"]
            "TCP三次握手和四次挥手" → ["TCP三次握手流程", "TCP四次挥手流程", "为什么握手三次挥手四次"]

        适合 AND 型查询（包含多个知识点），每个子问题单独检索后合并结果，
        比整句查询能更精准地命中各个知识点对应的文档。

        Returns:
            子问题列表（不含原始查询），失败时返回空列表
        """
        system_prompt = (
            "你是408考研知识点分析专家，专注于数据结构、操作系统、"
            "计算机网络、计算机组成原理四个科目。\n"
            "用户会给你一个包含多个知识点的复合查询，请将其分解为若干个"
            "独立的子问题，每个子问题对应一个具体的知识点。\n"
            "要求：\n"
            "1. 每行输出一个子问题\n"
            "2. 子问题应该是完整的问句，能单独作为检索查询\n"
            "3. 子问题数量控制在 2-5 个\n"
            "4. 若查询本身是简单问题（无需分解），直接返回原查询即可\n"
            "5. 直接输出子问题文本，不要编号、不要解释"
        )
        user_prompt = (
            f"请将以下408考研查询分解为子问题：\n{query}"
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._client.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                max_tokens=256,
            )
            lines = [
                line.strip()
                for line in resp.choices[0].message.content.strip().splitlines()
                if line.strip()
            ][:5]
            return lines
        except Exception as e:
            logger.warning(f"[QueryRewriter.decompose] LLM 调用失败，返回原始查询：{e}")
            return []

    # ----------------------------------------------------------
    # 策略3：hyde（Hypothetical Document Embeddings）
    # ----------------------------------------------------------

    def hyde(self, query: str) -> str:
        """
        HyDE（Hypothetical Document Embeddings）：生成一段假设性答案文档。

        原理：
            与其用简短的查询向量去检索，不如先让 LLM 生成一段"假设的答案"，
            用这段答案的嵌入向量去检索，因为答案和知识库文档在向量空间上更接近。

        适用场景：
            知识型问答，如"快速排序的时间复杂度分析"，生成一段包含具体
            知识点的假设答案，用于向量检索，能召回更精准的参考文档。

        Args:
            query : 用户查询

        Returns:
            假设性答案文档字符串（约 150-300 字），失败时返回原始查询
        """
        system_prompt = (
            "你是408考研辅导专家，专注于数据结构、操作系统、"
            "计算机网络、计算机组成原理四个科目。\n"
            "用户会给你一个考研知识点查询，请生成一段简洁准确的假设性答案段落。\n"
            "要求：\n"
            "1. 内容准确，符合408考研大纲\n"
            "2. 长度约 150-250 字，像教材或参考书中的一段正文\n"
            "3. 使用专业术语，涵盖核心概念、定义、关键结论\n"
            "4. 直接输出答案段落，不要包含'假设'、'可能'等不确定性词语\n"
            "5. 不要以'答：'或'回答：'开头"
        )
        user_prompt = (
            f"为以下408考研查询生成一段假设性答案文档：\n{query}"
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._client.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[QueryRewriter.hyde] LLM 调用失败，返回原始查询：{e}")
            return query


# ============================================================
# 单例工厂函数
# ============================================================

_rewriter_instance: QueryRewriter | None = None


def get_query_rewriter() -> QueryRewriter:
    """
    返回 QueryRewriter 单例实例。

    第一次调用时创建实例，后续调用直接返回缓存对象，避免重复初始化。
    线程安全性说明：当前实现不加锁，适合单线程场景（如考研助手典型用法）。

    Returns:
        QueryRewriter 实例
    """
    global _rewriter_instance
    if _rewriter_instance is None:
        _rewriter_instance = QueryRewriter()
    return _rewriter_instance


# ============================================================
# 自测（不依赖真实 API，只打印 Prompt 内容）
# ============================================================

if __name__ == "__main__":
    import textwrap

    print("=" * 65)
    print("query_rewriter.py 自测（展示 Prompt，不调用真实 API）")
    print("=" * 65)

    # ---- 模拟 QueryRewriter，覆盖 _client 调用 ----
    class _MockClient:
        """模拟 ZhipuAI 客户端，打印 Prompt 并返回预设响应。"""

        class _MockResp:
            class _Choice:
                class _Msg:
                    content = ""
                message = _Msg()
            choices = [_Choice()]

        def __init__(self, responses: list[str]):
            self._responses = iter(responses)

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    messages = kwargs.get("messages", [])
                    print("\n  [system prompt 截取前100字]:")
                    sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                    print(textwrap.indent(sys_msg[:100] + "...", "    "))
                    print("  [user prompt]:")
                    usr_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
                    print(textwrap.indent(usr_msg, "    "))
                    # 返回模拟响应
                    resp = type("R", (), {
                        "choices": [type("C", (), {
                            "message": type("M", (), {"content": "<模拟LLM输出>"})()
                        })()]
                    })()
                    return resp

    # 创建 rewriter 并替换 client
    rewriter = QueryRewriter.__new__(QueryRewriter)
    rewriter._client = type("FakeClient", (), {
        "chat": type("FakeChat", (), {
            "completions": type("FakeComp", (), {
                "create": staticmethod(lambda **kw: type("R", (), {
                    "choices": [type("C", (), {
                        "message": type("M", (), {
                            "content": "改写查询A\n改写查询B\n改写查询C"
                        })()
                    })()]
                })())
            })()
        })()
    })()

    # ---- 测试 expand ----
    print("\n【策略1：expand】")
    print("  输入查询：快速排序的时间复杂度分析")
    result = rewriter.expand("快速排序的时间复杂度分析", n=3)
    print(f"  改写结果：{result}")

    # ---- 测试 decompose ----
    print("\n【策略2：decompose】")
    print("  输入查询：进程和线程的区别及死锁的四个必要条件")
    result2 = rewriter.decompose("进程和线程的区别及死锁的四个必要条件")
    print(f"  分解结果：{result2}")

    # ---- 测试 hyde ----
    print("\n【策略3：hyde】")
    print("  输入查询：TCP三次握手的过程")
    result3 = rewriter.hyde("TCP三次握手的过程")
    print(f"  HyDE文档（前80字）：{result3[:80]}...")

    # ---- 测试 rewrite 统一入口 ----
    print("\n【rewrite() 统一入口测试】")
    for strat in ["expand", "decompose", "hyde"]:
        r = rewriter.rewrite("操作系统内存管理", strategy=strat, n=2)
        print(f"  strategy={strat} → {r}")

    # ---- 测试单例 ----
    print("\n【get_query_rewriter() 单例测试】")
    # 注意：真实场景需有效 API_KEY，此处仅验证函数可调用
    try:
        rw1 = get_query_rewriter()
        rw2 = get_query_rewriter()
        print(f"  单例一致性：{rw1 is rw2}")  # 应为 True
    except Exception as e:
        print(f"  单例创建（无真实 API KEY 时预期可能报错）：{e}")

    print("\n✅ query_rewriter.py 自测完成！")
