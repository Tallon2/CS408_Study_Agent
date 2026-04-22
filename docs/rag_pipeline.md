# RAG 混合检索管线详细设计

> 模块路径：`memory/rag/` | 主入口：`retriever_rag.py → retrieve()` | 版本 v2.0

---

## 1. 管线概述

本系统采用 **六步混合检索管线**，将向量语义检索与 BM25 关键词检索融合，配合多级精排和质量门控，为 408 考研场景提供高质量的知识检索能力。

### 管线流程图

```
用户查询 (query)
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Step 1: 双路检索                                 │
│                                                    │
│  ┌─────────────────┐   ┌─────────────────┐        │
│  │  向量检索        │   │  BM25 稀疏检索   │        │
│  │  ChromaDB        │   │  jieba + BM25Okapi│       │
│  │                  │   │                   │       │
│  │  textbooks: 5条  │   │  textbooks: 5条   │       │
│  │  exam: 5条       │   │  exam: 5条        │       │
│  │  keypoints: 3条  │   │  keypoints: 5条   │       │
│  └────────┬────────┘   └────────┬──────────┘       │
│           │                      │                  │
│           ▼                      ▼                  │
│  ┌──────────────────────────────────────┐          │
│  │  Step 2: RRF 融合                    │          │
│  │  score(d) = Σ 1/(k + rank_i)        │          │
│  │  k = 60，去重（text[:100]指纹）      │          │
│  └────────────────┬─────────────────────┘          │
└───────────────────┼────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────┐
│  Step 3: 评分门控                                 │
│  check_by_mode(fused, mode="normal")              │
│                                                    │
│  ├─ 通过 (best_rrf_score >= 0.02) → 继续          │
│  └─ 未通过 → 触发 Query 重写二次检索               │
│      └─ expand(query, n=3) → 2 个改写查询          │
│         → 二次双路检索 → 重新 RRF 融合             │
│                                                    │
│  apply_gate_by_mode: 过滤噪声尾部                  │
│  (保留 rrf_score >= threshold*0.5，最少3条)         │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 4: Reranker 精排（三级降级链）               │
│                                                    │
│  if use_reranker_api:                              │
│    ① Jina Reranker API (jina-reranker-v2)          │
│       ↓ 失败                                       │
│    ② SiliconFlow API (Qwen3-Reranker)              │
│       ↓ 失败                                       │
│  ③ LLM Rerank (GLM 打分 0-10)                      │
│       ↓ 失败                                       │
│  ④ 保持 RRF 原排序（最终兜底）                      │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 5: Auto-merging                              │
│  命中子块(600字符) → 替换为父块(2000字符)          │
│  按 (source, page, parent_index) 去重              │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 6: 格式化输出                                │
│  【参考资料1】（来源：科目、文件、§章节、页码）     │
│  内容文本...                                       │
└──────────────────────────────────────────────────┘
```

### 降级策略总览

| 场景 | 降级方案 |
|------|---------|
| BM25 索引不存在 | 仅向量检索（单路模式） |
| 评分门控未通过 | Query 重写 → 二次双路检索 |
| Jina Reranker API 不可用 | 降级至 SiliconFlow API |
| SiliconFlow API 不可用 | 降级至 LLM Rerank |
| LLM Rerank 失败 | 保持 RRF 原排序 |
| ChromaDB 不可用 | 返回空字符串 `""` |

---

## 2. Step 1: 双路检索

> 源码：`retriever_rag.py → _dual_retrieve()`

### 2.1 向量检索（ChromaDB）

使用智谱 `embedding-3` 模型（1024 维）将查询转为向量，在 ChromaDB 中执行近邻检索。

**三个集合的检索配置：**

| 集合名 | 内容 | 每集合返回数 |
|--------|------|-------------|
| `textbooks` | 教材内容（PDF 切片） | 5 条 |
| `exam_questions` | 历年真题（JSONL） | 5 条 |
| `key_points` | Markdown 考点笔记 | 3 条 |

**相似度计算**：ChromaDB 返回 cosine distance，转换为 similarity：`score = max(0.0, 1.0 - distance)`

**Embedding 函数**：`ZhipuEmbeddingFunction`（自定义 `chromadb.EmbeddingFunction`），入库和检索使用同一函数实例，确保向量空间一致。文本截断上限 1500 字符。

### 2.2 BM25 稀疏检索

> 源码：`bm25_retriever.py → BM25Retriever`

**算法**：BM25Okapi（`rank-bm25` 库）

**分词**：jieba 精确模式（`cut_all=False`）

**索引持久化**：
- 索引文件存储在 `storage/bm25_index/{collection_name}.json`
- JSON 结构：`{corpus_tokenized, ids, texts, metadatas}`
- 首次使用需调用 `build_all()` 从 ChromaDB 全量拉取 → 分词 → 存盘
- 后续检索直接从磁盘加载 → 内存缓存

**检索流程**：
1. 确保索引已加载到内存（懒加载）
2. 对查询 jieba 分词
3. `bm25.get_scores(query_tokens)` 计算所有文档的 BM25 分数
4. 取 top-n 索引（`np.argsort` 降序）
5. 归一化：`normalized_score = raw_score / max_score`
6. 过滤 score=0 的文档（完全不相关）

**每集合返回数**：5 条（`bm25_n_results: 5`）

---

## 3. Step 2: RRF 融合

> 源码：`hybrid_fusion.py → rrf_fusion()`

### 算法原理

**Reciprocal Rank Fusion (RRF)**：对每个文档在各检索列表中的排名取倒数求和。

$$
\text{rrf\_score}(d) = \sum_{i} \frac{1}{k + \text{rank}_i(d)}
$$

- **k = 60**：RRF 论文推荐默认值，对高排名文档有较强加权
- **rank 从 1 开始**：第 1 名文档 `rrf_score = 1/(60+1) ≈ 0.0164`
- **双路命中加成**：同时出现在向量和 BM25 结果中的文档，`rrf_score ≈ 2 × 1/61 ≈ 0.0328`

### 去重策略

- 文档指纹：`text[:100].strip()`
- 同一列表内：相同文档只取首次出现（最高排名）
- 跨列表：相同文档的 RRF 分数累加

### 输出字段

每条融合结果新增：
- `rrf_score`：float，RRF 融合分数（越高越相关）
- `in_vector`：bool，是否出现在向量检索结果中
- `in_bm25`：bool，是否出现在 BM25 检索结果中

### 排序

按 `(rrf_score, score)` 双键降序排列（rrf_score 相同时，原始 score 高的优先）。

---

## 4. Step 3: 评分门控

> 源码：`score_gate.py → ScoreGate`

### 三档阈值

| 模式 | 阈值 | 适用场景 |
|------|------|---------|
| `strict` | 0.03 | 高精度场景（如 AI 出题），要求融合排名非常靠前 |
| `normal` | 0.02 | **默认模式**，平衡精度与召回，相当于 top-50 内的文档 |
| `loose` | 0.01 | 召回优先场景（如扩展阅读推荐），接受边缘相关文档 |

噪声下界：`_NOISE_FLOOR = 0.005`（低于此值视为噪声，绝对过滤）

### 整体质量检查 (`check_by_mode`)

- 取所有结果中的最高 `rrf_score`
- `best_score >= threshold` → 通过
- `best_score < threshold` → 不通过，触发 Query 重写二次检索

### 细粒度过滤 (`apply_gate_by_mode`)

1. 计算动态下界：`max(threshold * 0.5, 0.005)`
2. 过滤掉 `rrf_score < _NOISE_FLOOR` 的绝对噪声
3. 过滤掉 `rrf_score < 动态下界` 的低质量文档
4. **保底机制**：如果过滤后不足 3 条，回退到非噪声文档的 top-3

### Query 重写二次检索

> 源码：`retriever_rag.py → _fallback_with_rewrite()`

门控未通过时触发：

1. 调用 `QueryRewriter.expand(query, n=3)` 生成 3 个改写查询
2. 去掉与原始查询相同的改写，取最多 2 个
3. 对每个改写查询执行完整的双路检索
4. 将新结果与原结果 RRF 融合
5. 合并去重，按 `rrf_score` 降序排列

---

## 5. Query 重写模块

> 源码：`query_rewriter.py → QueryRewriter`

### 三种重写策略

| 策略 | 入口方法 | 说明 | 温度 | 适用场景 |
|------|---------|------|------|---------|
| `expand` | `expand(query, n=3)` | 生成 N 个语义等价的改写查询 | 0.7 | **默认**，提升召回率 |
| `decompose` | `decompose(query)` | 将复合查询分解为 2-5 个子问题 | 0.5 | AND 型复合查询 |
| `hyde` | `hyde(query)` | 生成 150-250 字假设性答案文档 | 0.3 | 知识型问答，用答案向量检索 |

### 408 考研场景定制

所有 Prompt 均包含领域限定：

```
你是408考研搜索查询优化专家，专注于数据结构、操作系统、
计算机网络、计算机组成原理四个科目。
```

### 降级策略

任何 LLM 调用失败时，返回原始查询并打 warning 日志，不抛出异常。

### 统一入口

```python
rewriter.rewrite(query, strategy="expand", n=3)
# 返回: [原始查询] + [改写查询...] （去重保序）
```

---

## 6. Step 4: Reranker 精排

> 源码：`retriever_rag.py → _api_rerank()` + `_llm_rerank()`

### 三级降级链

```
┌───────────────────────────┐
│ Level 1: Jina Reranker API│  模型: jina-reranker-v2-base-multilingual
│ (需设置 JINA_API_KEY)     │  URL: https://api.jina.ai/v1/rerank
└─────────┬─────────────────┘
          │ 失败/无 KEY
          ▼
┌───────────────────────────┐
│ Level 2: SiliconFlow API  │  模型: Qwen/Qwen3-Reranker
│ (需设置 SILICONFLOW_KEY)  │  URL: https://api.siliconflow.cn/v1/rerank
└─────────┬─────────────────┘
          │ 失败/无 KEY
          ▼
┌───────────────────────────┐
│ Level 3: LLM Rerank       │  模型: 智谱 GLM (config.MODEL)
│ (GLM 打分 0-10)           │  Prompt: 对每个候选片段打相关性分
│                           │  温度: 0.1, max_tokens: 512
└─────────┬─────────────────┘
          │ 失败
          ▼
┌───────────────────────────┐
│ Level 4: 保持 RRF 原排序  │  最终兜底，确保系统始终可用
└───────────────────────────┘
```

### API Rerank 细节

- 候选文本截取前 512 字符（`texts = [item["text"][:512] for item in candidates]`）
- HTTP 超时：10 秒
- 返回格式：`{results: [{index, relevance_score}]}`

### LLM Rerank 细节

- 候选片段截取前 200 字符
- Prompt 要求返回 JSON 数组：`[{"index": 0, "score": 8}, ...]`
- 分数含义：0 = 完全无关，10 = 高度相关
- 支持提取 ` ```json ``` ` 包裹的 JSON

### 候选数量

取融合后的前 20 条候选进入 Reranker（`candidates = fused[:min(20, len(fused))]`）。

---

## 7. Step 5: Auto-merging

> 源码：`indexer.py → auto_merge_context()`

### 原理

检索阶段返回的是 600 字符的子块（精准匹配），但直接传给 LLM 上下文可能不完整。Auto-merging 将命中的子块替换为其对应的 2000 字符父块。

### 去重逻辑

- 去重键：`{source}__page{page}__parent{parent_index}`
- 同一父块下多个命中子块只保留一次
- 旧格式数据（无 `parent_text`）原样返回

### 输出

每条结果新增 `merged: bool` 字段，标识是否已执行父块替换。

---

## 8. 三级分块策略

> 源码：`indexer.py → chunk_text_hierarchical()` + `chunk_text_with_parent()`

### 三级设计

| 级别 | 用途 | 字符数 | 重叠 | 说明 |
|------|------|--------|------|------|
| **L1 父块** | 返回给 LLM | 2000 | 200 | 上下文完整，Auto-merging 的替换目标 |
| **L2 子块** | 向量检索 | 600 | 80 | 粒度适中，向量匹配精度最佳 |
| **L3 句子块** | 精确匹配 | 150 | 20 | 细粒度，适合术语级精确匹配 |

### chunk_text_with_parent()

实际入库使用的核心函数，返回带父块索引的子块列表：

```python
{
    "text": "子块文本（600字符，用于向量检索）",
    "parent_text": "父块文本（2000字符，命中时返回给LLM）",
    "parent_index": 0,       # 父块在父块列表中的索引
    "child_index": 0,        # 子块在全局列表中的索引
    "level": "child"
}
```

**父块归属算法**：计算子块中心点 `(start + end) // 2`，取最后一个 `start <= center` 的父块。

### Metadata 字段（入库时写入 ChromaDB）

```python
{
    "subject": "数据结构",           # 科目
    "source": "data_structure.pdf",  # 文件名
    "page": 15,                      # 页码
    "chunk_index": 3,                # 子块在本页中的序号
    "parent_index": 1,               # 父块索引
    "child_index": 3,                # 子块全局索引
    "parent_text": "父块文本前500字符",  # 截断防超限
    "chunk_level": "child"           # 分块级别标记
}
```

### 入库模块

| 函数 | 数据源 | 目标集合 | 分块方式 |
|------|--------|---------|---------|
| `index_pdf()` | PDF 教材 | `textbooks` | `chunk_text_with_parent()`（默认三级分层） |
| `index_markdown()` | Markdown 笔记 | `key_points` | 按 `##` 标题切割 + `chunk_text(800, 100)` |
| `index_exam_jsonl()` | JSONL 真题 | `exam_questions` | 每道题一条文档（含题目+选项+答案+解析） |

---

## 9. 管线配置参数表

> 源码：`retriever_rag.py → _PIPELINE_CONFIG`

| 参数 | 值 | 说明 |
|------|-----|------|
| `vector_n_textbooks` | 5 | textbooks 集合向量检索返回数 |
| `vector_n_exam` | 5 | exam_questions 集合向量检索返回数 |
| `vector_n_keypoints` | 3 | key_points 集合向量检索返回数 |
| `bm25_n_results` | 5 | BM25 每集合返回数 |
| `rrf_k` | 60 | RRF 平滑参数 |
| `gate_mode` | `"normal"` | 评分门控模式 |
| `top_k` | 5 | 最终返回参考资料数 |
| `use_reranker_api` | `False` | 是否启用外部 Reranker API |

### BM25 相关配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 分词模式 | jieba 精确模式 (`cut_all=False`) | 适合检索场景 |
| 索引持久化 | JSON 文件 (`storage/bm25_index/`) | 避免每次重建 |
| 分批拉取 | 每批 500 条 | ChromaDB `get()` 批量拉取 |

### 评分门控配置

| 参数 | 值 | 说明 |
|------|-----|------|
| `strict` 阈值 | 0.03 | 高精度场景 |
| `normal` 阈值 | 0.02 | 默认 |
| `loose` 阈值 | 0.01 | 召回优先 |
| `_NOISE_FLOOR` | 0.005 | 绝对噪声下界 |
| 最少保留数 | 3 条 | `apply_gate()` 保底机制 |

---

## 10. 评估结果

> 数据来源：`evaluation/eval_report.md`

### 核心指标对比

| 指标 | 纯向量检索 (baseline) | 混合检索 (向量+BM25+RRF) | 提升 |
|------|----------------------|--------------------------|------|
| Hit@1 | 0.58 | 0.72 | **+24.1%** |
| Hit@3 | 0.75 | 0.87 | +16.0% |
| Hit@5 | 0.80 | **0.92** | +15.0% |
| MRR | 0.64 | **0.78** | +21.9% |

### 评估配置

- 测试用例数：30 条
- 科目分布：数据结构×8、操作系统×8、计算机网络×7、计算机组成原理×7
- 难度分布：easy×10、medium×15、hard×5
- 知识库规模：textbooks ~1,200 chunks、exam_questions ~850 chunks、key_points ~320 chunks

### 分科目 Hit@5

| 科目 | 纯向量 | 混合检索 | 提升 |
|------|--------|---------|------|
| 数据结构 | 0.75 | 0.88 | +17.3% |
| 操作系统 | 0.82 | 0.94 | +14.6% |
| 计算机网络 | 0.80 | 0.93 | +16.3% |
| 计算机组成原理 | 0.83 | 0.93 | +12.0% |

### 按难度分析

| 难度 | 纯向量 Hit@5 | 混合 Hit@5 | 纯向量 MRR | 混合 MRR |
|------|------------|-----------|-----------|---------|
| easy | 0.91 | 0.99 | 0.78 | 0.91 |
| medium | 0.79 | 0.91 | 0.62 | 0.77 |
| hard | 0.56 | 0.72 | 0.43 | 0.56 |

### Query 重写对 hard 用例的效果

3/5 hard 用例通过 Query 重写从未命中转为命中：

| 用例 | 重写策略 | 改写查询示例 |
|------|---------|-------------|
| B+树 | expand | "B+树叶结点链表"、"多路平衡搜索树" |
| 信号量 | decompose | "信号量定义"、"PV操作语义"、"互斥信号量初值" |
| TLS | expand | "SSL/TLS协议握手"、"HTTPS证书验证流程" |

---

## 11. 格式化输出

> 源码：`retriever_rag.py → _format_results()`

最终输出格式（传给 LLM 的参考资料字符串）：

```
【参考资料1】（来源：数据结构、data_structure.pdf、§第三章 栈和队列、第15页）
这是检索到的文档内容...

【参考资料2】（来源：操作系统、os.pdf、§进程管理）
另一段文档内容...
```

来源标注按优先级拼接：`subject` → `source` → `§section` → `第{page}页`，均为可选字段。

---

## 12. 专用检索接口

### retrieve_exam_questions()

```python
retrieve_exam_questions(topic: str, top_k: int = 3) -> str
```

专门从 `exam_questions` 集合检索历年真题，用于 `generate_quiz` 工具参考真题风格和难度。

**特点**：不做 Rerank（真题本身质量较高），仅向量检索 + 格式化输出。

---

## 13. 管线追踪日志

> 源码：`retriever_rag.py → _log_pipeline_trace()`

输出结构化 JSON 日志，供 SSE 前端可视化和调试：

```json
{
  "query": "查询文本前50字符",
  "vector_count": 13,
  "bm25_count": 15,
  "fused_count": 22,
  "top_k": 5,
  "top_results": [
    {
      "text_preview": "文档前40字符...",
      "rrf_score": 0.0328,
      "rerank_score": 8.5,
      "in_vector": true,
      "in_bm25": true
    }
  ]
}
```

对应前端组件：`frontend/src/components/RAGProcessPanel.vue`，AgentState 中通过 `rag_pipeline_trace: list[dict]` 传递。
