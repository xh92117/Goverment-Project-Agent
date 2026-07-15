# 政府项目申报智能体

本项目是面向政府科研项目、科技计划项目、专项资金项目等申报场景的本地 Web 智能体系统。它基于 Agent Base / DeerFlow 运行时改造，内置知识库检索、政策指南分析、申报材料撰写、预算辅助、合规审查和多子智能体协作能力。

默认运行方式为本机启动后端 Gateway 和前端 Web：

- 前端 Web：`http://127.0.0.1:9527`
- 后端 Gateway：`http://127.0.0.1:10086`

## 核心功能

- 政策指南分析：解析申报通知、指南、模板、申报条件、材料清单、截止时间、评分重点和限制条款。
- 知识库管理：支持把政策文件、申报模板、历史申报书、团队成果、论文、专利、标准等资料整理到知识库，并生成可检索索引。
- 选题规划：结合政策方向、单位基础、团队成果和竞争风险，生成候选申报方向、项目名称和推荐排序。
- 文献、标准、专利调研：优先检索知识库，也可调用官方网页和搜索工具补充最新政策、标准、专利、论文和竞品信息。
- 申报书撰写：辅助生成研究目标、研究内容、技术路线、创新点、预期成果、考核指标、进度安排和风险控制。
- 预算辅助：按任务和成果拆解预算科目，检查预算说明与研究内容是否匹配。
- 合规审查：检查指南适配、模板完整性、证据可追溯、预算合规、逻辑一致性和措辞质量。
- 产物保存：可将可复用的申报章节保存到申报工作区，并在前端 Artifacts 面板查看。

## 项目结构

```text
.
├─ backend/                 后端 Gateway、Agent 运行时和工具实现
├─ frontend/                Next.js 前端
├─ configs/                 政府项目申报智能体示例配置
├─ skills/public/           政府项目申报相关技能
├─ scripts/                 安装、启动、检查、知识库索引脚本
├─ config.yaml              当前本地模型、工具、子智能体配置
├─ extensions_config.json   当前启用的技能和 MCP 扩展配置
├─ .env                     本地密钥和运行参数
└─ start_web_agent.py       Windows 本地一键启动脚本
```

运行态数据默认不写入源码目录，而是放在：

```text
C:\Users\Administrator\GP Agent
├─ .agent-base\             数据库、线程、运行状态
└─ workspace\
   ├─ knowledge_base\       知识库根目录
   ├─ proposal_drafts\      申报草稿与保存的 Markdown 产物
   └─ logs\                 后端和前端启动日志
```

## 环境要求

- Windows 本地环境。
- Python `3.12+`。
- `uv`，用于安装和运行 Python 依赖。
- Node.js `22+`。
- `pnpm` 或 Corepack。
- 可选：Make / Git Bash，用于执行 `make install`、`make doctor` 等命令。

可以先检查基础工具：

```powershell
python .\scripts\check.py
```

## 安装依赖

推荐从项目根目录执行：

```powershell
make install
```

该命令会：

- 将后端 Python 依赖安装到根目录 `.venv`。
- 将前端依赖安装到 `.venv/frontend/node_modules`。
- 根据 `frontend/.npmrc` 使用 `.venv/pnpm-store` 作为 pnpm store。

如果当前机器没有 Make，可以手动安装：

```powershell
cd .\backend
$env:UV_PROJECT_ENVIRONMENT = "..\.venv"
uv sync

cd ..\frontend
pnpm install
```

安装后建议运行：

```powershell
make doctor
```

## 模型配置

当前 `config.yaml` 默认配置了两个 DeepSeek 模型：

- `deepseek-v4-flash`：用于常规对话、资料整理、文本改写等轻量任务。
- `deepseek-v4-pro`：用于选题论证、技术路线推理、创新点梳理、申报书核心章节等复杂任务。

在项目根目录创建或编辑 `.env`：

```env
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

搜索和知识库解析相关能力可按需配置：

```env
# 可选：增强搜索召回
SERPER_API_KEY=你的 Serper API Key
JINA_API_KEY=你的 Jina API Key

# 可选：PDF 知识库解析
MINERU_API_TOKEN=你的 MinerU Token
MINERU_API_BASE_URL=https://mineru.net
MINERU_MODEL_VERSION=vlm
MINERU_LANGUAGE=ch
MINERU_TIMEOUT_SECONDS=60
MINERU_POLL_INTERVAL_SECONDS=5
MINERU_MAX_WAIT_SECONDS=900
```

也可以在前端“设置 → PDF 解析”中填写 MinerU 配置；保存后会同步更新 `.env` 和 `config.yaml`。

如需添加其他模型，在 `config.yaml` 的 `models:` 下追加模型项，并在子智能体配置中引用对应的 `name`。例如 OpenAI 兼容模型通常需要配置 `use`、`model`、`api_key`、`base_url`、`request_timeout` 等字段。真实密钥建议继续放在 `.env` 中，再通过 `$变量名` 引用。

## 启动智能体

从项目根目录执行：

```powershell
& ".\.venv\Scripts\python.exe" ".\start_web_agent.py"
```

启动成功后访问：

```text
http://127.0.0.1:9527
```

如需配置本地代理：

```powershell
& ".\.venv\Scripts\python.exe" ".\start_web_agent.py" --network-proxy http://127.0.0.1:7897
```

如需修改端口：

```powershell
& ".\.venv\Scripts\python.exe" ".\start_web_agent.py" --backend-port 10086 --frontend-port 9527
```

停止服务时，在运行 `start_web_agent.py` 的 PowerShell 窗口按 `Ctrl+C`。

## 知识库使用

### 图像证据（兼容 LLM-Wiki）

知识库上传现在同时支持 JPG、JPEG、PNG、WebP 和 TIFF。图像不会写入原有文本
`index.json` 正文，而是保存在知识库根目录的 `.assets/` 中，并自动生成一份待复核
`evidence.md` 证据卡；LLM-Wiki 只增加 `entry_type=evidence` 指针，因此原有文档、
章节分块、索引搜索和 `knowledge_read_file` 流程保持兼容。

- 图像按 `applicant_id` 隔离和去重；读取原图必须再次提供匹配的申报主体。
- 新证据默认是 `needs_review`，人工确认前不得当作已核实的申报事实。
- 图片上传阶段只做安全存储并加入待识别队列；点击“整理入库并构建索引”或
  “仅重建索引”时，系统才调用配置中 `supports_vision: true` 的多模态模型，由模型
  自主判断是否属于申报证据，并提取类型、持有人、颁发单位、编号、日期、OCR 原文、
  申报章节和标签。项目不安装也不依赖 Tesseract、`pytesseract` 或其他本地 OCR。
- 如果没有配置支持视觉的模型，或模型调用/JSON 解析失败，构建结果会在上传卡片下方
  显示明确警告，图片保持待识别状态，且不影响原有文本知识索引。
- 可在 `config.yaml` 设置 `knowledge_image_model` 明确指定知识库视觉模型；未指定时使用
  第一个 `supports_vision: true` 的模型。模型调用温度固定为 0，大图会缩放到安全尺寸，
  图片内的指令性文字会按不可信内容处理。
- “知识库管理”标题栏右上角常驻显示“图片识别模型”状态。点击后会打开置顶配置窗口，
  该入口采用单行紧凑布局，已配置时以绿色状态点显示具体模型名，未配置时只显示一次
  “图片识别模型未配置”。窗口既可
  选择已有 `supports_vision: true` 模型，也可复用“设置 → 模型供应商”的供应商、模型名、
  URL 和 API Key 表单直接新增；从该窗口创建的模型会自动启用视觉能力并立即写入
  `knowledge_image_model`，无需重启服务。构建索引遇到图片但视觉能力不可用时，该窗口
  也会自动打开；普通文档仍会继续完成索引。
- 模型配置中的 `provider` 只用于设置界面识别供应商及展示默认 URL，不会作为请求参数
  传给 OpenAI 兼容客户端，避免 DashScope 等接口因未知 `provider` 参数拒绝图片识别。
- 模型判断为 `non_evidence_image` 时仍保持 `needs_review`，不会自动驳回。知识库列表存在
  已识别待审核证据时，工具栏会出现“批量确认证据”或“标记无关图片”；确认操作逐条
  校验，缺少持有人或可追溯字段的证据会被跳过。
- 可使用 `knowledge_search_evidence` 和 `knowledge_read_evidence` 检索、读取证据卡。
- 撰写申报内容或生成 Word 时，智能体会主动使用
  `verification_statuses=["human_verified"]` 检索相关图片证据，并把
  `knowledge_read_evidence` 返回的 `word_image_markdown` 放入草稿。Word 导出器会解析
  `evidence://<applicant_id>/<evidence_id>`，再次校验当前用户、申报主体和人工复核状态后
  嵌入原图；同一证据只插入一次，WebP/TIFF 会转换为 Word 兼容的 PNG。只有内部
  `evidence:<id>` 引用时，默认主体的已复核证据也会自动补入“相关证明材料”，且内部 ID
  不会显示在成品 Word 中。未复核、错主体、文件缺失或伪造 URI 均不会插图。
- 项目工作区的 Word 导出弹窗提供“不插入图片”和“智能匹配并插入”两个选项，默认保持
  直接导出。开启智能插图后，后端使用当前模型一次性分析所选 Markdown 与默认申报主体的
  `human_verified` 证据，为每个文档分配相关图片并只在本次导出中追加引用，不改写源文件；
  没有已确认图片、没有相关匹配或模型调用失败时会返回明确提示。
- MinerU PDF 解析会保留 ZIP 中被 Markdown 引用的图片，并写入
  `<源文件名>.pdf.assets/`；旧缓存存在缺失图片时会在下次重建时自动失效。
- 删除证据会同步清理原图、缩略图、证据卡、注册表和 LLM-Wiki 指针。

当前前端不单独展示申报主体输入或图像预览区域，图片使用默认内部归属空间并随普通
材料统一上传、统一构建。智能体只应把 `human_verified` 证据作为已核实申报事实使用。
原有非图片文件仍按
`_incoming → 整理入库 → 重建索引` 流程处理。

默认知识库目录：

```text
C:\Users\Administrator\GP Agent\workspace\knowledge_base
```

推荐资料组织方式：

```text
knowledge_base\
├─ _incoming\        新增待整理资料
├─ 政策指南\         政策指南、通知、申报条件
├─ 申报书模板\       申报模板、填报说明、预算模板
├─ 历史申报书\       历史申报书、立项案例
├─ 团队成果\         团队成果、论文、专利、标准、奖项
├─ 已有研究基础\     研究基础、平台条件、已有项目
└─ 预算依据\         预算模板、预算科目、经费说明
```

常用流程：

1. 将新增 PDF、Word、Markdown、TXT、CSV、Excel 等资料放入 `_incoming`。
2. 在前端对话中要求智能体“更新知识库”或“整理新增申报资料”。
3. 智能体会调用 `knowledge_incremental_update` 整理资料并更新索引。
4. 后续选题、撰写和审查任务会优先检索知识库，再补充网页信息。

### 无 Embedding 的检索增强

当前政府申报检索明确使用 `keyword` 模式，不要求下载、部署或调用 Embedding 模型。
召回由多路词法查询和强元数据过滤共同完成：原始问题、同义/简称变体、标题/关键词/
摘要/正文加权，以及主管部门、文种、年份、资料类型和有效日期过滤。政策指南、申报通知、
模板和历史申报章节因此不会只靠“文本看起来相似”混排。

检索质量由 `backend/tests/evals/knowledge_retrieval_cases.yaml` 的 Golden Set 持续评估，
同时检查 Top-K 命中和禁止来源污染。以后只有在资料规模、同义表达和跨语言召回达到词法
检索瓶颈，并且能够承担模型服务、向量重建、版本迁移和评测成本时，才考虑引入 Embedding。

### 项目绑定记忆

政府申报智能体的长期记忆按“当前用户 + `project_id`”隔离，保存在运行目录的
`users/<user_id>/projects/<project_id>/memory.json`。项目工作区会把 `project_id` 和
`applicant_id` 传到主智能体及所有专家；缺少 `project_id` 时，政府申报智能体不会读取
或更新长期记忆，也不会退回到跨项目用户画像。

- 人工确认信息存放在 `confirmedFacts`。
- 对话自动抽取只能进入 `workingAssumptions`，并标记来源和置信度；模型输出不能直接创建
  “已确认事实”。
- `workflowState` 只记录工作阶段，不作为事实证据。
- 注入提示会明确区分“可用事实”和“待核验假设”，禁止跨项目、跨申报主体复用。
- 当前不启用梦境记忆蒸馏，不做跨项目聚类、合并或离线自我强化。

也可以用脚本构建索引：

```powershell
.\scripts\build-knowledge-index.ps1
```

## 基本使用流程

1. 打开 `http://127.0.0.1:9527`。
2. 新建或选择一个对话。
3. 说明项目类型、申报年份、主管部门、申报单位、技术方向和已有材料。
4. 要求智能体先分析指南和模板，再进行选题、调研、撰写或审查。
5. 对可复用章节，要求智能体“保存到申报草稿”。
6. 在前端 Artifacts 面板查看已保存内容。

示例任务：

```text
请基于知识库中 2026 年省重点研发计划指南，分析我们单位在智能检测方向可以申报的 5 个课题方向，并给出推荐排序。
```

```text
请围绕“隧道结构病害智能识别与风险预警”撰写申报书中的研究目标、研究内容、技术路线、创新点和考核指标。
```

```text
请根据指南和模板审查这份申报书草稿，列出 P0/P1/P2 问题、修改建议和缺失证据。
```

## 异构专家协作

当前配置将多智能体作为能力、工具、模型和交付契约不同的异构专家，而不是人格化角色扮演：

- `guide-analyzer`：指南、模板、资格条件和申报风险分析。
- `knowledge-manager`：知识库新增资料整理和索引更新。
- `topic-planner`：课题方向和项目名称规划。
- `literature-researcher`：国内外研究现状、文献和技术趋势调研。
- `standards-patent-researcher`：标准、专利、检测方法和工程应用调研。
- `proposal-writer`：只把已给定决策和证据编排为申报章节，不自行联网扩展事实。
- `budget-analyst`：预算编制和费用说明辅助。
- `compliance-reviewer`：使用不同模型进行只读独立审查，不能直接保存或修改被审稿件。

主智能体按互不重叠的专家交付拆解任务，每个任务自动携带项目/申请人作用域。专家统一返回
结论、证据项、冲突与边界、缺失信息和交接建议；主智能体按“当前官方规则 > 已核验一手
证据 > 人工确认项目事实 > 工作假设 > 模型推断”裁决冲突，不以多个智能体重复同一说法
作为真实性依据。写作前形成证据—主张矩阵，完成后再交给独立合规专家审查。

## 常见问题

### 提示找不到前端 Next.js 入口

说明前端依赖没有安装或 `.venv/frontend/node_modules` 不完整。重新执行：

```powershell
cd .\frontend
pnpm install
```

### 提示 `DEEPSEEK_API_KEY is not set`

检查项目根目录 `.env` 是否存在，并确认包含：

```env
DEEPSEEK_API_KEY=你的实际密钥
```

### 端口被占用

默认端口是前端 `9527`、后端 `10086`。可以换端口启动：

```powershell
& ".\.venv\Scripts\python.exe" ".\start_web_agent.py" --backend-port 10087 --frontend-port 9528
```

### 清理构建缓存

可删除 `frontend/.next` 后重新启动，Next.js 会自动重新生成构建缓存。

## 许可

本项目基于 DeerFlow / Agent Base 改造，保留上游许可与来源说明。许可条款见 [LICENSE](LICENSE)。
