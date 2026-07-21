# 政府项目申报智能体

面向政府科研项目、科技计划项目、专项资金项目等申报场景的本地 Web 智能体。

- 前端 Web：`http://127.0.0.1:9527`
- 后端 Gateway：`http://127.0.0.1:10086`
- GitHub：<https://github.com/xh92117/Goverment-Project-Agent>

## 1. 项目简介

本项目基于字节跳动开源项目 [DeerFlow](https://github.com/bytedance/deer-flow) 进行二次开发，
不是 DeerFlow 官方发行版。项目保留 DeerFlow / Agent Base 的智能体运行时、工具调用、工作区、
技能和多智能体基础能力，并针对中国政府项目申报流程进行了场景化改造。

主要二次开发内容包括：

- 政策指南、申报通知和模板的结构化分析。
- 不依赖 Embedding 模型的增强词法检索与检索质量评测。
- 按“用户 + 项目”隔离的长期记忆，区分已确认事实和待核验假设。
- 将多智能体角色扮演改为指南、调研、写作、预算、合规等异构专家协作。
- 申报资料、图像证据、草稿、Word 导出和项目工作区管理。
- 面向申报流程的技能、提示词、工具权限和证据追溯机制。

本项目适合用于申报辅助、材料整理和合规检查。模型生成内容不能替代主管部门正式文件、
专业财务意见、法律意见或人工最终审核。

## 2. 项目结构

```text
Goverment-Project-Agent/
├─ backend/                  FastAPI Gateway、智能体运行时、工具和后端测试
│  ├─ app/                   Web API、认证、项目、知识库和导出接口
│  ├─ packages/harness/      DeerFlow / Agent Base 核心运行时
│  └─ tests/                 后端单元、集成和质量评测
├─ frontend/                 Next.js 16 + React 19 前端
│  ├─ src/                   页面、功能模块、组件和样式
│  └─ tests/                 前端 Vitest 测试
├─ configs/                  基础配置及政府申报智能体配置示例
├─ contracts/                智能体交接和状态契约
├─ docker/                   Docker Compose、Nginx 和沙箱配置
├─ scripts/                  安装、诊断、测试、索引和部署脚本
├─ skills/public/            政府项目申报及通用技能
├─ config.example.yaml       根应用完整配置模板
├─ extensions_config.example.json  扩展配置模板
├─ .env.example              环境变量模板
├─ start.bat                 Windows 依赖检查、安装和启动入口
├─ start_web_agent.py        Windows 本地前后端进程启动脚本
└─ LICENSE                   MIT 许可证
```

默认运行数据与源码分离。当前启动脚本的默认目录为：

```text
%USERPROFILE%\GP Agent
├─ .agent-base\              数据库、线程和运行状态
├─ workspace\
   ├─ knowledge_base\        知识库
   ├─ proposal_drafts\       申报草稿
   └─ projects\              项目资料
└─ logs\                      前后端启动日志

```



### 2.1 服务器多用户隔离

生产 Docker 部署默认开启本地用户系统和严格用户上下文。智能体框架、内置工具、模型、MCP 和公共 Skills 由所有用户共用；线程、项目、草稿、上传、产物、沙箱、缓存、记忆、私有知识库及租户日志按账号写入 `AGENT_BASE_HOME/users/{user_id}/`。模型、MCP、Skills、系统设置、渠道配置和公共知识库的写操作仅限管理员。

`AGENT_BASE_KNOWLEDGE_ROOT` 是独立的公共知识库，用户私有知识库位于各自的 `users/{user_id}/knowledge_base/`。智能体检索会自动合并“当前用户私有库 + 公共库”，不会检索其他用户的私有库。部署、迁移、权限和验收步骤见 [多用户隔离与公共知识库部署指南](docs/MULTI_USER_ISOLATION.md)。

启用内置用户系统后，前端提供 `/setup`（首位管理员初始化）、`/login`（登录）和 `/register`（普通用户注册）三条认证路由；工作台会在加载业务数据前验证会话，登录后在左侧栏显示当前账号与角色，退出时清除浏览器内的用户查询缓存。若后端未启用本地认证，认证状态接口返回 404，前端会自动保持原有的无登录直达工作台模式，无需修改现有使用方式。

## 3. 环境要求

推荐使用 Windows 10/11 和 PowerShell。项目的本地一键启动脚本已按 Windows 环境优化。

| 组件    | 要求                                       |
| ------- | ------------------------------------------ |
| Git     | 用于克隆和更新源码                         |
| Python  | `3.12.x`，后端要求 `>=3.12`                |
| uv      | Python 依赖和虚拟环境管理                  |
| Node.js | 推荐 `22 LTS`                              |
| pnpm    | `10.26.2`，建议通过 Corepack 安装          |
| Nginx   | Windows 原生启动时可选；本地反向代理模式需要 |
| 网络    | 首次安装依赖、调用在线模型或联网检索时需要 |
| Docker  | 可选，仅容器沙箱或 Docker 部署需要         |

建议至少预留数 GB 磁盘空间；如运行本地大模型，CPU、内存和显存要求由所选模型决定。
Windows 使用 `start_web_agent.py` 时不需要安装 nginx，`make check` 和 `make doctor`
会将缺少 nginx 标记为可选警告；Docker 模式使用容器内的 nginx。

检查已安装版本：

```powershell
git --version
python --version
node --version
pnpm --version
uv --version
```

## 4. 首次安装

### 4.1 从 GitHub 下载源码

#### 方式一：Git 直接下载

```powershell
git clone https://github.com/xh92117/Goverment-Project-Agent.git
Set-Location .\Goverment-Project-Agent
```

#### 方式二：通过本地代理端口下载

以下示例使用 HTTP/Mixed 代理端口 `7890`。该端口只是示例，必须替换为代理软件的
实际监听端口，并先确认端口可连接：

```powershell
$proxyPort = 7890
$proxyUrl = "http://127.0.0.1:$proxyPort"
Test-NetConnection 127.0.0.1 -Port $proxyPort

git -c "http.proxy=$proxyUrl" clone https://github.com/xh92117/Goverment-Project-Agent.git
Set-Location .\Goverment-Project-Agent
```

只有检测结果为 `TcpTestSucceeded : True` 时，该代理端口才能使用。上述 `git -c`
配置只对本次克隆生效，不会影响后续依赖安装。

也可以临时设置当前 PowerShell 会话的代理：

```powershell
$proxyPort = 7890
$proxyUrl = "http://127.0.0.1:$proxyPort"
$env:HTTP_PROXY = $proxyUrl
$env:HTTPS_PROXY = $proxyUrl
git clone https://github.com/xh92117/Goverment-Project-Agent.git
Set-Location .\Goverment-Project-Agent
```

`HTTP_PROXY` 和 `HTTPS_PROXY` 会被同一 PowerShell 窗口中随后运行的 `uv`、`pnpm`
和 `make install` 继承。代理软件必须保持运行且端口正确；下载完成后如不再使用代理，
应在安装依赖前清除当前会话变量：

```powershell
Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue
```

#### 方式三：浏览器直接下载 ZIP

打开仓库页面，选择 **Code → Download ZIP**，或直接访问：

<https://github.com/xh92117/Goverment-Project-Agent/archive/refs/heads/main.zip>

使用 PowerShell 和代理下载 ZIP：

```powershell
$proxyPort = 7890
$proxyUrl = "http://127.0.0.1:$proxyPort"

Invoke-WebRequest `
  -Uri "https://github.com/xh92117/Goverment-Project-Agent/archive/refs/heads/main.zip" `
  -Proxy $proxyUrl `
  -OutFile ".\Goverment-Project-Agent.zip"

Expand-Archive ".\Goverment-Project-Agent.zip" -DestinationPath "." -Force
Set-Location ".\Goverment-Project-Agent-main"
```

### 4.2 安装基础工具

确认已安装 Python 3.12 和 Node.js 22，然后执行：

```powershell
python -m pip install --upgrade uv
corepack enable
corepack prepare pnpm@10.26.2 --activate
```

如果 `corepack` 不可用，可以使用：

```powershell
npm install --global pnpm@10.26.2
```

### 4.3 安装后端依赖

在项目根目录执行：

```powershell
Push-Location .\backend
$env:UV_PROJECT_ENVIRONMENT = "..\.venv"
uv sync --locked

# 推荐功能集：MCP、联网检索和文档解析
uv pip install `
  --python "..\.venv\Scripts\python.exe" `
  --editable ".\packages\harness[mcp,search,documents]"
Pop-Location
```

如果使用 Gemini 或 Ollama，可在上述可选依赖列表中分别加入 `google` 或 `ollama`。
知识图片与 Word 图片导出在后端启动时会导入 Pillow；Pillow 已列为 Harness 基础依赖，
执行 `uv sync --locked` 或 `make install` 会自动安装，无需再手动补装。
OpenAI 兼容接口、Anthropic Claude 和 DeepSeek 的模型适配包也已列为基础依赖，选择这些
模型时不需要再单独安装 `openai`、`anthropic` 或 `deepseek` extra。

### 4.4 安装前端依赖

```powershell
Push-Location .\frontend
pnpm install --frozen-lockfile
Pop-Location
```

前端依赖会安装到 `frontend/node_modules`；pnpm 的共享缓存保存在根目录
`.venv/pnpm-store`。项目已启用复制与提升模式，以减少 Windows 因符号链接权限导致的
`ERR_PNPM_EPERM` 安装失败。

如果访问 npm 官方源较慢，推荐通过仅对当前 PowerShell 窗口生效的临时代理安装。
以下示例仍使用 `7890`，请替换为代理软件的实际 HTTP/Mixed 端口：

```powershell
$proxyPort = 7890
$proxyUrl = "http://127.0.0.1:$proxyPort"

if (-not (Test-NetConnection 127.0.0.1 -Port $proxyPort -InformationLevel Quiet)) {
    throw "本地代理端口 $proxyPort 未监听，请启动代理或修改端口。"
}

$env:HTTP_PROXY = $proxyUrl
$env:HTTPS_PROXY = $proxyUrl

Push-Location .\frontend
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) {
        throw "pnpm install 执行失败，退出码：$LASTEXITCODE"
    }
}
finally {
    Pop-Location
    Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
}
```

如果决定不使用代理，应同时清除当前会话变量和可能存在的持久配置，然后直接重试安装：

```powershell
Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue

pnpm config delete proxy
pnpm config delete https-proxy
npm config delete proxy
npm config delete https-proxy

Push-Location .\frontend
pnpm install --frozen-lockfile
Pop-Location
```

失败后不需要删除 `pnpm-lock.yaml`、`node_modules` 或 pnpm 缓存；修正网络或代理配置后，
pnpm 会继续复用已经下载的依赖。

如果已安装 Make，也可以用以下命令安装基础依赖：

```powershell
make install
```

`make install` 会继承当前 PowerShell 环境变量和 pnpm 持久代理配置。执行前应确认代理
仍在运行且端口正确，或者按上述命令先清除不再使用的代理。

### 4.5 创建本地配置

首次安装时，在项目根目录执行：

```powershell
Copy-Item ".\.env.example" ".\.env"
Copy-Item ".\config.example.yaml" ".\config.yaml"
Copy-Item ".\extensions_config.example.json" ".\extensions_config.json"
```

如果目标文件已经存在，不要覆盖，直接编辑现有文件。

政府申报专用配置示例位于：

- `configs/government-project-declaration.agent.example.yaml`
- `configs/government-project-declaration.subagents.example.yaml`
- `configs/government-project-declaration.SOUL.example.md`

其中 `subagents` 片段需要合并到根 `config.yaml` 的同名配置段；Agent 示例用于创建
`government-project-declaration` 自定义智能体目录。

### 4.6 配置模型

真实 API Key 只写入 `.env`，不要直接提交到 `config.yaml` 或 GitHub。

通过前端“设置 → 模型供应商”新增或更新模型时，后端也遵循同一规则：真实密钥写入
项目根目录 `.env`，`config.yaml` 的模型条目只保存 `$环境变量名` 引用。模型配置历史
快照不会保存明文密钥。

DeepSeek 最小示例：

```env
DEEPSEEK_API_KEY=你的实际APIKey
```

在 `config.yaml` 的 `models:` 下配置模型：

```yaml
models:
  - name: deepseek-chat
    display_name: DeepSeek Chat
    use: deerflow.models.patched_deepseek:PatchedChatDeepSeek
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
    request_timeout: 600
    max_retries: 2
```

> `config.yaml` 中的 `deerflow.*` 和安装环境中的 `deerflow-harness` 是继承自上游的
> Python 包名与动态导入路径。它们属于运行时兼容接口，不代表当前项目的产品名称，请勿
> 直接批量替换；面向用户的安装提示、页面和文档使用“政府项目申报智能体”名称。

OpenAI 或其他 OpenAI 兼容接口示例：

```env
OPENAI_API_KEY=你的实际APIKey
```

```yaml
models:
  - name: openai-compatible
    display_name: OpenAI Compatible
    use: langchain_openai:ChatOpenAI
    model: 你的模型名称
    api_key: $OPENAI_API_KEY
    base_url: https://你的服务地址/v1
    request_timeout: 600
    max_retries: 2
    supports_vision: false
```

如模型支持图片理解，将 `supports_vision` 设置为 `true`，并可在 `config.yaml` 中使用
`knowledge_image_model` 指定知识库图片识别模型。

可选搜索和 PDF 解析配置：

```env
SERPER_API_KEY=你的SerperKey
JINA_API_KEY=你的JinaKey
MINERU_API_TOKEN=你的MinerUToken
MINERU_API_BASE_URL=https://mineru.net
```

安装完成后可执行基础检查：

```powershell
python .\scripts\check.py
```

## 5. 智能体启动

Windows 推荐从项目根目录双击 `start.bat`，或在 PowerShell 中执行：

```powershell
.\start.bat
```

脚本会先检查 Node.js 版本、Pillow 和核心模型适配器等后端关键依赖、Next.js 依赖以及依赖清单是否变化。依赖齐全时直接启动；
缺失或依赖清单变化时，会自动安装 `uv`/`pnpm`（如有需要）、同步前后端依赖，再启动服务。
Node.js 需要预先安装 22 或更高版本，因为批处理无法可靠地替用户选择系统级 Node.js 安装方式。

服务就绪后，启动脚本会先预热主要前端模块，再使用系统默认浏览器打开 Web 页面。新电脑第一次启动时，预热可能需要几十秒；
这段等待用于完成 Next.js 首次编译，避免进入页面后第一次点击模块时长时间无响应。如需禁止自动打开浏览器，可传入
`--no-open-browser`。

`start.bat` 支持将参数继续传给启动脚本，例如：

```powershell
.\start.bat --network-proxy "http://127.0.0.1:7897"
```

```powershell
.\start.bat --no-open-browser
```

也可以手动启动前端和后端：

```powershell
& ".\.venv\Scripts\python.exe" ".\start_web_agent.py"
```

启动成功后访问：

- 前端：<http://127.0.0.1:9527>
- 后端健康检查：<http://127.0.0.1:10086/health>


自定义端口：

```powershell
& ".\.venv\Scripts\python.exe" ".\start_web_agent.py" `
  --backend-port 10087 `
  --frontend-port 9528
```

启动日志默认位于 `%USERPROFILE%\GP Agent\logs`，也可通过前端存储目录设置或
`.env` 中的 `GOVERNMENT_PROJECT_LOG_ROOT` 修改。前台运行时按 `Ctrl+C` 可同时停止前后端。

## 6. 基本使用流程

1. 打开 <http://127.0.0.1:9527>。
2. 在“项目”页面新建项目，为不同申报任务使用不同项目，避免记忆和材料串用。
3. 填写或说明申报年份、主管部门、项目类别、申报单位、技术方向和截止时间。
4. 上传申报通知、指南、模板、历史材料、团队成果、专利、论文和预算依据。
5. 在知识库页面整理新增资料并构建索引；图片证据需人工确认后才能作为已核实事实使用。
6. 先让智能体分析申报指南、资格条件、评分点、材料清单和禁止事项。
7. 再进行选题规划、研究现状调研、研究方案编写、预算编制和合规审查。
8. 将可复用章节保存到项目草稿，按需导出 Markdown 或 Word。
9. 提交前由人工逐项核对官方要求、数字、名称、证明材料和预算数据。

示例任务：

```text
请基于知识库中的 2026 年省重点研发计划指南，提取申报条件、支持方向、考核指标、
材料清单和截止时间，并标出需要人工确认的内容。
```

```text
请结合当前项目资料，规划 5 个智能检测方向的候选课题，说明指南匹配度、单位基础、
创新性、实施风险和推荐排序。
```

```text
请审查当前申报书草稿，按 P0/P1/P2 列出指南不符合项、逻辑冲突、预算风险、缺失证据
和可直接执行的修改建议。
```

## 7. 本智能体功能简介

### 政策指南与模板分析

提取申报对象、资格条件、支持方向、截止时间、材料清单、评分重点、预算限制和否决条款，
并优先使用当前有效的官方文件作为依据。

### 知识库与无 Embedding 检索

支持 PDF、Word、Markdown、TXT、CSV、Excel 和常见图片资料。当前检索不要求安装或部署
Embedding 模型，通过多路词法查询、同义词扩展、字段加权、年份/部门/文种过滤和
Golden Set 评测提高召回质量，并减少历史材料污染当前政策结论。

### 图像证据管理

证书、专利、奖项、截图等图片按申报主体隔离存储。图片默认处于待复核状态，只有
`human_verified` 证据可以作为已确认申报事实或插入 Word 成品。

### 项目绑定长期记忆

记忆按“用户 + `project_id`”隔离。人工确认内容进入 `confirmedFacts`，模型从对话抽取的
内容只能进入 `workingAssumptions`；当前不启用跨项目梦境蒸馏，降低长期记忆污染风险。

### 异构专家协作

多智能体不是人格化角色扮演，而是按工具、模型、权限和交付物划分的专家协作：

- `guide-analyzer`：政策指南、模板和资格条件。
- `knowledge-manager`：资料整理和知识库索引。
- `topic-planner`：课题方向和项目名称规划。
- `literature-researcher`：研究现状、文献和技术趋势。
- `standards-patent-researcher`：标准、专利、检测方法和工程应用。
- `proposal-writer`：依据已确认决策和证据撰写申报章节。
- `budget-analyst`：预算拆解、测算和说明。
- `compliance-reviewer`：只读独立审查和风险分级。

主智能体负责拆解、调度、证据冲突裁决和最终整合，不以多个模型重复同一观点作为真实性依据。

子智能体的开关和额度由服务端统一约束：`subagents.enabled` 是全局总开关；标准/深度模式每次
主智能体响应最多分别发起 3/4 个 `task` 调用；同一后端进程内所有会话合计最多同时执行 4 个子任务。每个
子任务最多调用 `web_search` 2 次、`web_fetch` 3 次、`web_extract` 1 次，并同时受循环检测
保护。政府申报复杂调研只启动一批互不重叠的专家，通常优先 2–3 个；仅“两项中一项成功”
时允许追加一次补缺任务。以上值均可在 `config.yaml` 中调整，客户端不能突破服务端上限。

### 申报全流程辅助

覆盖指南分析、选题规划、国内外研究现状、研究目标、研究内容、技术路线、创新点、考核指标、
进度安排、预算说明、风险控制、合规审查和成品导出。

### 产物保存与 Word 导出

支持按项目保存 Markdown 草稿、管理版本、导出多个章节，并可在人工确认后智能匹配图片证据
插入 Word 文档。

## 8. 许可

本项目采用 [MIT License](LICENSE)。

本项目由 DeerFlow 二次开发而来，保留上游版权和许可声明。使用、修改或分发本项目时，
请同时遵守仓库 `LICENSE`、第三方依赖许可证及所使用模型和数据服务的条款。

DeerFlow 上游项目：<https://github.com/bytedance/deer-flow>
