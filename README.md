# A 股上市公司多智能体金融分析系统

基于 **LangGraph 状态机**编排多个 AI Agent 的 A 股投资研究分析系统。模拟专业投研流程：**数据采集 → 多维分析 → 多空辩论 → 报告生成**，输出带数据溯源的完整分析报告。

---

## ✨ 核心特性

- **LangGraph 有向图编排** — 8 个节点线性流转，实体解析后带条件分支（未匹配公司自动终止）
- **预置专家池 + 智能路由** — Supervisor 关键词粗筛 + LLM 精调，从 4 个预置专家中按需激活 2-4 个（节省 Token），Supervisor 只做"选择题"，不动态生成代码
- **多空对抗辩论** — Bull vs Bear 多轮辩论，**置信度驱动动态终止**（共识 / 溃败 / 僵局 / 上限四种条件，而非固定轮次）
- **数据全链路溯源** — 所有数值必须来自数据源或明确公式，LLM 只做推理和解释，不能编造数字
- **多格式输出** — Markdown / HTML（含图表）/ Excel 数据底稿 / CSV / PDF
- **异步 API + SSE 流式进度** — FastAPI 后端 + Streamlit 前端，实时观察分析进展

## 🏗️ 系统架构

```
用户输入 ──→ entity_resolver ──→ [条件路由] ──→ context_init ──→ supervisor ──→ sub_agents
                  │                                                        （按需激活 2-4 个专家）
                  └──→ END（未找到匹配）                                        │
                                                                             ▼
              report ◄── arbiter ◄── debate ◄── aggregator ◄─────────────────┘
              （报告）    （仲裁）    （多空辩论）   （汇聚+极性判断）
```

| 节点 | LLM | 职责 |
|------|-----|------|
| `entity_resolver` | 轻量 | 从用户输入提取公司名/代码，支持错别字纠正（如"嗨康威视"→"海康威视"）和自然语言描述 |
| `context_init` | 无 | 拉取财务（BaoStock）、估值（AKShare/MCP）、新闻（新浪财经）数据 |
| `supervisor` | 轻量 | 关键词粗筛 → LLM 从预置专家池中选择激活哪些 Agent → 精准数据分配 |
| `sub_agents` | 主 | 逐个执行激活的专家，**每个只拿到自己的数据子集**（数据隔离） |
| `aggregator` | 无 | 汇总事实池、极性判断（BULL/BEAR/NEUTRAL）、冲突检测与 LLM 冲突解析 |
| `debate` | 主 | Bull vs Bear 辩论，置信度驱动终止（差值<15 共识、任一方<20 溃败、4 轮且差>40 僵局） |
| `arbiter` | 主 | 规则判定胜方 + LLM 补充共识/分歧/风险 |
| `report` | 主 | 生成 Markdown 报告（含合规免责声明），保存到文件 |

### 预置专家池

| Agent | 能力 | 典型关键词 |
|-------|------|-----------|
| `financial_agent` | 财务健康度：杜邦分解、盈利质量、偿债能力、现金流质量 | 财务、ROE、毛利率、现金流 |
| `industry_agent` | 行业竞争格局与产业链地位 | 行业、竞争、市占率、护城河 |
| `sentiment_agent` | 舆情与市场情绪、资金流向 | 舆情、新闻、资金、机构 |
| `valuation_agent` | DCF 绝对估值 + PE/PB 相对估值 | 估值、PE、DCF、目标价 |

### 数据源与降级链

| 数据源 | 数据类型 | 特点 |
|--------|---------|------|
| **BaoStock** | K线、三大报表、成长指标 | 稳定，持久连接 + atexit 登出，默认近 3 年 |
| **AKShare** | 实时估值（PE/PB）、公司信息、行业数据 | 限流，带重试装饰器 + 缓存 |
| **MCP** | 基本信息、行情、资金流向 | HTTP JSON-RPC 调用公共服务 |
| **新浪财经** | 个股新闻 | httpx 爬取 + 关键词情绪分析 |

降级链：**AKShare → MCP → BaoStock → "数据不可用"**，SQLite 持久化缓存（分数据源 TTL，自动过期清理）。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少设置 LLM_API_KEY
```

必需变量：

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | LLM API 密钥（必需） |
| `LLM_PROVIDER` | 提供商，默认 `openai` |
| `LLM_MODEL` | 主模型 ID（辩论、报告生成） |
| `LLM_LIGHT_MODEL` | 轻量模型 ID（实体解析、路由） |
| `LLM_BASE_URL` | API 基础 URL（兼容任何 OpenAI 协议服务） |

完整列表见 `.env.example`。

### 3. 启动系统

```bash
# 方式一：启动 API 服务器（主入口，默认 127.0.0.1:8000）
python run.py server
python run.py server --port 8080 --reload   # 自定义端口 + 热重载

# 方式二：CLI 单次分析
python run.py analyze "分析贵州茅台"
python run.py analyze "600519" --rounds 3

# 方式三：CLI 交互模式
python run.py interactive

# 方式四：Streamlit 前端（需先启动 API 服务器）
streamlit run frontend/app.py
```

### 4. 运行测试

```bash
# 全部测试
python -m pytest tests/ -v

# 单个测试文件 / 测试方法
python -m pytest tests/test_calculators.py -v
python -m pytest tests/test_calculators.py::TestDupont::test_normal_case -v
```

## 📡 API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/analyze` | 提交分析任务（异步，立即返回 task_id） |
| GET | `/api/analyze/{task_id}/stream` | SSE 流式进度（阶段 + 百分比） |
| GET | `/api/analyze/{task_id}` | 获取分析结果 |
| GET | `/api/reports/{task_id}` | 下载 Markdown 报告 |
| GET | `/api/reports/{task_id}/html` | 在线 HTML 报告预览（含图表） |
| GET | `/api/reports/{task_id}/excel` | 下载 Excel 数据底稿 |
| POST | `/api/resolve` | 实体解析（LLM 增强，可识别错别字） |
| GET | `/api/health` | 健康检查（LLM 配置、缓存统计） |
| GET | `/api/tasks` | 列出所有任务 |

任务执行采用 `BackgroundTasks` + 540 秒超时控制，SSE 进度通过 `ProgressEvent` 模型序列化输出。

## 📁 项目结构

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
│   │   ├── supervisor.py           # 监督者（预置专家池 + 智能路由）
│   │   ├── financial.py            # 4 个子 Agent：财务/行业/舆情/估值
│   │   ├── aggregator.py           # 汇聚器（事实池 + 极性判断 + 冲突检测）
│   │   ├── bull.py / bear.py       # 多空辩论双方
│   │   ├── arbiter.py              # 辩论仲裁员（规则判定 + LLM 补充）
│   │   └── report.py               # 报告主笔
│   ├── tools/                      # BaoStock / AKShare / MCP / 新闻 / 财务计算器封装
│   ├── api/                        # FastAPI 应用、路由、Schema、任务管理器、LLM 工厂
│   ├── prompts/agent_prompts.py    # 所有 Agent 提示词集中管理
│   ├── cache/sqlite_cache.py       # SQLite 持久化缓存
│   └── utils/                      # 日志、HTML 报告、导出、图表、溯源、校验
├── frontend/app.py                 # Streamlit 前端
├── tests/                          # pytest 测试
├── data/cache/                     # SQLite 缓存数据库
├── reports/                        # 生成的报告
└── logs/                           # 运行日志
```

## 🔑 关键设计

- **Agent 信封模式** — 所有子 Agent 返回经过 Pydantic 校验的 `AgentEnvelope`（`fact_sheet` 中文指标名 + `brief_summary` + `confidence_score`），基类提供 JSON 解析重试与字段自动补全
- **Sub-agent 数据隔离** — 每个子 Agent 只注入自己的 `data_subset` + 基础标识，不暴露完整 `shared_context`
- **共享 JSON 解析** — `validators.parse_json_response()` 三段式回退（直接解析 → 代码块提取 → 花括号扫描），禁止各 Agent 重复拷贝
- **辩论与仲裁条件一致** — 终止条件与仲裁员 `_determine_winner()` 判定逻辑保持同步
- **Checkpointer** — 已启用 `MemorySaver`，所有 `invoke()` / `astream()` 调用必须传 `thread_id`
- **中文命名约定** — Agent 名称与 `fact_sheet` 键名使用中文（`财务分析`、`净资产收益率`），风险信号键名中英文兼容

## ⚠️ 免责声明

本系统生成的所有分析报告仅供研究与学习参考，不构成任何投资建议。股市有风险，投资需谨慎。

## 📄 许可证

仅供个人学习与研究使用。
