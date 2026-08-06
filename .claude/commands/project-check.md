# 项目完整检查与技术文档更新

对整个项目进行全面检查、修复、测试，并更新技术文档。

## 执行步骤

### 第一阶段：项目扫描

1. 列出所有 Python 源文件（排除 .venv）：
   ```bash
   find . -type f -name "*.py" -not -path "./.venv/*" | sort
   ```

2. 逐文件阅读以下核心模块，记录发现的问题：
   - `src/state.py` — 状态定义和 Pydantic 模型
   - `src/graph.py` — LangGraph 图编排
   - `src/config.py` — 配置管理
   - `src/agents/` — 所有 Agent 文件
   - `src/tools/` — 所有数据源封装
   - `src/api/` — API 模块（schemas, routes, tasks, app, llm_factory）
   - `src/prompts/agent_prompts.py` — 提示词
   - `src/utils/` — 工具模块
   - `src/cache/sqlite_cache.py` — 缓存
   - `frontend/app.py` — Streamlit 前端
   - `tests/` — 所有测试文件

3. 读取 `requirements.txt` 和 `.env.example` 确认依赖和配置完整性

### 第二阶段：问题诊断

逐项检查以下维度：

**A. 导入兼容性**
- 检查所有 `from src.xxx import yyy` 是否实际存在
- 检查函数签名是否与调用方一致
- 检查 Pydantic 模型字段是否与使用方匹配

**B. 跨模块一致性**
- Agent 名称是否在所有地方保持一致（中文名）
- fact_sheet 键名是否在 aggregator、prompts、html_report 中一致
- 状态字段名是否在 graph.py、agents、state.py 中一致
- API schemas 是否与 routes.py 的返回值匹配

**C. 数据流完整性**
- 从用户输入到最终报告的完整数据流是否通畅
- 每个节点的输入/输出是否与 state 定义匹配
- 缓存 key 是否在所有使用处一致

**D. 配置可扩展性**
- 环境变量是否都有默认值
- .env.example 是否覆盖所有 config.py 中的配置项
- LLM 配置是否支持多提供商切换

**E. 错误处理**
- 所有外部调用（API、数据库、网络）是否有 try/except
- 失败时是否有降级策略
- 错误信息是否对用户友好

### 第三阶段：修复

对发现的每个问题：
1. 说明问题所在文件和行号
2. 说明影响范围（哪些模块受影响）
3. 实施修复
4. 验证修复不破坏其他模块

### 第四阶段：测试

```bash
python -m pytest tests/ -v --tb=short
```

- 确保所有测试通过
- 如果测试失败，分析原因并修复（可能是代码变更导致，也可能是测试本身需要更新）
- 如果发现测试覆盖不足的区域，补充测试

### 第五阶段：导入链验证

```bash
python -c "
from run import app
from src.graph import compile_graph
from src.api.routes import router
from src.api.schemas import *
from src.api.tasks import *
from src.api.llm_factory import *
# ... 验证所有模块可正常导入
print('All imports OK')
"
```

### 第六阶段：更新技术文档

读取当前 `CLAUDE.md`，根据检查结果更新：

1. **项目结构** — 如果有新增/删除/重命名的文件
2. **架构详解** — 如果有节点变化、数据流变化
3. **API 端点表** — 如果有新增/修改的端点
4. **Pydantic Schema 体系** — 如果有新增/修改的模型
5. **关键约定** — 如果有新的编码约定
6. **环境变量** — 如果有新增的配置项
7. **常用命令** — 如果有新的运行方式
8. **数据源** — 如果有数据源变化

### 输出格式

最终输出一份检查报告：

```
## 项目检查报告

### 发现的问题
1. [严重] 文件:行号 — 问题描述
2. [中等] 文件:行号 — 问题描述
3. [轻微] 文件:行号 — 问题描述

### 已修复
- 问题1: 修复方式
- 问题2: 修复方式

### 测试结果
- 总测试数: N
- 通过: N
- 失败: N

### 文档更新
- 更新了哪些章节
- 新增了哪些内容
```
