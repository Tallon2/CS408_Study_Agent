# AI Agent 开发工程师面试完全备战手册

> 基于「408 考研 AI 学习教练」项目的深度面试准备文档
> 生成日期：2026-04-20

---

## 目录

1. [项目自我介绍话术](#1-项目自我介绍话术)
2. [项目全景概览](#2-项目全景概览)
3. [核心技术模块深度问答](#3-核心技术模块深度问答)
   - 3.1 LangGraph 状态图编排
   - 3.2 RAG 混合检索管线
   - 3.3 四层记忆系统 L1-L4
   - 3.4 FastAPI 后端服务
   - 3.5 Vue3 前端工程
   - 3.6 SSE 流式架构
4. [系统设计类问题](#4-系统设计类问题)
5. [技术选型决策答辩](#5-技术选型决策答辩)
6. [项目难点与解决方案](#6-项目难点与解决方案)
7. [量化指标速查表](#7-量化指标速查表)
8. [行为面试 STAR 故事库](#8-行为面试-star-故事库)
9. [高频追问与应对策略](#9-高频追问与应对策略)
10. [反问面试官清单](#10-反问面试官清单)

---

## 1. 项目自我介绍话术

### 30 秒电梯推介

> 这是一个面向 408 考研群体的个性化学习 AI Agent，历经四周系统性构建。技术上，我从零搭建了混合 RAG 检索引擎（向量 + BM25 + RRF 融合），用 LangGraph 编排多分支意图路由状态图，设计了 L1-L4 四层分级记忆系统实现跨会话个性化，并以 FastAPI + Vue3 完成全栈服务化。系统在 30 条标注数据上 Hit@5 从 0.80 提升至 0.92，最终构建产出 3488 个前端模块，具备完整的用户认证、SSE 流式对话、RAG 管线可视化等生产级能力。

### 1 分钟展开版

> 这个项目分四个阶段迭代：
>
> **第一周 — RAG 引擎**：从纯向量检索升级为向量+BM25 双路检索 + RRF 融合，加入三档评分门控、三级 Reranker 降级链、Query 重写三策略（expand/decompose/HyDE），Hit@5 从 0.80 提升至 0.92。
>
> **第二周 — Agent 编排**：用 LangGraph 构建 StateGraph，AgentState 包含 11 个字段，通过 intent_router 节点实现四路意图分支（study/plan/review/unknown），每条分支走不同的节点链路，支持同步和 astream 流式两种调用模式。
>
> **第三周 — 后端服务**：FastAPI 实现 13 个 REST 接口 + 5 张 ORM 表 + JWT 认证，SSE 流式推送覆盖 5 种事件类型，三级依赖注入链（get_db → get_current_user → get_agent）。
>
> **第四周 — 前端工程**：Vue3 + TypeScript + Vite 构建，SSE 客户端用 fetch + ReadableStream 实现（非 EventSource，因为需要 POST + JWT），RAGProcessPanel 组件实时可视化 4 步管线状态。

### 核心亮点提炼（按稀缺度排序，面试主动提及）

| 排名 | 亮点 | 稀缺度 |
|:----:|------|:------:|
| 1 | 四层分层记忆系统（L1-L4）自主设计 | ★★★★★ |
| 2 | 混合检索 RAG 管线（向量+BM25+RRF+门控+Reranker） | ★★★★★ |
| 3 | LangGraph 多分支状态图编排 | ★★★★★ |
| 4 | 三级滑动窗口分块 + Auto-merging | ★★★★☆ |
| 5 | QueryRewriter 三策略（expand/decompose/HyDE） | ★★★★☆ |
| 6 | SSE 流式架构端到端打通 | ★★★★☆ |
| 7 | FastAPI 全栈服务化（13接口+JWT+DI） | ★★★☆☆ |
| 8 | 双轨制工具适配层（lc_tools + execute_tool） | ★★★☆☆ |
| 9 | RAG 评估体系（30标注+Hit@K+MRR） | ★★★☆☆ |
| 10 | Vue3 RAGProcessPanel 管线可视化 | ★★★☆☆ |

---

## 2. 项目全景概览

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端层 (Port 3000)                            │
│    Vue3 + Ant Design + Vite + Pinia + SSE 实时流                    │
│    views: Chat.vue / Login.vue / Plan.vue                          │
│    components: ChatBubble.vue / RAGProcessPanel.vue                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API 层 (Port 8000)                           │
│    server.py → uvicorn                                             │
│    路由: /api/v1/auth  /api/v1/chat  /api/v1/plan                  │
│    中间件: CORS / JWT 认证                                          │
│    数据库: dao/ (SQLite + SQLAlchemy)                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Agent 编排层 (LangGraph)                          │
│  START → [intent_router] ──条件路由──┬─ study  → rag → tool → resp │
│                                      ├─ plan   → tool → resp       │
│                                      ├─ review → rag → resp        │
│                                      └─ unknown→ resp              │
│                          所有分支 → [memory_update] → END           │
└──────────────┬───────────────────────────────┬──────────────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────────────┐
│    RAG 检索层             │   │         记忆层 (L1-L4)               │
│  Query重写(3策略)        │   │  L1 会话: journal.jsonl (append-only)│
│  向量检索(ChromaDB)      │   │  L2 任务: task_state.json            │
│  BM25稀疏检索(jieba)     │   │  L3 知识: LLM提炼 patterns/pitfalls │
│  RRF融合(k=60)           │   │  L4 画像: profile.json (知识图谱)   │
│  Reranker三级降级        │   │                                      │
│  评分门控(3档)           │   │  注入: build_memory_context()        │
│  Auto-merging            │   │  钩子: on_session_stop()             │
└──────────────────────────┘   └──────────────────────────────────────┘
```

### 2.2 技术栈全景

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | Vue 3 + TypeScript + Vite | 8.x |
| UI 组件 | Ant Design Vue | 4.x |
| 状态管理 | Pinia | 2.1 |
| 后端框架 | FastAPI + Uvicorn | 0.115+ |
| ORM | SQLAlchemy | 2.0+ |
| 认证 | python-jose (JWT HS256) | — |
| Agent 编排 | LangGraph (StateGraph) | 0.2+ |
| LLM | 智谱 GLM-4-Flash | — |
| Embedding | 智谱 embedding-3 (1024维) | — |
| 向量数据库 | ChromaDB | 0.5+ |
| 稀疏检索 | rank-bm25 + jieba | 0.2.2 |
| 缓存 | Redis 7 Alpine | — |
| 部署 | Docker Compose | 3.8 |

### 2.3 项目规模速览

| 指标 | 数值 |
|------|------|
| Python 后端文件 | ~35 个 |
| 前端 Vue/TS 文件 | ~17 个 |
| REST API 接口 | 13 个 |
| ORM 数据表 | 5 张（核心）+ 5 张（扩展） |
| LangGraph 图节点 | 5 个 |
| Agent 工具 | 7 个 |
| RAG 管线步骤 | 6 步 |
| 评测用例 | 30 条 |
| 前端构建模块 | 3488 个 |
| 构建耗时 | 767ms |

---

## 3. 核心技术模块深度问答

### 3.1 LangGraph 状态图编排

**Q1：为什么选择 LangGraph 而不是 LangChain AgentExecutor？**

> LangChain AgentExecutor 是一个黑盒 ReAct 循环，难以在中间插入自定义节点（如记忆更新、RAG 检索）。我的场景需要四路意图分支，每条分支走不同的处理链路，这本质上是一个**有向无环图**而非线性链。LangGraph 的 StateGraph 提供了显式的节点定义和条件边（conditional edges），可以精确控制数据流向，同时支持 `stream_mode="values"` 逐节点推送状态，非常适合做 SSE 流式输出。

**Q2：AgentState 是怎么设计的？为什么用 TypedDict 而不是 Pydantic？**

> AgentState 包含 11 个字段：`messages`（对话历史，使用 `add_messages` Reducer 实现不可变追加）、`intent`（意图分类结果）、`rag_context`（检索上下文）、`tool_name/tool_args/tool_result`（工具调用三元组）、`memory_l2/memory_l4`（记忆快照）、`session_events`（L1事件缓冲）、`final_response`（最终回复）、`rag_pipeline_trace`（管线追踪）。
>
> 用 TypedDict 是因为 LangGraph 的 State 需要支持 Reducer 注解（如 `Annotated[list, add_messages]`），Pydantic BaseModel 的字段赋值语义和 LangGraph 的 channel 合并机制不兼容。TypedDict 更轻量，且与 LangGraph 的设计哲学一致。

**Q3：意图路由是怎么实现的？纯 LLM 分类还是有规则兜底？**

> 双层决策。首先用 LLM 语义分类（Prompt 要求输出 study/plan/review/unknown 之一），然后有一个**关键词覆盖映射表**做精确兜底。比如用户输入包含"制定计划""安排学习"等关键词时，直接映射到 plan 意图，避免 LLM 偶尔分类错误。这种"LLM 分类 + 规则兜底"的双层设计在工业实践中很常见。

**Q4：图的路由逻辑是怎样的？有几层条件边？**

> 两层条件边：
> 1. `route_by_intent()`：根据 intent 字段四路分支 → study 走 rag_node，plan 走 tool_executor，review 走 rag_node，unknown 直接走 response_generator
> 2. `route_after_rag()`：RAG 节点执行后的二级路由 → study 意图继续走 tool_executor，review 意图直接走 response_generator
>
> 所有分支最终汇聚到 `response_generator → memory_update → END`。

**Q5：如何实现流式输出？stream_mode 的选择？**

> 使用 `graph.astream(state, stream_mode="values")`，每个节点执行完毕后推送完整的 AgentState 快照。在 FastAPI 侧比较前后两次快照的 diff，提取新增的 `final_response`、`intent`、`rag_pipeline_trace` 等字段，包装为 SSE 事件推送给前端。选择 `values` 模式而非 `updates` 是因为前端需要完整的上下文（如显示意图分类结果时需要知道当前完整状态）。

---

### 3.2 RAG 混合检索管线

**Q1：你的 RAG 管线有几步？每步做什么？**

> 六步管线：
> 1. **双路检索**：ChromaDB 向量检索（3个集合：textbooks/exam_questions/key_points）+ BM25 稀疏检索（jieba 分词），共产出约 28 条候选
> 2. **RRF 融合**：Reciprocal Rank Fusion（k=60），公式 `score(d) = Σ 1/(k + rank_i)`，双路命中的文档分数叠加，按 `text[:100]` 指纹去重
> 3. **评分门控**：三档阈值（strict=0.03, normal=0.02, loose=0.01），未通过则触发 Query 重写二次检索
> 4. **Reranker 精排**：三级降级链（Jina API → SiliconFlow API → LLM Rerank → 保持原序）
> 5. **Auto-merging**：命中的 600 字符子块替换为 2000 字符父块，按 `(source, page, parent_index)` 去重
> 6. **格式化输出**：带来源标注的参考资料文本

**Q2：为什么要做向量+BM25 混合检索？纯向量不够吗？**

> 408 考研有大量精确术语（如"KMP""B+树""partition"），纯向量语义检索对这类精确词匹配能力不足。BM25 基于词频匹配，对专有名词精确匹配能力强。RRF 融合后 Hit@5 从 0.80 提升至 0.92（+15%），Hit@1 从 0.58 提升至 0.72（+24.1%）。两种检索方式优势互补：向量擅长语义相似，BM25 擅长关键词精确匹配。

**Q3：RRF 的 k=60 是怎么来的？换成其他值会怎样？**

> k=60 是 RRF 原始论文（Cormack et al., 2009）推荐的默认值。k 的作用是平滑排名差异：k 越大，高排名和低排名文档的分数差距越小；k 越小，分数越集中在 top 结果。60 是一个经验最优值，在大多数 IR 基准上表现稳定。我没有在自己的数据集上做 k 的网格搜索，但论文结论对 k 值不太敏感（50-70 范围内差异很小）。

**Q4：评分门控的三档阈值是怎么确定的？**

> 基于 RRF 分数的数学含义推导。单路第 1 名的 RRF 分数 = 1/(60+1) ≈ 0.0164，双路命中第 1 名 ≈ 0.0328。`normal` 阈值 0.02 意味着至少有一条文档在某路检索中排名前几，是一个合理的"有用结果"下界。`strict` 0.03 要求接近双路命中，`loose` 0.01 接受边缘相关。还有一个绝对噪声下界 `_NOISE_FLOOR = 0.005`，低于此视为噪声直接过滤。

**Q5：Reranker 为什么设计三级降级链？**

> 可靠性优先。外部 Cross-Encoder API（Jina/SiliconFlow）精排效果最佳，但可能因网络超时、限额耗尽等原因不可用。LLM Rerank 用 GLM 对每个候选打 0-10 相关性分，质量仍优于 RRF 原排序。最差情况保持 RRF 原排序，确保系统**始终可用**。这是一种"优雅降级"设计模式，在生产环境中非常重要。

**Q6：三级分块是怎么设计的？Auto-merging 解决什么问题？**

> 三级分块：L1 父块 2000 字符（重叠 200）、L2 子块 600 字符（重叠 80）、L3 句子块 150 字符（重叠 20）。检索时用 600 字符子块做向量匹配（粒度适中，精度最佳），命中后 Auto-merging 替换为 2000 字符父块返回给 LLM（上下文更完整）。这解决了 RAG 中经典的"检索精度 vs 上下文完整性"矛盾。父块归属算法是计算子块中心点位置，取最后一个 `start <= center` 的父块。

**Q7：Query 重写的三种策略分别什么时候用？**

> - **expand**（默认）：生成 N 个语义等价改写，提升召回率。比如"B+树"→"B+树叶结点链表""多路平衡搜索树"
> - **decompose**：将复合查询分解为 2-5 个子问题，适合 AND 型查询。比如"信号量的定义和PV操作"→"信号量定义""PV操作语义""互斥信号量初值"
> - **HyDE**：生成 150-250 字假设性答案文档，用答案向量去检索，适合知识型问答（因为答案和文档的语义空间更接近）

**Q8：你的 RAG 效果如何量化评估？**

> 30 条标注数据集，覆盖四科（数据结构×8、操作系统×8、计算机网络×7、组成原理×7），三档难度（easy×10、medium×15、hard×5）。评估指标：Hit@1=0.72（+24.1%）、Hit@3=0.87（+16%）、Hit@5=0.92（+15%）、MRR=0.78（+21.9%）。其中 3/5 hard 用例通过 Query 重写从未命中转为命中。

---

### 3.3 四层记忆系统 L1-L4

**Q1：为什么设计四层？每层的职责和生命周期？**

> 模拟人类记忆的短期/长期分层：
>
> | 层级 | 职责 | 存储 | 生命周期 | 触发时机 |
> |------|------|------|---------|---------|
> | L1 会话 | append-only 事件日志 | journal.jsonl | 单次会话 | 每条消息 |
> | L2 任务 | 薄弱点、纠偏、下一步建议 | task_state.json | 跨会话累积 | 会话结束 |
> | L3 知识 | LLM 提炼学习模式/踩坑记录 | patterns/*.md | 长期 | 每5次会话 |
> | L4 画像 | 知识图谱+学习偏好 | profile.json | 长期 | 每次会话结束 |
>
> 这样设计的好处：L1 保证不丢失任何信息（审计轨迹），L2 实现任务连续性（"上次你学到哪了"），L3 构建可复用知识（不重复犯错），L4 实现个性化（适配学习风格）。

**Q2：on_session_stop 钩子做了什么？**

> 会话结束时触发五步管线：
> 1. LLM 生成会话摘要 digest（包含 summary、topics_learned、mastered、struggled、corrections、next_recommendation）
> 2. 更新 L2 任务状态（session_count++、累积 blockers、移除已掌握项）
> 3. 更新 L4 用户画像（知识图谱状态更新，每3次触发偏好提炼）
> 4. 摘要写入向量索引（供后续语义检索历史记录）
> 5. 条件触发 L3 知识提炼（每5次会话，收集最近5个digest，LLM提炼patterns/pitfalls）

**Q3：L4 知识图谱的三种状态是什么？怎么流转？**

> - `introduced`：首次接触但未评估掌握程度
> - `struggling`：标记为薄弱，累计 attempts 次数
> - `mastered`：已掌握
>
> 流转：新知识点 → introduced → 如果出现在 digest.struggled → struggling（attempts++）→ 如果出现在 digest.mastered → mastered。已掌握的知识点从 L2 的 blockers 列表中移除。

**Q4：记忆是怎么注入给 LLM 的？**

> `build_memory_context()` 函数将 L2-L4 记忆拼接为结构化 Markdown 文本，注入系统提示。包含四部分：当前任务状态（L2）、用户知识状态（L4知识图谱）、用户偏好（L4偏好）、相关历史记录（向量语义检索 session_digests 集合）。这样 LLM 在生成回复时可以参考用户的学习进度和风格偏好。

**Q5：L2 的更新逻辑为什么不用 LLM？**

> L2 采用确定性逻辑（if-else），不依赖 LLM。原因是：任务状态更新需要**可预测、可调试**。如果用 LLM 做状态更新，可能出现幻觉（错误地移除blockers或添加不存在的知识点），且无法保证幂等性。确定性逻辑 + JSON 快照的组合便于debug和回滚。

---

### 3.4 FastAPI 后端服务

**Q1：后端接口设计有哪些？怎么组织的？**

> 13 个 REST 接口分三组：
> - **认证组** `/api/v1/auth`：POST register、POST login、GET me
> - **对话组** `/api/v1/chat`：POST stream（SSE）、POST sync、GET history、DELETE session
> - **计划组** `/api/v1/plan`：GET list、POST create、GET detail、DELETE plan、POST tasks、PATCH done
>
> 路由层通过 FastAPI 的 `APIRouter` 模块化组织，统一挂载到 `server.py` 入口。

**Q2：依赖注入链是怎么设计的？**

> 三级链式注入：
> 1. `get_db()` → 生成 SQLAlchemy 会话，请求结束自动关闭
> 2. `get_current_user(token, db)` → 解析 JWT Bearer Token，查询数据库验证用户
> 3. `get_agent(user)` → 按用户维度缓存 LangGraphAgent 实例（单例模式，避免重复初始化图）
>
> 每个接口只需声明依赖即可自动注入，体现了 IoC（控制反转）思想。

**Q3：JWT 认证方案的关键细节？**

> - 算法：HS256（对称加密，适合单服务部署）
> - 有效期：7 天
> - Payload：`{"sub": user_id, "exp": expire_time}`
> - 密码存储：bcrypt 哈希（passlib 库）
> - Token 传递：Authorization: Bearer {token}
> - 401 处理：前端 Axios 拦截器捕获 401，自动清除本地 token 并跳转登录页

**Q4：数据库设计有几张核心表？**

> 5 张核心表：
> - `users`：用户认证信息（username, email, hashed_password）
> - `chat_sessions`：会话记录（user_id, started_at, ended_at, summary）
> - `chat_messages`：消息记录（session_id, role, content, intent）
> - `study_plans`：学习计划（user_id, title, is_active）
> - `study_tasks`：学习任务（plan_id, title, subject, is_done, due_date）

---

### 3.5 Vue3 前端工程

**Q1：前端架构是怎样的？**

> 标准 Vue3 SPA 架构：Vite 8 构建 + Composition API + TypeScript + Pinia 状态管理 + Vue Router 路由守卫。三个页面（Login/Chat/Plan），两个核心组件（ChatBubble/RAGProcessPanel），两个 Pinia store（auth/chat），工具层封装 HTTP 拦截器和 SSE 客户端。

**Q2：为什么 SSE 不用原生 EventSource？**

> EventSource API 有三个致命限制：
> 1. **只支持 GET 请求**：我们的 `/chat/stream` 需要 POST body 发送消息
> 2. **无法自定义 Header**：无法携带 JWT Authorization 头
> 3. **无法控制重连策略**：自动重连可能导致重复消息
>
> 因此自研了基于 `fetch + ReadableStream + TextDecoder` 的 SSE 客户端，支持 POST + JWT + 手动流控制。

**Q3：RAGProcessPanel 是怎么实现实时可视化的？**

> 4 步状态机（intent → rag → tool → llm_generation），每步三种状态（waiting → active → done）。后端通过 SSE 的 `event: pipeline` 推送 stage 信息，前端通过 `onPipeline` 回调将事件 push 到 `pipelineEvents` 数组，computed 属性根据事件计算每步当前状态，active 状态展示脉冲动画（CSS @keyframes pulse）。

**Q4：Pinia 双 Store 怎么设计的？**

> - `auth store`：管理 token（localStorage 持久化）、用户信息、login/logout actions
> - `chat store`：管理 messages 数组、streaming 状态、pipelineEvents、sendMessage action（内部调用 SSE 客户端并通过回调更新状态）

---

### 3.6 SSE 流式架构

**Q1：SSE 端到端的数据流是怎样的？**

> ```
> LangGraph graph.astream() → 逐节点推送 AgentState
>     ↓
> FastAPI event_generator() → 解析 state diff → yield SSE events
>     ↓ (HTTP chunked transfer)
> 前端 fetch + ReadableStream → TextDecoder 逐行解析
>     ↓
> onStart/onPipeline/onToken/onDone/onError 回调分发
>     ↓
> Pinia store 更新 → Vue 响应式渲染
> ```

**Q2：SSE 有几种事件类型？**

> 5 种：
> - `start`：对话开始（前端清空旧状态）
> - `pipeline`：管线阶段推进（intent/rag/tool/llm_generation）
> - `token`：增量文本 token（实时渲染）
> - `done`：完整回复（前端 streaming=false）
> - `error`：错误信息

**Q3：SSE vs WebSocket，为什么选 SSE？**

> - SSE 是**单向推送**（服务器→客户端），正好匹配"LLM 流式生成"场景
> - 基于 HTTP/1.1 长连接，无需协议升级，CDN/代理友好
> - 自带重连和 event-id 机制
> - WebSocket 是双向通道，对于"用户发一条消息，服务端流式回复"场景过于重量级
> - 但如果未来需要实时协同编辑或多用户聊天室，会考虑 WebSocket

---

## 4. 系统设计类问题

**Q1：如果用户量扩大到 10 万，这个系统需要怎么改造？**

> 1. **数据库**：SQLite → PostgreSQL（支持并发连接池）
> 2. **Agent 缓存**：per-user 单例 → Redis 缓存 + 按需加载（减少内存占用）
> 3. **RAG 检索**：ChromaDB → Milvus/Qdrant（分布式向量数据库，支持横向扩展）
> 4. **API 网关**：增加 Nginx/Kong 做限流、负载均衡
> 5. **异步任务**：on_session_stop 中的 LLM 调用改为 Celery 异步任务（不阻塞响应）
> 6. **水平扩展**：FastAPI 无状态化（Agent 状态存 Redis），多实例部署

**Q2：如果 LLM API 延迟很高（3-5秒），你怎么优化用户体验？**

> 1. **SSE 流式**：已实现，逐 token 推送，首 token 延迟 < 1s
> 2. **RAG 管线可视化**：让用户看到"正在检索知识库""正在分析意图"等中间状态，减少等待焦虑
> 3. **并行化**：BM25 和向量检索可以并行执行（目前是顺序的，可用 asyncio.gather 优化）
> 4. **缓存**：对高频问题缓存 RAG 结果（Redis TTL 缓存）
> 5. **预测性加载**：用户打字时预先执行意图分类（debounce 300ms）

**Q3：RAG 的知识库如何更新？新增教材怎么办？**

> 1. 运行 `scripts/index_textbooks.py` 处理新 PDF → ChromaDB 入库
> 2. 运行 `scripts/build_bm25_index.py` 重建 BM25 索引
> 3. 增量模式：ChromaDB 支持 upsert，同 ID 文档会更新
> 4. 版本控制：通过 metadata 中的 source 字段标记文档来源，可按版本过滤
> 5. 未来考虑：增量索引管道 + 文档变更检测（hash 对比）

**Q4：如何保证 Agent 的回答质量？有没有防幻觉机制？**

> 1. **RAG Grounding**：所有回答必须基于检索到的参考资料，prompt 中明确要求"基于以下参考资料回答"
> 2. **来源标注**：每条参考资料标注出处（科目、文件、章节、页码），用户可验证
> 3. **评分门控**：检索质量不达标时触发 Query 重写，而非硬用低质量上下文
> 4. **记忆注入**：纠偏记录（L2 corrections）提醒 LLM 不重复之前的错误
> 5. **工具化**：核心操作（出题、检查答案）通过 Tool 调用，结构化输出减少随机性

---

## 5. 技术选型决策答辩

| 技术组件 | 选型 | 为什么选它 | 备选方案及弃选理由 |
|----------|------|-----------|-------------------|
| 向量数据库 | ChromaDB | 本地零依赖、Python 原生、支持持久化 | Pinecone（云端收费）、Milvus（运维重）、FAISS（无元数据过滤） |
| 稀疏检索 | BM25+jieba | 对专有名词精确匹配强 | Elasticsearch（运维重）、TF-IDF（无词频饱和度） |
| 融合算法 | RRF(k=60) | 无需调权重、论文验证稳定 | 加权平均（量纲不一）、CombSUM（对异常敏感） |
| Agent 编排 | LangGraph | 显式状态图、条件路由、支持流式 | AgentExecutor（黑盒）、自研状态机（造轮子） |
| 后端框架 | FastAPI | 原生异步、自动文档、SSE 支持好 | Flask（同步）、Django（过重） |
| ORM | SQLAlchemy | 生态成熟、SQLite→PG 无缝迁移 | Tortoise（生态小）、原生 SQL（维护难） |
| 前端 | Vue3+Vite | 组合式 API、构建极快(767ms) | React（非团队偏好）、Nuxt（SSR 过重） |
| 状态管理 | Pinia | Vue3 官方推荐、TS 友好 | Vuex4（模板代码多） |
| JWT 库 | python-jose | FastAPI 推荐、API 简洁 | PyJWT（功能近似）、session-based（有状态扩展难） |
| 记忆存储 | JSONL/JSON | 轻量、append-only 天然适合日志、人类可读 | Redis（多一个依赖）、SQLite（灵活性差） |

---

## 6. 项目难点与解决方案

### 难点 1：RAG 检索精度 vs 上下文完整性矛盾

**问题**：小 chunk（200字符）向量匹配精准但上下文不完整，大 chunk（2000字符）上下文好但向量匹配不准。

**解决**：三级分块 + Auto-merging。用 600 字符子块做向量检索（精度最佳甜蜜点），命中后自动替换为 2000 字符父块传给 LLM。通过 parent_index metadata 关联父子块。

---

### 难点 2：LangGraph 流式输出与 SSE 事件映射

**问题**：LangGraph 的 astream 推送的是完整 state 快照，但前端需要区分不同类型的事件（意图分类、RAG进度、token增量等）。

**解决**：在 FastAPI 的 event_generator 中维护上一次 state 快照的引用，每次新快照到来时做 diff，根据变化的字段生成不同类型的 SSE 事件。例如 `intent` 字段变化 → 发送 `pipeline:intent` 事件，`final_response` 增量 → 发送 `token` 事件。

---

### 难点 3：BM25 中文分词质量

**问题**：jieba 默认词典对 408 领域术语覆盖不足（如"页表""进程控制块"可能被错误切分）。

**解决**：使用 jieba 精确模式（`cut_all=False`），减少过度切分。同时 BM25 天然对多 token 查询有容错（即使切分不完美，部分 token 命中也能给出合理排名）。

---

### 难点 4：bcrypt 兼容性问题

**问题**：bcrypt 4.x 版本与 passlib 存在不兼容（`__about__` 属性被移除导致 import 报错）。

**解决**：锁定 bcrypt 版本 + 使用 passlib 的 `CryptContext` 做适配层，确保哈希验证正常工作。

---

### 难点 5：EventSource 不支持 POST + JWT

**问题**：浏览器原生 EventSource API 只支持 GET 请求，无法发送 POST body 和自定义 Header。

**解决**：自研 SSE 客户端，基于 `fetch API + ReadableStream + TextDecoder`，手动解析 `event:` 和 `data:` 行，通过回调机制分发事件。代码量仅 84 行（`utils/sse.ts`）。

---

## 7. 量化指标速查表

| 指标 | 数值 | 对比基线 | 提升 |
|------|------|---------|------|
| Hit@1 | 0.72 | 0.58 | +24.1% |
| Hit@3 | 0.87 | 0.75 | +16.0% |
| Hit@5 | **0.92** | 0.80 | +15.0% |
| MRR | **0.78** | 0.64 | +21.9% |
| 前端构建模块数 | 3488 | — | — |
| 前端构建耗时 | 767ms | — | — |
| API 接口数 | 13 | — | — |
| ORM 表数 | 10 | — | — |
| LangGraph 节点数 | 5 | — | — |
| Agent 工具数 | 7 | — | — |
| 评测用例数 | 30 | — | — |
| 知识库规模（chunks） | ~2370 | — | — |
| 全部 API 测试通过 | 12/12 | — | — |

---

## 8. 行为面试 STAR 故事库

### Story 1：RAG 检索精度提升（技术攻坚）

- **S(情境)**：初版纯向量检索 Hit@5 只有 0.80，对精确术语检索不佳
- **T(任务)**：需要在不增加大量标注数据的情况下提升检索质量
- **A(行动)**：
  1. 分析 bad case 发现术语匹配问题 → 引入 BM25 补充
  2. 研究 RRF 论文 → 实现融合算法
  3. 发现部分查询完全无结果 → 设计评分门控 + Query 重写
  4. 引入 Reranker 精排 → 设计三级降级链保证可靠性
- **R(结果)**：Hit@5 提升至 0.92，Hard 用例 3/5 从未命中变为命中

### Story 2：四层记忆系统设计（系统设计）

- **S**：用户反馈每次对话都要"重新介绍自己"，没有连续性
- **T**：设计一个跨会话的个性化记忆系统
- **A**：
  1. 调研 MemGPT、Generative Agents 等论文
  2. 设计 L1-L4 分层架构，各层职责明确
  3. 实现 on_session_stop 钩子自动化更新
  4. build_memory_context 注入机制，透明集成到 Agent
- **R**：系统能记住用户的薄弱点、学习偏好、历史进度，实现"上次我们学到了死锁检测"的连续性

### Story 3：SSE 端到端打通（全栈联调）

- **S**：需要实现类 ChatGPT 的流式打字效果，但 EventSource 不支持 POST
- **T**：从 LangGraph astream 到前端渲染的完整流式链路
- **A**：
  1. 调研发现 EventSource 限制 → 自研 fetch+ReadableStream 客户端
  2. 设计 5 种 SSE 事件类型 → 覆盖管线进度+token流
  3. FastAPI side 做 state diff → 精确映射事件
  4. 前端 RAGProcessPanel 状态机 → 实时可视化
- **R**：首 token 延迟 < 1s，管线可视化让用户看到 Agent"思考过程"，提升信任感

---

## 9. 高频追问与应对策略

### "这个项目有多少是你自己写的？"

> 100% 自主编码。四周迭代，从第一行代码开始构建。技术选型、架构设计、编码实现、测试评估全部独立完成。可以现场打开任何模块的代码讲解实现细节。

### "如果让你重新做一次，会有什么不同？"

> 1. **测试覆盖**：会从第一周就引入 pytest 单元测试，目前测试主要是集成级别
> 2. **配置中心化**：RRF k 值、门控阈值等参数分散在代码中，应该抽到统一配置文件
> 3. **日志框架**：引入 structlog 做结构化日志，而非手动 print/dict 构造
> 4. **向量数据库**：如果预期用户量大，从一开始选 Qdrant 而非 ChromaDB

### "这个项目有什么局限性？"

> 1. **单用户优化**：当前记忆系统和 Agent 缓存是 per-user 单例，多用户并发场景需要改造
> 2. **知识库规模**：~2370 chunks，覆盖不完整，实际上线需要更多教材和真题
> 3. **评估规模**：30 条测试用例偏少，更严谨需要 100+ 条标注
> 4. **LLM 依赖**：意图分类、记忆提炼、Query 重写等都依赖 LLM，离线场景不可用

### "LangGraph 和 LangChain 的关系？"

> LangGraph 是 LangChain 团队开发的子项目，专门用于构建有状态的 Agent 工作流。LangChain 提供 LLM 调用、工具定义等基础设施，LangGraph 在其之上提供图执行引擎。两者是互补关系：LangChain 管"怎么调 LLM"，LangGraph 管"按什么顺序调"。

### "HyDE 的原理是什么？"

> Hypothetical Document Embedding。核心想法：用户查询和文档之间存在"语义鸿沟"（query 通常很短且缺少上下文），但**答案和文档在语义空间中更接近**。所以先让 LLM 生成一个假设性答案（150-250字），再用这个答案的向量去检索，往往能找到更相关的文档。适合知识型问答场景。

### "你怎么看 Agent 和 RAG 的关系？"

> RAG 是 Agent 的一个**工具/能力模块**。Agent 负责"决定做什么"（意图路由、工具选择），RAG 负责"找到相关知识"。在我的系统中，RAG 是 Agent 图中的一个节点，只有 study/review 意图才会触发 RAG，plan 意图直接走工具执行。这种解耦设计让两者可以独立演进。

### "为什么不用 GPT-4/Claude？选智谱有什么考虑？"

> 1. **合规性**：国内部署，数据不出境
> 2. **成本**：GLM-4-Flash 价格远低于 GPT-4，适合高频调用场景（意图分类、Query 重写等辅助任务）
> 3. **延迟**：国内 API 延迟 < 国外 API
> 4. **可替换性**：通过 config.py 统一配置模型名称和 API key，切换模型只需改配置

---

## 10. 反问面试官清单

1. 贵团队目前的 Agent 技术栈是什么？用的是 LangGraph/AutoGen 还是自研框架？
2. RAG 系统上线后，你们的知识库更新频率和维护流程是怎样的？
3. 团队对 Agent 的评估体系是怎么建设的？有自动化 eval pipeline 吗？
4. 当前 LLM 选型是自部署还是 API 调用？有考虑 MoE 或小模型蒸馏吗？
5. Agent 的记忆/个性化方向，团队有在做长期记忆或 user profile 相关的工作吗？
6. 产品侧对"回答可靠性"的要求如何？有 human-in-the-loop 的机制吗？
7. 团队在 Agent 多步推理的可观测性方面做了哪些工作？（tracing, debugging）
8. 未来 3-6 个月，这个方向最大的技术挑战是什么？

---

---

## 11. 实战 Debug 案例集（本次开发真实记录）

> 以下是项目联调过程中遇到的真实 Bug，每个案例都可以作为面试中"你遇到过什么难排查的问题"的素材。

---

### 🐛 Bug 1：vue-router 版本与 Vite 8 ESM 不兼容 → 前端空白页

**现象**：`http://localhost:3000` 打开后一片空白，F12 控制台报错：
```
Uncaught ReferenceError: exports is not defined
    at vue-router.esm-bundler.js:2306:23
```

**根因**：`package.json` 中 `"vue-router": "^4.0.0"` 被 npm 解析到旧版（4.0.x）。该版本内部仍使用了 CommonJS 的 `exports` 对象，而 Vite 8 已升级为纯 ESM 模式，不再对 CJS 做自动 polyfill，导致运行时崩溃。

**修复**：
```json
// package.json
"vue-router": "^4.5.0"   // 4.5.0+ 完整支持 ESM
```
执行 `npm install vue-router@^4.5.0 --save` 重装。

**面试话术**：
> "前端空白，控制台报 `exports is not defined`，定位是 vue-router 旧版本用了 CJS 语法与 Vite 8 纯 ESM 不兼容。升级到 4.5.0+ 解决。教训：前端依赖版本不能用宽泛的 `^4.0.0`，应锁定到兼容 bundler 的最低版本。"

---

### 🐛 Bug 2：未登录时 API 拦截器与 Vue Router 守卫竞争 → 偶发白屏

**现象**：未登录状态访问 `/`，页面偶发白屏，有时闪一下再跳转登录页，有时直接空白。

**根因**：双重跳转竞争。
1. Vue Router `beforeEach` 守卫检测到未登录 → 调用 `router.push('/login')`（Vue 虚拟路由跳转）
2. `Chat.vue` 的 `onMounted` 中 `loadHistory()` 发了 `GET /api/v1/chat/history` → 返回 401 → Axios 拦截器执行 `window.location.href = '/login'`（强制整页刷新）

两个跳转几乎同时触发，`window.location.href` 打断了 Vue Router 的跳转过程，导致页面处于中间状态。

**修复**：
```typescript
// stores/chat.ts — 加 try-catch，401 时静默忽略
async function loadHistory() {
  try {
    const { data } = await http.get('/api/v1/chat/history')
    messages.value = data.messages ?? []
  } catch {
    messages.value = []  // 未登录时安静降级
  }
}

// utils/http.ts — 拦截器加去重判断
if (error.response?.status === 401) {
  localStorage.removeItem('access_token')
  if (window.location.pathname !== '/login') {
    window.location.replace('/login')  // replace 避免历史记录污染
  }
}
```

**面试话术**：
> "SPA 中 `window.location` 和 Vue Router 不能混用。`window.location.href` 是浏览器级跳转，会打断正在进行的 Vue Router 导航，导致组件处于半初始化状态。统一用 Router 实例跳转，或在拦截器里加路径判断避免重复触发。"

---

### 🐛 Bug 3：RRF 门控阈值 > 理论最大值 → 每次都"未通过"

**现象**：RAG 管线追踪面板每次都显示 `🚦 门控：未通过 阈值=0.02 / 最高=0.01639`，永远触发二次检索。

**根因**：数学上不可能通过。RRF(k=60) 的分数公式为 `1/(k + rank)`，单路第 1 名的理论最高分 = `1/(60+1) ≈ 0.01639`。门控阈值 `normal=0.020 > 0.0164`，**任何结果都不可能越过这个阈值**。

**修复**：
```python
# memory/rag/score_gate.py — 基于 RRF 值域重新校准
GATE_THRESHOLDS = {
    "strict": 0.014,  # 接近单路第 1 名
    "normal": 0.010,  # top-5 文档均可通过
    "loose":  0.006,  # 召回优先
}
```

**面试话术**：
> "配置数值类阈值前，必须先推导底层算法的值域。RRF 分数量纲和 cosine similarity 完全不同，不能套用 0.5/0.7 这种经验值。出了问题先打印实际分布，再反推合理阈值范围。"

---

### 🐛 Bug 4：BM25 索引从未建立 → 真题关键词检索始终 0 条

**现象**：RAG 追踪面板中 `📋 BM25: 0 条`，即使真题已通过向量方式成功入库（682 道题在 ChromaDB 中）。

**根因**：BM25 稀疏索引和 ChromaDB 向量索引是**完全独立的两套存储**，数据入库 ChromaDB 时不会自动同步到 BM25 的 `.pkl` 持久化文件。因为历史上数据是通过 `indexer.py` 直接入库向量库，从未调用过 `BM25Retriever.build_all()`，所以 BM25 索引文件一直是空的。

**修复**：
```bash
# 手动重建全量 BM25 索引（从 ChromaDB 读取所有文档）
python -c "from memory.rag.bm25_retriever import get_bm25_retriever; get_bm25_retriever().build_all()"
# 输出：textbooks=639, exam_questions=682, key_points=618，共 1939 条
```
长远修复：在 `indexer.py` 的入库流程最后，同步调用 `bm25_retriever.add_documents()`，保证两路索引始终同步。

**面试话术**：
> "混合检索系统中，向量索引和稀疏索引是两套独立的存储，写入时必须**同时维护两路**。这是混合检索最容易踩的坑——数据明明在向量库里，关键词检索就是查不到，根因是忘了同步 BM25。"

---

### 🐛 Bug 5：ChromaDB distance 值域误解（0~2 vs 0~1）→ 真题全部被过滤

**现象**：`generate_quiz` 工具始终走"无匹配真题"分支，LLM 一直在自己编题，从不展示原题。

**排查过程（三步定位）**：
1. 第一次猜测：以为是 `_query_collection(collection, query)` 参数顺序传反了 → 检查代码，参数顺序正确，此猜测错误
2. 第二次猜测：以为是 prompt 不够强力，LLM 没遵循指令 → 改了 temperature 和 prompt 结构，还是不行
3. **直接打印实际值**（终结猜测）：
```bash
python -c "from memory.rag.retriever_rag import _query_collection; \
  hits = _query_collection('exam_questions', '操作系统', n_results=5); \
  [print(f'dist={h[\"distance\"]:.4f} | {h[\"text\"][:40]}') for h in hits]"

# 输出：
# dist=0.9800 | [2013年第29题-操作系统-系统启动]
# dist=1.0195 | [2019年第25题-操作系统-系统调用]
```

**根因**：ChromaDB 默认使用 **cosine distance**（余弦距离），值域是 **0~2**（0=完全相同，1=正交，2=完全相反），而非 cosine **similarity**（0~1）。代码中过滤阈值写的是 `distance < 0.8`，而实际相关真题的 distance 约为 0.98~1.08，全部被误判为"不相关"过滤掉。

**修复**：
```python
# 旧：< 0.8（基于 similarity 量纲的经验值，实际上过滤了所有真题）
good_hits = [h for h in exam_hits if h.get("distance", 1.0) < 0.8]

# 新：< 1.2（基于 cosine distance 真实值域，同科目题目 distance ≈ 0.98~1.08）
good_hits = [h for h in exam_hits if h.get("distance", 2.0) < 1.2]
```
同时修复了 `check_answer` 中 `< 0.85` 的同类错误。

**面试话术**：
> "向量数据库踩的最深的坑：cosine distance 和 cosine similarity 是相反的量纲。similarity 越接近 1 越相关，distance 越接近 0 越相关。ChromaDB 返回的是 distance，值域 0~2，不是 0~1。调参前一定先打印实际返回值，肉眼看分布，再定阈值。"

---

### 🐛 Bug 6：LLM 忽略工具指令，System 消息不如 User 消息强制

**现象**：`generate_quiz` 成功从知识库检索到真题原文并返回，但 LLM 最终输出的是自己编的题目，完全没有使用原题。

**根因**：`tool_result`（包含完整真题原文的指令）被注入到 `system` 消息中。LLM 的行为模式是：**system 消息 = 背景设定/约束**，**最后一条 user 消息 = 当前要完成的任务**。LLM 倾向于"自主发挥"完成 user 消息的表面意图（"出一道题"），而不是严格执行 system 里的详细指令。加之 `temperature=0.7` 赋予了过多随机性。

**修复**：
```python
# response_generator.py
# 出题类指令：不放 system，改为最后一条 user 消息强制注入
if is_strict_quiz and tool_result:
    llm_messages.append({
        "role": "user",
        "content": (
            f"【系统指令 - 必须严格执行】\n"
            f"{tool_result}\n\n"
            f"再次强调：请直接展示上方真题原文，不允许自己编题或改编。"
        )
    })

# 出题类指令降温至 0.1，减少创造性偏差
temperature = 0.1 if is_strict_quiz else 0.7
```

**判断是否为"严格出题指令"的函数**：
```python
def _is_quiz_tool(tool_result: str) -> bool:
    return "[工具指令]" in tool_result and \
           ("历年真题" in tool_result or "请直接展示" in tool_result)
```

**面试话术**：
> "LLM 对消息角色的响应优先级：最后一条 user > system > 历史对话。需要 LLM 严格执行时，关键指令必须放在 user 消息末尾，而不是 system；同时把 temperature 降到 0.1 减少创造性偏差。这是 prompt engineering 中的'指令位置'原则。"

---

### � Bug 7：跨轮次状态丢失 → 判答时 `current_quiz_answer` 为空 → LLM 自由发挥判错

**现象**：出题轮正常显示题目（正确答案是 D），用户输入 "C"，系统回复"🎉 正确答案！D. RAM"——用户明明答错了，但系统既没说答错，又莫名表示"正确"，回复自相矛盾。

**排查过程（链路追踪）**：
1. 出题轮：`generate_quiz` → `response_generator` 从 `tool_result` 中提取隐藏答案 `D` → 写入 `state["current_quiz_answer"] = "D"` ✅
2. **答题轮**：`LangGraphAgent.chat_stream()` 构建新的 `initial_state` → 发现 `current_quiz_answer` 字段为空字符串 ❌
3. `tool_executor` 需要 `correct_answer` 来判答 → 拿不到 → LLM 自行判断 → 输出混乱

**根因**：`LangGraphAgent.__init__` 中没有 `self._current_quiz_answer` 实例变量，`chat()` 和 `chat_stream()` 方法在构建 `initial_state` 时不携带上一轮的 quiz_answer，且执行完毕后不保存结果中的 quiz_answer。**State 只在图执行期间有效，跨轮次信息靠实例变量桥接，但桥接逻辑缺失。**

**修复**（`agent/main_agent.py`，共 5 处）：
```python
# 1. __init__：初始化实例变量
self._current_quiz_answer = ""

# 2. chat() 的 initial_state：注入上一轮答案
"current_quiz_answer": self._current_quiz_answer,

# 3. chat() 结果保存：更新实例变量
self._current_quiz_answer = result.get("current_quiz_answer", self._current_quiz_answer)

# 4-5. chat_stream() 同理
```

**面试话术**：
> "LangGraph 图的 State 只在单次 invoke/stream 执行期间有效。跨轮次的状态传递，需要在 Agent 类实例上建立'桥接变量'——从上一次执行结果中提取关键字段，下一次执行时注入 initial_state。这是有状态 Agent 最容易忽略的问题：**图是无状态的，状态管理在图外面**。"

---

### 🐛 Bug 8：隐藏元标记泄露 → 答案提前暴露给用户

**现象**：出题时，用户能看到 `===展示内容结束===` 和 `[隐藏-仅供判答]正确答案=D[/隐藏]`，答案直接暴露。

**根因**：`response_generator` 把完整的 `tool_result`（含隐藏标记）注入给 LLM，虽然 prompt 要求"只输出展示内容"，但 LLM 不理解边界标记的语义，把元标记也原样输出了。**依赖 LLM 做格式过滤是不可靠的**。

**修复**（双重防护）：
```python
# 1. 输入端：注入 LLM 前剥离隐藏标记
def _strip_hidden_markers(text: str) -> str:
    text = re.sub(r'\[隐藏-仅供判答\].*?\[/隐藏\]', '', text)
    text = re.sub(r'===展示内容(?:开始|结束)===\s*', '', text)
    return text.strip()

# 2. 输出端：LLM 返回后兜底清洗
def _clean_final_response(text: str) -> str:
    text = re.sub(r'\[隐藏-仅供判答\].*?\[/隐藏\]', '', text)
    text = re.sub(r'===展示内容(?:开始|结束)===\s*', '', text)
    text = re.sub(r'\[工具指令\].*?\n', '', text)
    return text.strip()
```

**面试话术**：
> "任何不想让用户看到的内容，绝不能依赖 LLM 来过滤——LLM 可能原样输出、可能部分泄露、可能在某些 temperature 下不遵守指令。正确做法是**双重防护**：输入端把敏感信息剥离（LLM 根本看不到），输出端再兜底正则清洗（即使 LLM 以某种方式泄露了也能拦截）。这是安全性设计的纵深防御原则。"

---

### 🐛 Bug 9：判答全链路失效 → 用户回答 A/B/C/D 后系统错判（三层级联故障）

**现象**：工具层已正确返回 `❌ 回答错误...正确答案是 D`，但最终回复说"恭喜你，选择正确！正确答案是 D. RAM"——对错结论完全相反。

**排查发现三层级联问题**：

| 层级 | 问题 | 影响 |
|------|------|------|
| ① 路由层 | `intent_router` 对 "A"/"B"/"C"/"D" 这类极短消息无法正确分类 | 走错分支或走 unknown |
| ② 检索层 | 判答走了 `study` 分支的完整 RAG 链路，检索出不相关内容 | RAG 上下文干扰 LLM 判断 |
| ③ 生成层 | `check_answer` 的 tool_result 放在 system prompt 而非 user 消息 | LLM 忽略工具指令，自由发挥 |

**修复方案（三层同时修复）**：

**① 路由层**（`intent_router.py`）— 快速路径：
```python
def _is_quiz_answer(user_text: str, quiz_answer: str) -> bool:
    """当存在未消费的 quiz_answer 且用户输入匹配选项时，直接判定为答题"""
    if not quiz_answer:
        return False
    stripped = user_text.strip().upper()
    if re.match(r'^[A-D]\.?$', stripped):
        return True
    if re.search(r'(?:选|答案|选择)\s*[A-D]', stripped):
        return True
    return False

# intent_router_node 中优先检测
if _is_quiz_answer(user_text, quiz_answer):
    return {**state, "intent": "study", "tool_name": "check_answer",
            "tool_args": {"user_answer": user_choice, "correct_answer": quiz_answer}}
```

**② 检索层**（`graph.py`）— 判答跳过 RAG：
```python
def route_by_intent(state: AgentState) -> str:
    tool_name = state.get("tool_name", "")
    # check_answer 不需要 RAG，直接走 tool_executor
    if tool_name == "check_answer":
        return "plan_branch"  # 复用 plan 分支：tool_executor → response_generator
    # ...原逻辑
```

**③ 生成层**（`response_generator.py`）— 判答结果作为强制 user 消息注入：
```python
if is_check_answer and tool_result:
    llm_messages.append({
        "role": "user",
        "content": (
            f"【系统指令 - 判答结果已由系统确定，不得更改对错结论】\n\n"
            f"{tool_result}\n\n"
            f'如果上面说"回答错误"，你绝对不能说"回答正确"或"恭喜"。'
        )
    })
```

**④ 工具层**（`tools.py`）— 确定性判断，不依赖 LLM：
```python
# 在工具层面直接做字符串比较，不让 LLM 判断对错
is_correct = (user_answer == correct_answer)  # "A" == "D" → False

if is_correct is False:
    return f"[工具指令] 用户答错了这道题。\n❌ 回答错误。用户选了 {user_answer}，正确答案是 {correct_answer}。\n..."
```

**面试话术**：
> "这是一个典型的**级联故障**：路由错误 → RAG 噪声 → 指令被忽略，三层叠加导致最终输出完全相反。修复策略是**每层各自防守**：路由层加快速路径（不依赖 LLM 分类短消息）、检索层跳过无意义的 RAG、工具层用确定性逻辑判断对错（不让 LLM 做简单比较）、生成层只负责美化已确定的结论。核心原则：**能用确定性逻辑解决的问题，绝不依赖 LLM**。"

---

### 🐛 Bug 11：出题功能每次都出同一道题 → 向量检索确定性 + 固定取首条

**现象**：每次发送「帮我出一道关于操作系统的练习题」，系统永远返回同一道题（2013年操作系统·系统启动），无论问多少次都不变。

**排查过程（三步定位）**：

1. **第一步：确认检索层正常**。打印 `_query_collection("exam_questions", "操作系统", n_results=5)` 的返回值，发现确实返回了 5 条不同的真题，距离均约 0.98~1.08，全部在 `< 1.2` 阈值内——检索本身没有问题。

2. **第二步：看取题逻辑**。定位到 `agent/tools.py` 第 241~304 行，发现关键代码：
```python
exam_hits = _query_collection("exam_questions", topic, n_results=5)
good_hits = [h for h in exam_hits if h.get("distance", 2.0) < 1.2]
# ...
h0 = good_hits[0]   # ← 永远取第一条
```

3. **根因明确**：ChromaDB 向量检索是**确定性算法**——相同的查询向量每次返回完全一致且有序的结果列表。代码始终取 `good_hits[0]`（排名第一的结果），因此每次出的都是同一道题，与查询词无关。此外 `n_results=5` 候选池太小，即使打乱也缺乏多样性。

**修复**（三处改动）：

**① `agent/tools.py` — 随机化 + 扩大候选池 + 过滤已出题**：
```python
import random  # 新增

# 扩大候选池：5 → 20，获取更多不同题目供随机选择
exam_hits = _query_collection("exam_questions", topic, n_results=20)
good_hits = [h for h in exam_hits if h.get("distance", 2.0) < 1.2]

# 过滤已出过的题目，避免重复
shown_questions = state.get("shown_questions", []) if state else []
if shown_questions and good_hits:
    filtered = [h for h in good_hits if h["text"][:60].strip() not in shown_questions]
    if filtered:
        good_hits = filtered   # 过滤后还有题则使用，否则重置（刷完一轮）

# 关键修复：随机打散，每次出不同的题
if good_hits:
    random.shuffle(good_hits)
```

**② `agent/graph/nodes/tool_executor.py` — 出题后记录已出题 key + 传 state 给 execute_tool**：
```python
# 调用时传入 state，供 execute_tool 读取已出题记录
tool_result = execute_tool(tool_name, arguments_json, state=dict(state))

# 出题成功后把本题加入 shown_questions，防止下次重复
shown_questions = list(state.get("shown_questions") or [])
if tool_name == "generate_quiz" and "===展示内容开始===" in tool_result:
    m = re.search(r'===展示内容开始===\s*\n(.*)', tool_result, re.DOTALL)
    if m:
        quiz_key = m.group(1).strip()[:60]
        if quiz_key and quiz_key not in shown_questions:
            shown_questions.append(quiz_key)
    shown_questions = shown_questions[-50:]   # 最多保留近 50 条

return {**state, "tool_result": tool_result, "shown_questions": shown_questions, ...}
```

**③ `agent/graph/state.py` — AgentState 新增字段**：
```python
# 已出过的题目记录（前60字符 key，防止重复出同一道题）
shown_questions: list
```

**验证**：连续两次发送「帮我出一道关于操作系统的练习题」：
- 第一次：2017年 操作系统 · 系统调用
- 第二次：2024年 操作系统 · 文件系统

✅ 两道完全不同的题，问题解决。

**面试话术**：
> "向量数据库的检索是**确定性算法**，相同查询每次返回完全相同且有序的结果。如果总是取第一条，用户体验上就是'永远同一道题'。修复方式是两步：①扩大召回池（n_results 从 5 到 20），给随机化提供足够的候选多样性；②`random.shuffle()` 打散候选列表，加上跨轮次 `shown_questions` 记录防止重复。这个 Bug 的教训是：确定性系统需要主动引入随机性才能得到多样化的用户体验。"

---

### 🐛 Bug 12：流式输出"一次性出来" → LangGraph 节点级流式 ≠ token 级流式（全栈架构重构）

**现象**：用户提问后，需要等 3-8 秒（LLM 完整生成），文本突然"一下子全蹦出来"，没有逐字打字效果。RAG 管线进度条也是一次性全部亮起，不是逐步推进的。体验完全没有类 ChatGPT 的流畅感。

**排查过程（三层定位）**：

1. **前端层**：`sse.ts` 确实支持逐 event 解析和 `onToken` 回调，ChatBubble 也有流式光标动画——前端本身具备逐字渲染能力，问题不在前端。

2. **API 层**：`chat.py` 的 `event_generator()` 确实在逐个 yield SSE event——但 yield 的速度取决于 `agent.chat_stream()` 产出事件的速度。

3. **Agent 层（根因）**：`LangGraphAgent.chat_stream()` 使用 `graph.stream(stream_mode="values")`，这只是**逐节点**返回完整 State 快照，不是逐 token 流式。更致命的是：
   - `response_generator_node` 内部调用 `ZhipuAI.create(stream=False)`——**LLM 是一次性返回完整文本**
   - 拿到完整文本后，代码用 `re.split(r'(?<=[。！？\n])')` 按标点分句，再逐句 yield——这是**假的流式输出**
   - 所有节点（intent → rag → tool → response_generator → memory_update）在同一个**同步 for 循环**中串行执行，pipeline 事件虽然在节点间 yield 了，但每个节点内部的耗时（尤其是 LLM 调用）完全阻塞了事件推送

```python
# ❌ 旧代码的核心问题
response_generator_node():
    resp = client.chat.completions.create(stream=False)  # ← 等 3-8 秒
    final_response = resp.choices[0].message.content      # ← 一次拿到全部

chat_stream():
    for step in self._graph.stream(initial_state, stream_mode="values"):
        if step.get("final_response"):
            sentences = re.split(r'(?<=[。！？\n])', final_reply)  # ← 假分句
            for sentence in sentences:
                accumulated += sentence
                yield {"type": "token", "content": accumulated}   # ← 假流式
```

**根因总结**：三层问题叠加导致"假流式"：
| 层级 | 问题 | 影响 |
|------|------|------|
| ① LLM 调用 | `stream=False`，一次性返回全文 | 等待 3-8 秒无任何输出 |
| ② 图执行模式 | `stream_mode="values"`，节点级快照 | pipeline 事件被节点阻塞 |
| ③ 并发模型 | 同步 for 循环，单线程串行 | RAG 进度无法与 LLM token 交织 |

**修复方案（借鉴 SuperMew 项目的 asyncio.Queue + 后台 Task 架构，改动 6 个文件）**：

**① `agent/graph/graph.py` — 新增"准备图"**：

把完整图拆成两部分，新增 `build_prep_graph()` 构建不含 `response_generator` 和 `memory_update` 的**准备图**，流式场景只运行前半段（intent → rag → tool），LLM 生成在图外部独立流式调用。

```python
def build_prep_graph():
    """准备图：只运行 intent_router → rag_node → tool_executor，不含 response_generator"""
    builder = StateGraph(AgentState)
    builder.add_node("intent_router", intent_router_node)
    builder.add_node("rag_node",      rag_node)
    builder.add_node("tool_executor", tool_executor_node)
    
    builder.add_edge(START, "intent_router")
    builder.add_conditional_edges("intent_router", route_by_intent, {
        "rag_then_tool": "rag_node",
        "plan_branch":   "tool_executor",
        "review_branch": "rag_node",
        "direct_response": END,       # unknown → 直接结束准备阶段
    })
    builder.add_conditional_edges("rag_node", route_after_rag, {
        "tool_executor":      "tool_executor",
        "response_generator": END,    # review → RAG 结束即可
    })
    builder.add_edge("tool_executor", END)
    return builder.compile()
```

**② `agent/graph/nodes/response_generator.py` — 新增流式生成函数**：

提取消息构建逻辑为独立的 `build_llm_messages()` 函数，新增 `response_generator_stream()` 生成器，使用 `stream=True` 逐 token yield：

```python
def response_generator_stream(state: AgentState):
    """逐 token yield，与 response_generator_node 逻辑一致但使用 stream=True"""
    llm_messages, temperature = build_llm_messages(state)  # 复用消息构建逻辑
    
    full_response = ""
    client = ZhipuAI(api_key=API_KEY)
    stream = client.chat.completions.create(
        model=MODEL, messages=llm_messages,
        temperature=temperature, stream=True,         # ← 关键改动
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            full_response += token
            yield token          # 逐 token yield（真流式）
    
    full_response = _clean_final_response(full_response)
    yield {"__done__": True, "full_response": full_response, "quiz_answer": quiz_answer}
```

**③ `agent/main_agent.py` — 新增 `chat_stream_async()` 方法（核心架构变更）**：

用 `asyncio.Queue` + 后台 `asyncio.Task` 替代同步 for 循环：

```python
async def chat_stream_async(self, user_message: str):
    output_queue: asyncio.Queue = asyncio.Queue()  # 统一事件汇聚点
    loop = asyncio.get_running_loop()
    
    async def _graph_worker():
        # Phase 1: 线程池中运行准备图，pipeline 事件通过 call_soon_threadsafe 实时推送
        def _run_graph_sync():
            for step in self._prep_graph.stream(initial_state, stream_mode="values"):
                if step.get("intent") and step["intent"] != "unknown":
                    evt = {"type": "pipeline", "stage": "intent", ...}
                    loop.call_soon_threadsafe(output_queue.put_nowait, evt)  # 跨线程安全推送
                # ... 同理推送 rag、tool 事件
            return last_state
        
        last_state = await loop.run_in_executor(None, _run_graph_sync)
        
        # Phase 2: 线程池中流式调用 LLM，逐 token 推送
        def _run_stream_llm():
            for item in response_generator_stream(last_state):
                if isinstance(item, str):
                    loop.call_soon_threadsafe(output_queue.put_nowait, {"type": "token", "content": item})
            return done_signal
        
        done_signal = await loop.run_in_executor(None, _run_stream_llm)
        
        # Phase 3: 线程池中运行 memory_update（后台静默，不阻塞输出）
        await loop.run_in_executor(None, lambda: memory_update_node(updated_state))
        
        await output_queue.put(None)  # 哨兵信号
    
    worker_task = asyncio.create_task(_graph_worker())
    
    try:
        while True:
            event = await output_queue.get()
            if event is None: break
            yield event
    except GeneratorExit:             # 客户端断开连接
        worker_task.cancel()          # 安全取消后台任务
        try: await worker_task
        except asyncio.CancelledError: pass
        raise
```

**④ `api/v1/chat.py` — 改用 StreamingResponse + 支持 GeneratorExit**：

```python
# 从 sse-starlette 的 EventSourceResponse 改为 FastAPI 原生 StreamingResponse
from fastapi.responses import StreamingResponse

async def event_generator():
    async for chunk in agent.chat_stream_async(req.message):
        # 增量 token：content 是新片段，accumulated 是全量
        full_reply += token_content
        yield f"event: token\ndata: {json.dumps({'content': token_content, 'accumulated': full_reply})}\n\n"
    
return StreamingResponse(event_generator(), media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

**⑤ `frontend/src/utils/sse.ts` — 支持 AbortController 中断**：

```typescript
export async function streamChat(message: string, callbacks: SSECallbacks, signal?: AbortSignal) {
    const response = await fetch('/api/v1/chat/stream', {
        method: 'POST', signal,                          // ← 传入 AbortSignal
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message }),
    })
    // ... 解析逻辑不变
}
// AbortError 是正常中断，走 onClose 而非 onError
```

**⑥ `frontend/src/stores/chat.ts` — 增加中断控制**：

```typescript
let abortController: AbortController | null = null

async function sendMessage(content: string) {
    abortController = new AbortController()
    await streamChat(content, {
        onToken: (data) => {
            // 新版增量模式：content 是增量 token，accumulated 是全量
            if (data.accumulated !== undefined) {
                messages.value[aiIndex].content = data.accumulated
            }
        },
        // ...
    }, abortController.signal)
}

function stopStreaming() {
    abortController?.abort()       // 前端中断 → 后端 GeneratorExit → 取消 asyncio.Task
    abortController = null
}
```

**⑦ `frontend/src/views/Chat.vue` — 停止按钮 + 流式滚动**：

```html
<!-- 发送/停止切换按钮 -->
<a-button v-if="!chat.streaming" type="primary" @click="handleSend">发送</a-button>
<a-button v-else danger @click="chat.stopStreaming()">⏹ 停止</a-button>
```

```typescript
// 流式输出时自动滚动（messages.length 不变但内容在增长）
watch(() => chat.currentStreamContent, () => nextTick(() => {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}))
```

**修复后的完整数据流**：

```
用户输入 → Chat.vue → Pinia Store（AbortController）
    ↓
fetch POST /api/v1/chat/stream（带 signal）
    ↓
FastAPI StreamingResponse(event_generator())
    ↓
agent.chat_stream_async() 启动 asyncio.Queue + worker_task
    │
    ├─ Phase 1 [线程池]: prep_graph.stream()
    │   call_soon_threadsafe → pipeline 事件实时入队
    │   （前端看到：意图识别中... → RAG 检索中... → 工具执行中...）
    │
    ├─ Phase 2 [线程池]: response_generator_stream(stream=True)
    │   call_soon_threadsafe → token 事件逐个入队
    │   （前端看到：文字一个字一个字地出现 ✨）
    │
    └─ Phase 3 [线程池]: memory_update_node()
        （后台静默运行，不阻塞输出）
    │
主循环: while event = await queue.get() → yield SSE → 前端实时渲染
```

**验证效果**：

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 首 token 延迟 | 3-8 秒（等全量） | <1 秒（pipeline 事件即时推送） |
| 文本输出效果 | 一次性全部出现 | 逐字符打字效果 |
| Pipeline 进度 | 一次性全部亮起 | 逐步推进（intent → rag → tool → llm） |
| 用户中断 | ❌ 不支持 | ✅ 停止按钮 → AbortController → GeneratorExit |
| 流式输出时滚动 | ❌ 不自动滚 | ✅ watch currentStreamContent 自动滚底 |

**面试话术**：
> "这个问题的本质是架构级别的：LangGraph 的 `stream_mode='values'` 只是**节点级别**的流式（每个节点跑完才推送一次），不是 **token 级别**的流式。而且 `response_generator_node` 内部用的 `stream=False`，LLM 一次性返回全文，之后用正则分句'假装'逐句输出——用户体验完全不是真正的打字效果。"
>
> "修复方案借鉴了 SuperMew 项目的 `asyncio.Queue + 后台 Task` 并发架构，做了三个关键改动：①拆图——新建一个不含 `response_generator` 的'准备图'，前半段（intent→rag→tool）在线程池中执行，pipeline 事件通过 `call_soon_threadsafe` 实时推入队列；②流式 LLM——新增 `response_generator_stream()` 函数用 `stream=True`，逐 token 推入同一个队列；③主循环统一消费队列 yield SSE，pipeline 进度和 LLM token 真正交织输出。加上前端 AbortController → 后端 GeneratorExit → 取消 asyncio.Task 的完整中断链路。最终首 token 延迟从 3-8 秒降到 <1 秒，体验完全对齐 ChatGPT 级别。"

---

### 🐛 Bug 10：f-string 中文引号与 Python 引号冲突 → SyntaxError → 全站 500

**现象**：修完 Bug 9 后，所有聊天请求返回 `Internal Server Error`，后端 uvicorn 日志正常启动但接口 500。

**根因**：`response_generator.py` 第 152-153 行：
```python
# ❌ f-string 使用双引号包裹，内部中文双引号 "" 与 Python 引号冲突
f"如果上面说"回答错误"，你绝对不能说"回答正确"或"恭喜"。"
#              ↑ Python 认为字符串在这里结束了
```

Python 解释器将中文左双引号 `"` 视为 ASCII 双引号 `"` 的等价物（在某些编码场景下），导致字符串提前闭合，后续内容变成非法语法。

**修复**：
```python
# ✅ 外层改用单引号，内部双引号不冲突
f'如果上面说"回答错误"，你绝对不能说"回答正确"或"恭喜"。'
```

**排查方法**：
```bash
python -c "from agent.graph.graph import get_graph; print('OK')"
# SyntaxError: invalid syntax. Perhaps you forgot a comma?
# → 直接指向行号，一目了然
```

**面试话术**：
> "这个 Bug 非常阴险：uvicorn --reload 检测到文件变化后重启，但由于 import 失败，路由注册失败，健康检查接口因为在模块加载前就注册了所以还能通过。导致 `/health` 返回 200 但所有业务接口 500。排查方法：直接在终端 `python -c 'import ...'` 验证模块能否正常加载，语法错误会即时报出行号。教训：**修代码后，先跑一次 import 验证，再提交。**"

---

### �💡 通用 Debug 原则（从以上案例提炼）

| 原则 | 对应案例 | 具体做法 |
|------|---------|---------|
| **先打印实际值，再调阈值** | Bug 3/5 | `python -c "..."` 打印真实分布，消灭猜测 |
| **理解算法值域再配参数** | Bug 3/5 | RRF 最高分 ≈ 0.016；cosine distance 范围 0~2 |
| **distance ≠ similarity** | Bug 5 | ChromaDB 返回的是 distance，越小越相关 |
| **混合检索两路索引独立维护** | Bug 4 | 写入时同步更新 BM25 和向量两套索引 |
| **LLM 指令放 user 末尾更强制** | Bug 6/9 | 严格执行场景：指令 → user msg + temperature=0.1 |
| **跨轮次状态靠实例变量桥接** | Bug 7 | LangGraph State 是单次执行的，跨轮次需要外部保存 |
| **敏感信息双重防护** | Bug 8 | 输入端剥离 + 输出端兜底清洗，不依赖 LLM 过滤 |
| **能用确定性逻辑就不用 LLM** | Bug 9 | 简单比较、路由判断等用 if-else，LLM 只做生成 |
| **修改后先验证 import** | Bug 10 | `python -c "from ... import ..."` 快速验证语法 |
| **SPA 中统一使用 Router 跳转** | Bug 2 | 避免 `window.location` 与 Vue Router 竞争 |
| **前端依赖版本锁定要关注 ESM/CJS** | Bug 1 | Vite 8+ 要求依赖完整支持 ESM |
| **确定性检索需主动引入随机性** | Bug 11 | 向量检索结果有序且固定，必须 shuffle + 扩大候选池 |
| **跨轮次去重靠 State 字段持久化** | Bug 11 | shown_questions 存入 AgentState，每轮过滤已出题目 |
| **节点级流式 ≠ token 级流式** | Bug 12 | LangGraph `stream_mode="values"` 只是逐节点推送快照，不是逐 token |
| **同步阻塞→异步队列解耦** | Bug 12 | asyncio.Queue + 后台 Task + `call_soon_threadsafe` 跨线程推事件 |
| **拆图分治：准备图 + 外部流式** | Bug 12 | 图内不含 LLM 生成节点，LLM 在图外 `stream=True` 独立流式调用 |
| **全链路中断：前端→后端→Task** | Bug 12 | AbortController → GeneratorExit → worker_task.cancel() |

---

### 🎤 基于真实 Debug 的面试问答

**"你遇到过什么难排查的 Bug？"**

> "印象最深的是 ChromaDB distance 阈值的问题。我们的真题检索始终命中 0 条，前两次排查都猜错了根因——先以为是函数参数顺序，再以为是 prompt 不够强，折腾了半小时。最后静下来直接在终端打印实际 distance 值，才发现操作系统真题的 distance 约为 0.98~1.08，而我的过滤阈值是 `< 0.8`，全被误判为不相关。根本原因是我把 cosine distance（0~2）当成了 cosine similarity（0~1）来用。修一行数字，系统立刻恢复正常。教训就是：调参之前先打印实际值，不要凭感觉猜阈值。"

**"你的 RAG 检索效果不好时怎么排查？"**

> "四步走：①看 RAG 追踪面板，确认哪一步出问题——是召回少（BM25/向量）、融合分数低（RRF配置）、门控拦截（阈值）还是精排乱序（Reranker）；②对问题步骤打印中间变量；③检查配置参数的值域是否合理（距离/分数的量纲容易搞错）；④如果是 BM25 召回 0，先确认索引是否存在且非空。"

**"LLM 不遵循指令怎么办？"**

> "三个手段：①把关键指令移到最后一条 user 消息（而非 system），LLM 优先响应最新 user 消息；②降低 temperature 到 0.1 减少创造性；③在指令末尾加重复强调（'再次强调：...'），利用 recency bias 强化执行。如果还不行，考虑换成 function calling 的结构化输出方式，完全绕过自然语言指令。"

**"有状态 Agent 跨轮次状态管理踩过什么坑？"**

> "最典型的是出题-答题的跨轮次状态传递。LangGraph 的 State 只在单次 invoke 期间存在，执行结束后就丢了。我出题时在 State 中保存了正确答案 'D'，但下一轮用户答题时 State 已经是全新的，正确答案丢失，LLM 只能瞎猜对错。修复方法是在 Agent 类实例上增加 `_current_quiz_answer` 桥接变量，每次执行结束后从 result 中提取保存，下次执行时注入 initial_state。本质上就是：**图是无状态函数，跨轮次状态管理在图外面**。"

**"Agent 系统中，哪些逻辑该用 LLM，哪些不该？"**

> "判答系统是最好的反面案例。最初让 LLM 判断用户回答是否正确——把正确答案和用户答案都告诉 LLM，让它比较。结果 LLM 经常无视提供的正确答案，自己推理出一个错误结论。这种简单字符串比较（A == D？False）根本不需要 LLM，反而 LLM 容易出错。后来改成工具层直接 `if user_answer == correct_answer`，确定性判断对错，LLM 只负责把'答对了/答错了'这个已确定结论包装成友好的解释文案。原则就是：**能用确定性逻辑解决的，绝不用 LLM；LLM 只做它擅长的——自然语言生成。**"

**"遇到过级联故障吗？怎么排查的？"**

> "判答功能出过一个三层级联故障。表面看是 LLM 回复错误，但实际涉及路由层（短消息 'A' 无法被 LLM 分类器正确识别意图）、检索层（判答不需要 RAG 却走了完整检索流程，引入噪声）、生成层（tool_result 放在 system 消息中被忽略）三个问题叠加。排查方法是从 RAG 管线追踪面板逐层检查——先看路由结果是否正确，再看 RAG 是否必要，最后检查 LLM 输入的 messages 构成。修复是每层各自加防守：路由层加快速路径绕过 LLM 分类、图路由层让 check_answer 跳过 RAG、工具层做确定性判断、生成层强制注入结论。"

**"流式输出体验差，你是怎么排查和优化的？"**

> "用户反馈文字是'一下子蹦出来'的，没有打字效果。我从前端到后端逐层排查：前端 SSE 解析和渲染都没问题，问题在后端——LangGraph 的 `stream_mode='values'` 只是节点级推送，不是 token 级流式；而且 `response_generator_node` 内部用了 `stream=False`，LLM 一次性返回全文后再用正则分句假装逐句输出。修复方案借鉴了另一个项目的并发架构：①新建'准备图'（不含 response_generator），前半段在线程池中运行，pipeline 事件通过 `call_soon_threadsafe` 实时推入 `asyncio.Queue`；②新增 `response_generator_stream()` 用 `stream=True` 逐 token yield 到同一个队列；③主循环统一消费队列。加上 AbortController → GeneratorExit → Task.cancel() 的完整中断链路。首 token 延迟从 3-8 秒降到 <1 秒。"

**"为什么要拆出'准备图'？不能直接在完整图里流式吗？"**

> "LangGraph 的 `response_generator_node` 是一个同步函数，返回完整 state dict。要做到 token 级流式，必须绕过图的节点执行机制——图只能在节点**完成后**才推送快照。所以方案是：准备图只运行到 tool_executor 就结束，拿到中间 state 后，在图外部直接调用 `response_generator_stream(state)` 逐 token yield。这样既保留了 LangGraph 管理前半段节点路由的能力，又避开了它不支持节点内流式的限制。本质是'拆图分治'——适合用图编排的部分用图，不适合的部分手动控制。"

**"`call_soon_threadsafe` 是什么？为什么需要它？"**

> "LangGraph 的 `graph.stream()` 是同步阻塞调用，我用 `run_in_executor(None, _run_graph_sync)` 放到线程池里跑。但 `asyncio.Queue` 是异步对象，不能从线程池的同步函数里直接 `await queue.put()`。`loop.call_soon_threadsafe(queue.put_nowait, evt)` 是 asyncio 提供的**跨线程安全**方法——它把 `put_nowait` 调度到主事件循环的下一个 tick 执行，既不阻塞线程池，又保证了线程安全。这是 Python 异步编程中'同步代码向异步队列推送事件'的标准模式。"

---

## 附录：面试前快速复习清单

- [ ] 能画出完整系统架构图（5层）
- [ ] 能说出 AgentState 的 11 个字段
- [ ] 能解释 RRF 公式和 k=60 的含义
- [ ] 能说出三级分块的具体参数（2000/600/150）
- [ ] 能解释 HyDE 的核心思想
- [ ] 能说出 SSE 5 种事件类型
- [ ] 能说出记忆系统 L1-L4 的存储格式和触发时机
- [ ] 能说出 Hit@5 = 0.92 和 MRR = 0.78
- [ ] 能解释为什么不用 EventSource
- [ ] 能说出 Reranker 三级降级链的顺序
- [ ] 能解释 LangGraph vs AgentExecutor 的区别
- [ ] 能说出 3 个 Query 重写策略及其场景
- [ ] 能讲 1 个完整的 STAR 故事（< 2 分钟）
- [ ] 能解释 LangGraph 跨轮次状态管理（Bug 7 桥接变量）
- [ ] 能解释"确定性逻辑 vs LLM"的设计原则（Bug 9）
- [ ] 能说出敏感信息双重防护策略（Bug 8 输入剥离+输出清洗）
- [ ] 能讲 Bug 9 级联故障的排查过程（路由→检索→生成三层）
- [ ] 能解释向量检索确定性问题及 shuffle + shown_questions 去重方案（Bug 11）
- [ ] 能解释"节点级流式 vs token 级流式"的区别，以及 asyncio.Queue + 后台 Task 的并发架构（Bug 12）
- [ ] 能画出 Bug 12 修复后的数据流：prep_graph → response_generator_stream → Queue → SSE
- [ ] 能解释 `call_soon_threadsafe` 为什么是跨线程推送事件的关键（同步线程池→异步事件循环）
- [ ] 能说出完整的中断链路：AbortController → fetch abort → GeneratorExit → worker_task.cancel()
