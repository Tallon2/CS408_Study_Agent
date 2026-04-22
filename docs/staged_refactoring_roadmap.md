# 分阶段重构路线图（工程落地版）

> 目标：在**不破坏现有可运行能力**的前提下，逐步降低维护成本、收敛技术债，并为后续新增功能（更多意图、更强 RAG、记忆演进、后台管理）建立稳定边界。
>
> 适用范围：当前 `E:\DEMO` 仓库（FastAPI + LangGraph + RAG + Vue3）
>
> 设计原则：**先稳定、后收敛；先统一边界、后做拆分；先补验证、后做迁移。**

---

## 1. 当前仓库的核心判断

结合当前仓库代码，项目现状不是“不能用”，而是典型的**可运行但演进成本逐渐走高**：

- 主链路能跑，但存在明显的结构性技术债：
  - `agent/main_agent.py` 同时承载 legacy agent、LangGraph agent、同步/异步流式、生命周期逻辑
  - `memory/rag/retriever_rag.py` 集中了承担召回、融合、门控、fallback、rerank、trace、格式化等多种职责
  - `config.py` 与 `core/settings.py` 并存，配置来源不统一
- 运行方式不统一：大量 `sys.path` hack 说明项目尚未完成包化
- 状态存储边界不清：已有 ORM Model，但 `L2/L4` 仍以 JSON 为主
- 测试与回归保护薄弱：当前重构若直接大拆，高概率引入隐性回归

因此，重构策略不应是“先大面积拆文件”，而应改为：

1. **先修复确定性问题和统一入口**
2. **再收敛运行时边界与配置边界**
3. **再拆核心大模块**
4. **最后推进包化、数据迁移与目录清理**

---

## 2. 重构总目标

本次重构聚焦四个目标：

### 目标 A：建立稳定边界
让配置、Agent 运行时、RAG 管线、数据访问各自有清晰入口，减少“改一个点牵一片”的情况。

### 目标 B：降低新增功能成本
为后续新增以下能力预留稳定扩展点：
- 新 intent / 新工具
- 新的 reranker / embedding / 检索策略
- 更细粒度的会话与画像管理
- 后台管理与运营分析能力

### 目标 C：避免重构期间破坏主流程
必须优先保护以下现有能力：
- FastAPI 服务启动
- `/api/v1/chat/stream` SSE 对话
- study / review / plan 基本链路
- 现有本地索引与存储目录兼容

### 目标 D：让仓库从“个人项目形态”过渡到“可持续维护形态”
重点不是追求复杂架构，而是保证：
- 目录职责清晰
- 运行方式统一
- 核心模块可测试
- 历史遗留代码可控退出

---

## 3. 重构原则（执行期间必须遵守）

### 3.1 不先追求“拆得漂亮”，先追求“边界稳定”
如果只是把一个 600 行文件拆成 4 个 150 行文件，但职责仍然互相缠绕，那不算真正完成重构。

### 3.2 不一次性做基础设施大迁移
`pyproject.toml`、包化、移除 `sys.path` hack、脚本整理，这些都要分阶段推进，避免一次性把运行入口全部打散。

### 3.3 所有重构都要有可验证出口
每一阶段都必须定义：
- 改哪些模块
- 不改哪些模块
- 完成标准（Definition of Done）
- 回归验证方式

### 3.4 对外契约优先稳定
以下接口在重构中默认不能随意改动：
- `agent.chat()`
- `agent.chat_stream()`
- `agent.chat_stream_async()`
- `/api/v1/chat/stream` SSE 事件格式
- `AgentState` 关键字段结构
- `storage/` 现有目录与数据兼容性

---

## 4. 分阶段路线图

---

## Phase 0：建立最小回归保护与问题基线（建议 1~2 天）

### 目标
在正式重构前，先建立“最小可回归保护”，避免后续每一步都靠人工体感判断是否改坏。

### 范围
- 不做大重构
- 只补最小级别的 smoke check / 回归基线
- 记录当前主流程行为

### 建议动作
1. 补充一份最小回归清单文档
2. 明确以下手工验证用例：
   - 服务启动成功
   - `/health` 正常
   - 登录接口可用
   - `/api/v1/chat/sync` 可返回
   - `/api/v1/chat/stream` 能输出 `start/token/done`
   - `study` 意图能走 RAG
   - `review` 意图当前行为记录下来
3. 为纯函数模块优先建立测试入口：
   - `memory/rag/hybrid_fusion.py`
   - `memory/rag/score_gate.py`
4. 将现有关键运行方式记录到文档：
   - 本地启动方式
   - 索引构建方式
   - 前端启动方式

### DoD
- 团队可以用一份固定清单验证“系统没被重构搞坏”
- 至少有 2 个纯函数模块具备测试落点
- 关键接口和启动方式不再只存在于口头认知中

### 风险说明
如果跳过这一阶段，后续任何拆分都会缺少可靠反馈闭环。

---

## Phase 1：修复确定性问题，统一配置入口（建议 2~3 天）

### 目标
优先解决**低风险高收益**问题，为后续结构收敛铺路。

### 重点模块
- `config.py`
- `core/settings.py`
- `agent/graph/nodes/rag_node.py`
- `dao/database.py`
- `agent/graph/nodes/response_generator.py`

### 建议动作

#### 1）统一配置入口
将 `config.py` 改造成**兼容层**，内部委托到 `core/settings.py`。

目标状态：
- 老代码仍可 `from config import API_KEY, MODEL`
- 新代码统一走 `get_settings()`
- 所有新增配置只允许定义在 `core/settings.py`

#### 2）修复 `rag_node.py` 的 review RAG bug
当前 `review` 路由进入 `rag_node` 后会被错误跳过，应修复。

同时补一个轻量规则函数概念：
- 哪些 intent 允许走 RAG，应该被显式表达，而不是散落在 if 条件里

#### 3）修复 `create_tables()` 导入不完整问题
虽然当前不一定导致运行故障，但会制造认知偏差，应尽早修正。

#### 4）去掉 `response_generator.py` 内部重复逻辑
优先让 `response_generator_node()` 复用 `build_llm_messages()`，降低 prompt 构造分叉。

### DoD
- 仓库只保留一个“真实配置源”：`core/settings.py`
- `review` 请求能够获得 RAG 上下文
- `response_generator` 的消息构造逻辑不再重复维护
- 启动、聊天、SSE 主链路无行为回退

### 为什么这一阶段先做
这一阶段改动小、收益高，而且能显著降低 Phase 2/3 的重构不确定性。

---

## Phase 2：收敛 LLM / Provider 访问边界（建议 2~4 天）

### 目标
把散落在各模块中的模型客户端初始化方式收拢成统一入口，避免后续扩展模型、超时、重试、降级策略时重复修改。

### 重点模块
- `core/`
- `agent/graph/nodes/intent_router.py`
- `agent/graph/nodes/response_generator.py`
- `memory/hooks.py`
- `memory/l4_profile.py`
- `memory/rag/query_rewriter.py`
- `memory/rag/retriever_rag.py`
- `memory/retrieval.py`

### 建议动作
1. 新增统一 LLM 客户端/提供者入口，例如：
   - `core/llm_client.py`
   - 或 `core/clients.py`
2. 统一管理：
   - `ZhipuAI` client 获取
   - 默认模型名
   - timeout / retry / 温度等默认策略（如适合）
3. 将分散的 `ZhipuAI(api_key=API_KEY)` 逐步替换为统一入口
4. 明确区分以下能力边界：
   - chat model
   - embedding model
   - reranker API

### DoD
- 核心运行链中不再散落直接实例化 `ZhipuAI(api_key=...)`
- 模型名和 API key 来源不再分散
- 后续切换 provider 或增加兜底逻辑时只需修改集中入口

### 说明
这一阶段不是为了“造抽象层”，而是为了避免后续每次改模型配置都全仓搜索替换。

---

## Phase 3：收敛 Agent 运行时边界（建议 4~6 天）

### 目标
先把 Agent 的运行时职责拆清楚，再谈更细粒度的模块拆分。

### 当前问题
`agent/main_agent.py` 当前至少混合了：
- legacy agent
- LangGraph agent
- state 初始化
- session 管理
- sync chat
- async stream
- sync stream 兼容
- session end hook

这会导致后续新增一个能力时，必须冒险修改主文件。

### 建议动作

#### 1）先做物理隔离
- `LearningAgent` 移到 `agent/legacy_agent.py`
- `main_agent.py` 先聚焦当前主用实现

#### 2）再做职责下沉
从 `LangGraphAgent` 中优先抽出以下逻辑：
- 初始 state 构造
- memory snapshot 读写同步
- 流式执行编排（尤其 async stream）
- session 结束生命周期处理

#### 3）保持外部接口稳定
以下方法签名优先保持不变：
- `chat()`
- `chat_stream()`
- `chat_stream_async()`
- `on_session_end()`

### 推荐目标结构
不要求一次到位，但建议朝以下方向演进：

```text
agent/
├── main_agent.py          # 对外主入口，尽量变薄
├── legacy_agent.py        # 历史实现隔离
├── runtime.py             # 会话态、memory snapshot、message 管理
├── execution.py           # sync / async 执行路径
└── ...
```

### DoD
- `LearningAgent` 不再与主用 Agent 混在一个文件
- `LangGraphAgent` 的职责明显收窄，不再同时承担全部细节
- `api/v1/chat.py` 兼容逻辑仍然可工作
- SSE 流式行为与现状保持兼容

### 风险提醒
这一阶段不能“边拆边改外部协议”，否则前端 SSE、聊天接口、历史逻辑容易一起受影响。

---

## Phase 4：重构 RAG 主管线，先统一内部结果模型，再拆模块（建议 5~7 天）

### 目标
把 `memory/rag/retriever_rag.py` 从“超级脚本”收敛为“清晰 orchestration 入口”。

### 当前问题
该模块当前同时承担：
- 双路检索
- RRF 融合
- score gate
- fallback rewrite
- rerank
- trace 生成
- 格式化输出
- 日志
- 配置读取

真正的问题不是文件大，而是职责耦合过深。

### 建议动作

#### 1）先统一内部结果对象
不要直接把 `retrieve()` 改成 `with_trace: bool` 的双态返回。

更推荐：
- 保留稳定外部接口：
  - `retrieve(...) -> str`
  - `retrieve_with_trace(...) -> dict`
- 统一内部实现：
  - `_run_pipeline(...) -> RetrievalResult`

这样可以做到：
- 调用方不用改习惯
- 内部逻辑真正去重
- 类型更稳定

#### 2）按职责拆分，而不是按长度拆分
建议优先拆出：
- `reranker.py`：LLM/API rerank
- `formatter.py`：context/trace/log 输出格式
- `pipeline_config.py` 或 settings adapter：配置映射

如果拆分过快，也至少要在同文件中先形成清晰私有层次。

#### 3）统一配置来源
`_PIPELINE_CONFIG` 不应继续成为孤立硬编码，应从 `core/settings.py` 映射生成。

#### 4）保留可观测性
前端已经有 RAG 可视化面板，因此 trace 结构重构时必须保证：
- 语义兼容
- 字段有演进说明
- 不随意删除关键阶段信息

### DoD
- `retrieve()` 与 `retrieve_with_trace()` 主体逻辑不再重复
- rerank / format / trace 的边界清晰
- RAG 关键参数统一从 settings 获得
- 前端 RAG 过程展示不回退

### 风险提醒
RAG 是整个项目“可用性体感”的核心，任何重构都必须优先保证检索质量与 trace 可用性不回退。

---

## Phase 5：重构工具层与节点层的局部热点（建议 3~5 天）

### 目标
清理局部热点文件，减少单函数过长、逻辑缠绕问题。

### 重点模块
- `agent/tools.py`
- `agent/graph/nodes/*`

### 建议动作

#### 1）处理 `agent/tools.py`
其中 `generate_quiz` 分支明显偏长，建议抽离为专门模块，例如：

```text
agent/
├── tools.py
└── tools/
    └── quiz.py
```

但注意：
- 不要为了“分层漂亮”过度创建抽象基类
- 保留简单函数映射方式即可

#### 2）节点层收敛规则
对 `intent_router.py`、`response_generator.py`、`tool_executor.py` 等节点，优先统一：
- 配置获取方式
- LLM 获取方式
- 轻量公共工具函数

### DoD
- `tools.py` 不再承载明显超长业务分支
- 节点层的公共行为（配置 / LLM / message 构造）不再散落
- 新增一个工具或新意图时，不需要再修改过多无关文件

---

## Phase 6：分阶段包化，逐步移除 `sys.path` hack（建议 4~6 天）

### 目标
让项目运行方式从“脚本式工程”过渡为“标准 Python 包工程”。

### 现状判断
当前多个核心文件中存在 `sys.path.insert(...)`，说明：
- 工程可运行，但高度依赖 cwd 和启动姿势
- 一次性移除会有较大风险

### 正确策略：分阶段推进

#### 阶段 A：先引入包描述
新增 `pyproject.toml`，明确：
- 项目名
- Python 版本要求
- 包发现方式

#### 阶段 B：统一推荐启动方式
确保以下方式成为主推荐路径：
- 后端启动方式
- 索引脚本执行方式
- 测试执行方式

#### 阶段 C：优先移除核心链路 hack
优先处理：
- `api/`
- `agent/graph/`
- `memory/rag/`
- `server.py`

#### 阶段 D：最后处理脚本层
最后再处理：
- `scripts/`
- `evaluation/`
- 零散测试脚本

### DoD
- 项目具备标准包安装/开发模式
- 核心运行链路不再依赖 `sys.path` hack
- 文档中明确推荐的启动方式与实际一致
- Docker / 本地 / 测试三种场景的 import 行为一致

### 风险提醒
这是基础设施迁移，不是简单格式化清理；必须分批验证，不能一口气删完。

---

## Phase 7：推进状态存储收敛，优先迁移 L2/L4（建议 5~8 天）

### 目标
解决“已有 ORM model，但真实状态仍主要依赖 JSON 文件”的长期维护问题。

### 迁移优先级

#### 第一优先级
- `L2 TaskState`
- `L4 UserProfile`

原因：
- 已有对应 ORM Model
- 结构相对稳定
- 对后续后台能力、统计能力、并发一致性更有帮助

#### 第二优先级
- 会话历史
- L3 知识沉淀索引相关元数据

### 建议动作
1. 为 `TaskState` / `UserProfile` 建立数据库读写主路径
2. 保留 JSON 读取迁移工具或一次性导入脚本
3. 设置迁移窗口：
   - 先支持读取旧数据并写入新结构
   - 验证稳定后再考虑收缩旧路径

### DoD
- `L2/L4` 有明确单一真实数据源
- 新会话下不再依赖 JSON 作为主状态存储
- 迁移方案可重复执行、可回滚、可验证

### 风险提醒
这一步不要和大规模 Agent/RAG 重构同时进行，否则问题定位会非常困难。

---

## Phase 8：清理遗留入口、目录整顿、文档收尾（建议 2~3 天）

### 目标
在核心结构稳定后，再清理历史包袱，避免“先删再发现有人还在用”。

### 建议动作
1. 处理根目录遗留文件：
   - 旧入口：`app.py`, `main.py`
   - 一次性脚本：`fix_all.py`, `fix_questions.py`, `append_corrections.py`
   - 调试脚本：`show_questions.py`, `review_questions.py`
   - 散落测试：`test_api.py`, `test_validate.py`
   - 临时文件：`tmp_out.txt`, `1.26.0` 等
2. 归档或迁移：
   - 可保留但低频使用的移入 `_legacy/` 或 `scripts/`
   - 散落测试移入 `tests/`
3. 更新文档：
   - `README.md`
   - 启动方式
   - 架构图
   - 重构后目录说明

### DoD
- 根目录只保留真正的应用入口与必要配置
- 历史文件不再污染主阅读路径
- 新成员看目录即可理解主要模块职责

---

## 5. 推荐执行顺序（建议采用）

如果以“工程落地优先”为原则，推荐顺序如下：

1. **Phase 0**：最小回归保护
2. **Phase 1**：配置统一 + 确定性 bug 修复
3. **Phase 2**：LLM/provider 边界统一
4. **Phase 3**：Agent 运行时边界收敛
5. **Phase 4**：RAG 主管线重构
6. **Phase 5**：工具层与节点层局部热点治理
7. **Phase 6**：包化与 `sys.path` hack 分阶段移除
8. **Phase 7**：L2/L4 状态迁移到 DB
9. **Phase 8**：遗留清理与文档收尾

这个顺序的核心思想是：
- 先保证“看得清、配得准、测得到”
- 再动最复杂的 Agent / RAG 主链路
- 最后再做基础设施与数据层迁移

---

## 6. 每阶段的验证矩阵

每完成一个 Phase，至少验证以下内容：

### API 层
- `GET /health`
- 鉴权链路可用
- `POST /api/v1/chat/sync`
- `POST /api/v1/chat/stream`

### Agent 层
- `study` 请求
- `review` 请求
- `plan` 请求
- 工具调用路径
- 流式 token 返回路径

### RAG 层
- 正常检索
- 门控未过时 fallback rewrite
- reranker API 不可用时降级
- trace 能正常给前端消费

### 数据层
- 数据库初始化
- 任务状态读取/更新
- 用户画像读取/更新

### 运行层
- 本地开发启动
- Docker 启动（如果仍维护）
- 关键脚本运行方式不回退

---

## 7. 明确不建议在本轮重构做的事

为避免过度工程化，本轮不建议做以下事情：

1. 不引入复杂的 `ToolBase` / Factory / 插件系统
2. 不新增一层空洞的 `service` 层
3. 不把简单工具拆成过多目录与抽象
4. 不在没有验证收益前替换 ChromaDB
5. 不在同一轮里同时做：
   - Agent 主链路大改
   - RAG 大改
   - DB 迁移
   - 包化全量迁移
6. 不为了“整洁”提前删除所有 legacy 文件

---

## 8. 建议的里程碑产出

### M1：系统进入“可稳步重构”状态
完成 Phase 0 ~ 2

产出：
- 配置统一
- 确定性 bug 修复
- LLM/provider 入口统一
- 有最小回归保护

### M2：系统进入“主链路边界清晰”状态
完成 Phase 3 ~ 4

产出：
- Agent 运行时职责收敛
- RAG 主流程结构清晰
- 前后端主要契约稳定

### M3：系统进入“可持续维护”状态
完成 Phase 5 ~ 8

产出：
- 关键热点文件被治理
- 包化落地
- L2/L4 存储边界统一
- 历史遗留代码退出主路径

---

## 9. 最终结论

对于当前仓库，**最正确的重构方向不是“立刻大拆文件”，而是“分阶段收敛边界、逐步替换历史路径”**。

如果只追求把大文件拆小，技术债会换个形式继续存在；
如果先统一配置、统一 provider、稳定 Agent/RAG 边界，再做拆分和迁移，项目才会真正进入“可持续维护”的状态。

因此，本路线图建议采用以下总策略：

> **先修复确定性问题与统一入口，再治理 Agent/RAG 主链路，最后做包化、数据迁移和遗留清理。**

这是当前仓库在“工程落地优先”前提下，风险最低、收益最高、也最适合持续推进的一条重构路径。
