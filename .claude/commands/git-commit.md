# Git 安全提交管理

管理本地项目库的 Git 提交，确保隐私安全。自动检测敏感文件、校验 .gitignore 完整性、生成规范提交信息。

## 执行步骤

### 第一阶段：安全扫描

在任何 Git 操作前，先进行隐私安全检查：

1. **检测敏感文件**：
   ```bash
   # 检查是否有敏感文件被跟踪或即将被提交
   git status --short
   ```

2. **敏感文件清单**（以下文件绝对不能提交）：
   - `.env` — 包含 API Key、密码等真实凭据
   - `*.db` — SQLite 缓存数据库（可能含用户数据）
   - `*.log` — 日志文件（可能含请求信息、Token 等）
   - `__pycache__/` — Python 字节码
   - `.venv/` — 虚拟环境（含已安装的包）
   - `data/cache/` — 缓存数据
   - `logs/` — 运行日志
   - `reports/*.md` — 生成的报告（可能含分析结果）
   - `.idea/`、`.vscode/` — IDE 配置（含个人路径）
   - `*.pyc` — 编译文件

3. **检查 .gitignore 完整性**：
   - 确认 `.env` 在 .gitignore 中
   - 确认 `data/cache/` 在 .gitignore 中
   - 确认 `logs/` 在 .gitignore 中
   - 确认 `.venv/` 在 .gitignore 中
   - 如果缺失，自动补充

4. **检查已跟踪文件中是否有敏感内容**：
   ```bash
   git ls-files | grep -E '\.(env|db|log|pyc)$'
   ```
   如果有，警告用户并提供移除命令

### 第二阶段：变更分析

1. **查看变更概览**：
   ```bash
   git status --short
   git diff --stat
   ```

2. **分类变更**：
   - 新增文件（`??` 或 `A`）
   - 修改文件（`M`）
   - 删除文件（`D`）
   - 重命名文件（`R`）

3. **检查变更中是否混入敏感信息**：
   - 搜索 diff 中是否包含 `api_key`、`secret`、`password`、`token` 等关键词
   - 如果发现，警告用户确认

### 第三阶段：暂存与提交

1. **询问用户提交范围**：
   - 全部提交（`git add .`）
   - 选择性提交（逐文件确认）
   - 按模块提交（src/、tests/、frontend/ 等）

2. **生成提交信息**：
   根据变更内容自动生成规范的提交信息，格式：
   ```
   <类型>: <简要描述>

   <详细说明（可选）>

   变更文件:
   - file1.py: 变更说明
   - file2.py: 变更说明
   ```

   类型枚举：
   - `feat` — 新功能
   - `fix` — 修复
   - `refactor` — 重构
   - `docs` — 文档
   - `test` — 测试
   - `chore` — 杂项

3. **执行提交**：
   ```bash
   git add <files>
   git commit -m "<message>"
   ```

### 第四阶段：提交后验证

1. **确认提交成功**：
   ```bash
   git log --oneline -1
   git status
   ```

2. **检查是否有敏感文件意外提交**：
   ```bash
   git show --stat HEAD
   ```

3. **如果发现敏感文件被提交**：
   - 立即警告用户
   - 提供 `git reset HEAD~1` 撤销命令
   - 提供从 Git 历史中移除敏感文件的命令

## 安全规则（不可妥协）

1. **绝对不提交**：`.env` 文件中的真实 API Key
2. **绝对不提交**：数据库文件（`.db`）
3. **绝对不提交**：日志文件（`.log`）
4. **绝对不提交**：虚拟环境（`.venv/`）
5. **绝对不提交**：IDE 个人配置（`.idea/`、`.vscode/`）
6. **提交前必须**：检查 diff 中是否有硬编码的密钥或密码
7. **提交前必须**：确认 .gitignore 覆盖所有敏感路径

## .gitignore 模板

如果项目缺少 .gitignore，自动创建包含以下内容：

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
*.egg

# Virtual environment
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Environment (敏感!)
.env
.env.local
.env.*.local

# Data (缓存和数据库)
data/cache/*.db
data/chroma/
*.sqlite3

# Reports (生成物)
reports/*.md
reports/*.html
reports/*.xlsx
reports/*.pdf

# Logs (可能含敏感信息)
logs/
*.log

# OS
.DS_Store
Thumbs.db

# Pytest
.pytest_cache/

# Coverage
.coverage
htmlcov/
```

## 使用示例

```
/project-check     # 先执行项目检查
/git-commit        # 再安全提交
```
