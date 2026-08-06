# CLAUDE.md

本文件为 Claude Code 提供项目开发指引。

## 项目概述

A 股上市公司多智能体金融分析系统。基于 LangGraph 状态机编排多个 AI Agent，模拟投资研究流程：数据采集 → 多维分析 → 多空辩论 → 报告生成。

核心特征：
- LangGraph 有向图编排，8 个节点线性流转（含一个条件分支）
- 预置专家池 + 智能路由（Supervisor 只做选择题，不动态生成代码）
- 多空对抗辩论，置信度驱动动态终止（非固定轮次）
- 数据全链路溯源，所有数值必须来自数据源或明确公式

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（必须先完成）
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY 等

# 启动 API 服务器（主入口）
python run.py server                    # 默认 127.0.0.1:8000
python run.py server --port 8080        # 自定义端口
python run.py server --reload           # 开发模式热重载

# 直接运行（无子命令，默认启动服务器，PyCharm 右键兼容）
python run.py

# CLI 单次分析
python run.py analyze "分析贵州茅台"
python run.py analyze "600519" --rounds 3

# CLI 交互模式
python run.py interactive

# Streamlit 前端（需先启动 API 服务器）
streamlit run frontend/app.py

# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_calculators.py -v

# 运行单个测试方法
python -m pytest tests/test_calculators.py::TestDupont::test_normal_case -v
```

## 项目结构

```
financial-multi-agent/
├── run.py                          # 统一入口（server / analyze / interactive）
├── src/
│   ├── state.py                    # FinancialAnalysisState + Pydantic 校验模型
│   ├── graph.py                    # LangGraph 图定义、编译、执行
│   ├── config.py                   # 冻结 dataclass 配置，环境变量加载
│   ├── agents/
│   │   ├── base.py                 # FinancialAgentBase 基类（信封校验 + 重试）
│   │   ├── resolver.py             # 实体解析器（LLM 提取 + 别名表 + AKShare 搜索）
│   │   ├── context_agent.py        # 上下文初始化（拉取财务/估值/行情数据）
│   │   ├── supervisor.py           # 监督者（预置专家池 + 关键词粗筛 + LLM 精调路由）
│   │   ├── financial.py            # 4 个子 Agent：财务/行业/舆情/估值
│   │   ├── aggregator.py           # 汇聚器（事实池 + 极性判断 + 冲突检测）
│   │   ├── bull.py                 # 做多方辩论 Agent
│   │   ├── bear.py                 # 做空方辩论 Agent
│   │   ├── arbiter.py              # 辩论仲裁员（规则判定 + LLM 补充）
│   │   └── report.py               # 报告主笔 Agent
│   ├── tools/
│   │   ├── baostock_wrapper.py     # BaoStock 封装（持久连接，atexit 登出）
│   │   ├── akshare_wrapper.py      # AKShare 封装（重试装饰器 + 缓存）
│   │   ├── mcp_stock_wrapper.py    # MCP 中国股票数据（HTTP JSON-RPC 调用公共服务）
│   │   ├── news_fetcher.py         # 新浪财经新闻采集 + 关键词情绪分析
│   │   └── financial_calculators.py # 财务指标计算器（杜邦/DCF/PE/PB 等）
│   ├── api/
│   │   ├── app.py                  # FastAPI 应用工厂（lifespan、CORS、异常处理器、请求日志中间件）
│   │   ├── routes.py               # API 路由（REST + SSE 流式，含 _task_or_404 辅助函数）
│   │   ├── schemas.py              # Pydantic 请求/响应模型（13 个，含 ProgressEvent/TaskListItem）
│   │   ├── tasks.py                # 内存异步任务管理器（TaskRecord 惰性 Event、cleanup_expired）
│   │   └── llm_factory.py          # LLM 实例创建工厂（含 is_llm_configured 配置检查）
│   ├── prompts/
│   │   └── agent_prompts.py        # 所有 Agent 提示词集中管理
│   ├── cache/
│   │   └── sqlite_cache.py         # SQLite 持久化缓存（自动过期清理）
│   └── utils/
│       ├── logger.py               # 彩色日志系统（colorama）
│       ├── html_report.py          # HTML 报告生成
│       ├── export.py               # 多格式导出（PDF/Excel/CSV）
│       ├── charts.py               # matplotlib 图表生成（base64 PNG）
│       ├── citation.py             # 数据溯源脚注管理
│       └── validators.py           # Pydantic 数据校验工具
├── frontend/
│   └── app.py                      # Streamlit 前端
├── tests/                          # pytest 测试
├── data/cache/                     # SQLite 缓存数据库
├── reports/                        # 生成的报告
├── logs/                           # 运行日志
├── requirements.txt
├── .env.example
└── README.md
```

## 架构详解

### LangGraph 状态图

8 个节点，线性流转，`entity_resolver` 后有条件分支：

```
entity_resolver ──→ [条件路由] ──→ context_init ──→ supervisor ──→ sub_agents
                        │
                        └──→ END（未找到匹配）

sub_agents ──→ aggregator ──→ debate ──→ arbiter ──→ report ──→ END
```

节点职责：

| 节点 | Agent 类 | LLM | 职责 |
|------|---------|-----|------|
| `entity_resolver` | `EntityResolver` | light_llm | 从用户输入提取公司名/代码，匹配到唯一 A 股公司 |
| `context_init` | `ContextAgent` | 无 | 拉取财务数据(BaoStock)、估值(AKShare/MCP)、新闻(Sina) |
| `supervisor` | `Supervisor` | light_llm | 关键词粗筛 → LLM 从 4 个预置 Agent 中选 2-4 个激活 |
| `sub_agents` | `_run_sub_agents()` | llm | 逐个执行激活的 Agent，每个只拿到自己的数据子集 |
| `aggregator` | `AggregatorAgent` | 无 | 汇总输出、极性判断(BULL/BEAR/NEUTRAL)、冲突检测 |
| `debate` | `_run_debate()` | llm | Bull vs Bear 辩论，置信度驱动终止 |
| `arbiter` | `ArbiterAgent` | llm | 规则判定胜方 + LLM 生成共识/分歧/风险 |
| `report` | `ReportAgent` | llm | 生成 Markdown 报告，保存到文件 |

### 预置专家池（Supervisor 路由）

```python
AGENT_POOL = {
    "financial_agent":  {capability: "财务健康度分析", keywords: ["财务","盈利","ROE",...], priority: 1},
    "industry_agent":   {capability: "行业竞争格局",   keywords: ["行业","竞争","市占率",...], priority: 2},
    "sentiment_agent":  {capability: "舆情情绪分析",   keywords: ["舆情","新闻","资金",...],   priority: 3},
    "valuation_agent":  {capability: "估值定价分析",   keywords: ["估值","PE","DCF",...],     priority: 4},
}
```

路由流程：关键词匹配（零成本）→ LLM 从候选池选择 → 构建 Agent 注册表 → 精准数据分配。

### 状态设计

`FinancialAnalysisState`（TypedDict）核心字段：

```python
class FinancialAnalysisState(TypedDict):
    messages: Annotated[List[Dict], add]   # 消息历史（add 归约器）
    user_query: str                        # 原始用户问题
    resolved_entity: Optional[Dict]        # 实体解析结果 {stock_code, stock_name, confidence, action}
    shared_context: Optional[Dict]         # 共享数据上下文（财务/估值/行情/新闻）
    agent_registry: List[Dict]             # Supervisor 选中的 Agent 列表
    agent_outputs: Dict[str, Any]          # {agent_id: AgentEnvelope}
    debate_briefing: Optional[Dict]        # 辩论简报（事实池 + 极性）
    debate_history: List[Dict]             # 辩论记录 [{role, round, argument, confidence}]
    debate_consensus: Optional[Dict]       # 仲裁结论
    final_report: Optional[str]            # Markdown 报告文本
    report_id: Optional[str]               # 报告文件路径
    current_phase: str                     # 当前阶段标识
    errors: List[Dict]                     # 错误记录
    start_time: float                      # 流程开始时间戳
```

### Agent 信封模式

所有子 Agent 必须返回经过 Pydantic 校验的 `AgentEnvelope`：

```python
class AgentEnvelope(BaseModel):
    agent_name: str                                    # 中文名称，如 "财务分析"
    status: str                                        # success | partial | failed | timeout
    fact_sheet: Dict[str, Any]                         # 中文指标名 → 数值
    brief_summary: str                                 # ≤1000 字核心结论
    confidence_score: Optional[float]                  # 0-100
```

`fact_sheet` 使用中文字段名：`净资产收益率`、`毛利率`、`资产负债率`、`流动比率`、`净现比` 等。

基类 `FinancialAgentBase` 提供：JSON 解析重试、信封校验、自动补全缺失字段。

### 辩论机制

```
Bull 第1轮 → Bear 第1轮 → 检查终止条件
Bull 第2轮 → Bear 第2轮 → 检查终止条件
...
```

终止条件（满足任一即停）：
1. **达成共识**：双方置信度差 < 15
2. **一方溃败**：任一方置信度 < 20
3. **僵局**：轮次 ≥ 4 且差值 > 40
4. **达到上限**：`max_debate_rounds`（默认 2）

仲裁员 `_determine_winner()` 以规则判定为准，LLM 只补充共识/分歧/风险文字。

### 数据源

| 数据源 | 数据类型 | 稳定性 | 特点 |
|--------|---------|--------|------|
| **BaoStock** | K线、利润表、资产负债表、现金流、成长 | ✅ 稳定 | 持久连接，atexit 登出，默认近 3 年 |
| **AKShare** | 实时估值(PE/PB)、公司信息、行业数据 | ⚠️ 限流 | `@_retry(max_retries=3)` + MCP 降级 |
| **MCP** | 基本信息、行情、资金流向 | ✅ 稳定 | HTTP 调用公共服务 `82.156.17.205` |
| **新浪财经** | 个股新闻 | ✅ 稳定 | httpx 爬取 + 关键词情绪分析 |

降级链：AKShare → MCP → BaoStock → "数据不可用"。

缓存策略：
- BaoStock 数据：24h TTL
- AKShare 估值：1h TTL
- MCP 简要信息：1h TTL
- 新闻数据：1h TTL
- 公司名称表：24h TTL

### 日志系统

```python
from src.utils.logger import get_logger
logger = get_logger(__name__)
```

颜色规则（colorama）：
- `api` 模块 → 白色
- `task` 模块 → 黄色
- 其他模块 → 青色
- WARNING → 黄色
- ERROR → 红色

格式：`时间 - 模块名 - 级别 - 消息`

辅助函数：
- `log_api_request(method, path, status_code, duration_ms)`
- `log_task_event(task_id, event, detail)`
- `log_agent_event(agent_name, event, detail)`
- `log_data_source(source, action, detail)`
- `TaskTimer(task_id)` — 任务级分段计时器

### 输出格式

| 格式 | 生成方式 | 入口 |
|------|---------|------|
| **Markdown** | ReportAgent LLM 生成 | `report.py` |
| **HTML** | Markdown 转 HTML + 数据表格 + 图表嵌入 | `html_report.py` |
| **Excel** | openpyxl 导出（"分析数据" + "辩论结论"两个 Sheet） | `export.py` |
| **CSV** | 与 Excel 同结构 | `export.py` |
| **PDF** | weasyprint（优先）→ fpdf2（降级） | `export.py` |

Excel/CSV 列：`导出时间 | 数据年份 | 数据截止 | 分析模块 | 指标 | 数值 | 状态`

图表类型（matplotlib，base64 PNG）：杜邦瀑布图、财务雷达图、多空置信度对比、K线走势、营收趋势、利润率对比、资金流向饼图。

### API 端点

| 方法 | 路径 | 功能 | 响应模型 |
|------|------|------|---------|
| POST | `/api/analyze` | 提交分析任务 | `AnalyzeResponse` |
| GET | `/api/analyze/{task_id}/stream` | SSE 流式进度 | `ProgressEvent` (SSE) |
| GET | `/api/analyze/{task_id}` | 获取分析结果 | `AnalyzeResult` |
| GET | `/api/reports/{task_id}` | 下载 Markdown 报告 | FileResponse |
| GET | `/api/reports/{task_id}/html` | 在线 HTML 报告预览 | HTMLResponse |
| GET | `/api/reports/{task_id}/excel` | 下载 Excel 数据底稿 | FileResponse |
| POST | `/api/resolve` | 实体解析（支持 LLM 增强，可识别错别字） | `ResolveResponse` |
| GET | `/api/health` | 健康检查 | `HealthResponse` |
| GET | `/api/tasks` | 列出所有任务 | `TaskListResponse` |

任务执行：`BackgroundTasks` 异步执行，`asyncio.wait_for` 超时控制（540 秒），`loop.run_in_executor` 避免阻塞事件循环。

辅助函数（`routes.py`）：
- `_task_or_404(task_id)` — 获取任务，不存在抛 404
- `_completed_task_or_404(task_id)` — 获取已完成任务，未完成抛 404

异常处理（`app.py`）：
- `RequestValidationError` → 422 + 结构化 `{error, detail}`
- `Exception` → 500 + JSON（记录 traceback）

### Pydantic Schema 体系（`api/schemas.py`）

```
请求模型                    响应模型                     内部模型
─────────────              ─────────────               ─────────────
AnalyzeRequest             AnalyzeResponse             ProgressEvent (SSE)
ResolveRequest             AnalyzeResult               TaskListItem
                           ResolveResponse             TaskListResponse
                           HealthResponse
                           ErrorResponse
                           AgentOutputSummary
                           DebateSummary
```

## 关键约定

- 所有 Python 导入使用 `src.` 前缀（`run.py` 将项目根目录加入 `sys.path`）
- 所有财务数值必须来自数据源或明确公式 — LLM 只做推理和解释，不能编造数字
- 每份报告必须包含合规免责声明（定义在 `agent_prompts.py:COMPLIANCE_DISCLAIMER`）
- Pydantic v2 模型用于所有结构化数据校验
- 冻结 dataclass（`frozen=True`）用于配置
- BaoStock 使用持久连接（`_get_bs()` 懒登录，`atexit.register(_logout_bs)` 登出）
- Agent 名称和 `fact_sheet` 键名使用中文（`财务分析`、`净资产收益率`）
- Streamlit 使用 `width="stretch"` 替代已弃用的 `use_container_width=True`
- Streamlit 使用 `st.html()` 替代已弃用的 `st.components.v1.html()`
- API 路由中使用 `_task_or_404()` / `_completed_task_or_404()` 统一任务查询和 404 处理
- LLM 配置检查使用 `is_llm_configured()`（不抛异常），创建实例用 `create_llm()`（缺 Key 抛 ValueError）
- SSE 进度事件使用 `ProgressEvent` Pydantic 模型（`model_dump_json()` 序列化）
- `asyncio.Event` 必须惰性创建（`_ensure_event()`），不能在 `__init__` 中直接创建
- 提交分析任务时自动调用 `cleanup_expired()` 防止内存泄漏
- `/api/resolve` 默认 `use_llm=true`，通过 `_get_resolve_llm()` 惰性创建轻量 LLM 单例；LLM 不可用时自动降级到纯规则匹配

## 环境变量

必需：
- `LLM_API_KEY` — LLM API 密钥

可选（有默认值）：
- `LLM_PROVIDER` — 提供商（默认 `openai`）
- `LLM_MODEL` — 主模型 ID（默认 `mimo-v2.5-pro`）
- `LLM_LIGHT_MODEL` — 轻量模型 ID（默认 `mimo-v2.5`）
- `LLM_BASE_URL` — API 基础 URL
- `LLM_TEMPERATURE` — 温度（默认 `0.1`）
- `LLM_MAX_TOKENS` — 最大 Token（默认 `4096`）
- `SQLITE_DB_PATH` — 缓存数据库路径
- `MAX_DEBATE_ROUNDS` — 辩论最大轮次（默认 `2`）
- `REPORT_OUTPUT_DIR` — 报告输出目录
- `LOG_LEVEL` — 日志级别（默认 `INFO`）

完整列表见 `.env.example`。
