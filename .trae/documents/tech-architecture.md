# 政府类科研项目申报智能体 — 前端技术架构（V2）

## 一、版本变更摘要（相对 V1）

| 维度 | V1 | V2 |
| --- | --- | --- |
| 账号系统 | 顶部用户菜单 / 头像 | **完全移除** |
| 主题 | 固定政务深靛蓝 + 朱砂红 | **森林苔藓 + 暖陶土**，支持**亮 / 暗**双主题实时切换 |
| 布局 | 三栏（侧栏 + 对话 + 右侧 4-Tab） | 两栏（侧栏 + 主区），**右栏 Tab 改为独立页面** |
| 主导航 | 仅 logo + 全局搜索 | 顶部 **对话 / 知识库 / 设置** 单页切换 |
| 知识库 | 右侧 Tab 缩略列表 | **全屏页面**，含分类树、列表、详情三栏 |
| 设置 | 不存在 | **全屏页面**，含大模型 / 智能体能力 / 技能 / MCP / 外观 / 通用 6 大组 |
| 后端适配 | 沿用 LangGraph 兼容 API + `/api/knowledge` + `/api/proposal-drafts` | 同 V1，**新增**：`/api/models` 用于设置页模型列表 |

## 二、架构目标

1. **单文件可即时预览**：双击 `index.html` 即可在浏览器中看到完整效果（含主题切换 / 页面切换）
2. **可演进到正式前端**：CSS 变量分层、视图容器与数据状态分离
3. **主题切换零闪烁**：通过 `<html data-theme="...">` 驱动 CSS 变量级联
4. **页面切换平滑**：使用 View Transitions API 或 CSS 渐变过渡

## 三、文件结构

```
frontend-reference/
└── index.html      # 单文件参考稿（内联 CSS / JS / SVG）
```

正式工程结构：
```
frontend/
├── app/
│   ├── layout.tsx
│   ├── (workspace)/
│   │   ├── chat/page.tsx
│   │   ├── knowledge/page.tsx
│   │   └── settings/page.tsx
├── components/
│   ├── nav/                # TopNav 主导航
│   ├── theme/              # ThemeProvider, ThemeToggle
│   ├── chat/               # MessageList, MessageBubble, Composer
│   ├── knowledge/          # KBCategoryTree, KBList, KBDetail
│   ├── settings/           # ModelPanel, CapabilityMatrix, SkillsPanel, MCPPanel
│   └── ui/                 # Button, Switch, Slider, Tabs, Modal
├── lib/
│   ├── theme.ts            # 主题定义
│   ├── api/                # LangGraph 兼容 + Gateway 客户端
│   └── hooks/
└── public/fonts/
```

## 四、信息架构

```
┌─ TopNav ───────────────────────────────────────────────┐
│ Logo │ [对话] [知识库] [设置] │ 🔍搜索 │ ☀/🌙 │ 模型名 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│              主区（按页面切换）                         │
│                                                         │
│  /chat       左侧栏 │ 对话区 │ 行内抽屉(草稿/计划)      │
│  /knowledge  分类树 │ 列表   │ 详情预览                  │
│  /settings   设置组 │ 设置表单                            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 五、设计 Token（双主题）

### 5.1 亮色（默认）

```css
:root, [data-theme="light"] {
  /* Brand */
  --c-primary:        #1F4A36;   /* 深森林绿 */
  --c-primary-2:      #173A29;
  --c-primary-50:     #E5EDE7;
  --c-primary-100:    #C5D8C9;
  --c-accent:         #C26A4D;   /* 暖陶土 */
  --c-accent-2:       #A8573C;
  --c-accent-50:      #F4E5DD;
  --c-gold:           #B8893E;
  --c-gold-50:        #F3EBD6;

  /* Surface */
  --c-bg:             #FAF6EE;   /* 暖象牙 */
  --c-bg-2:           #F1ECDD;   /* 旧象牙 */
  --c-surface:        #FFFFFF;
  --c-surface-2:      #FBF8F0;
  --c-ink:            #1A1F1B;   /* 墨色 */
  --c-ink-2:          #3A4138;
  --c-muted:          #7A8480;
  --c-muted-2:        #B5BCB6;
  --c-border:         #E8E2D2;
  --c-border-2:       #D6CFB9;

  /* Status */
  --c-success:        #2D7A3E;
  --c-warning:        #B57300;
  --c-danger:         #A03E2E;
  --c-info:           #1A5F8A;
}
```

### 5.2 暗色

```css
[data-theme="dark"] {
  --c-primary:        #9BC4A0;   /* 柔鼠尾草 */
  --c-primary-2:      #B6D2B9;
  --c-primary-50:     #1E2A22;
  --c-primary-100:    #2C3A30;
  --c-accent:         #E8956D;   /* 暖珊瑚 */
  --c-accent-2:       #F2A782;
  --c-accent-50:      #3A261E;
  --c-gold:           #E8B568;   /* 琥珀金 */
  --c-gold-50:        #3A2E16;

  --c-bg:             #0E1410;   /* 深炭墨 */
  --c-bg-2:           #161D17;
  --c-surface:        #161D17;
  --c-surface-2:      #1C251D;
  --c-ink:            #E5E8E2;   /* 米白 */
  --c-ink-2:          #C5CAC2;
  --c-muted:          #7E8A82;
  --c-muted-2:        #4F5750;
  --c-border:         #252D26;
  --c-border-2:       #34402F;

  --c-success:        #6BBF7B;
  --c-warning:        #E8B568;
  --c-danger:         #E8956D;
  --c-info:           #6FAFD0;
}
```

### 5.3 通用 token

```css
:root {
  /* Typography */
  --font-serif: "Noto Serif SC", "Source Han Serif SC", "宋体", serif;
  --font-sans:  "Inter", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-mono:  "JetBrains Mono", "Cascadia Code", "Consolas", monospace;

  /* Spacing */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px;  --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px;  --sp-10: 40px;
  --sp-12: 48px;

  /* Radius */
  --r-xs: 4px;  --r-sm: 6px;  --r-md: 10px;
  --r-lg: 14px; --r-xl: 20px; --r-2xl: 24px; --r-full: 9999px;

  /* Shadow */
  --sh-1: 0 1px 2px rgba(31,74,54,.06), 0 1px 1px rgba(31,74,54,.04);
  --sh-2: 0 4px 14px rgba(31,74,54,.08), 0 1px 3px rgba(31,74,54,.04);
  --sh-3: 0 16px 40px rgba(31,74,54,.12), 0 2px 6px rgba(31,74,54,.06);
  --sh-glow: 0 0 0 3px rgba(194,106,77,.18);

  /* Layout */
  --sidebar-w: 280px;
  --topbar-h: 60px;
}
```

> 切换主题时，仅替换 CSS 变量；JS 通过 `document.documentElement.dataset.theme` 持久化到 `localStorage`。

## 六、布局栅格

### 6.1 /chat
```
┌─ TopNav ─────────────────────────────────────────────┐
├──────────┬──────────────────────────────────────────┤
│ Sidebar  │   Chat                                    │
│ (280px)  │   (flex 1) + 行内抽屉(可选 360px)        │
│ 280px    │                                           │
└──────────┴──────────────────────────────────────────┘
```

### 6.2 /knowledge
```
┌─ TopNav ─────────────────────────────────────────────┐
├──────────┬──────────────┬───────────────────────────┤
│ 分类树   │   列表        │   详情预览                 │
│ (220px)  │   (flex 1)   │   (420px)                  │
└──────────┴──────────────┴───────────────────────────┘
```

### 6.3 /settings
```
┌─ TopNav ─────────────────────────────────────────────┐
├──────────┬──────────────────────────────────────────┤
│ 设置组   │   设置表单                                  │
│ (220px)  │   (max-width 800px)                        │
│ 大模型   │                                              │
│ 智能体   │   - 大模型：选择 + 温度 + token + 推理     │
│ 技能     │   - 智能体能力：开关矩阵                     │
│ MCP      │   - 技能 / MCP：列表 + 启用 / 禁用          │
│ 外观     │   - 外观：主题切换、字体、字号               │
│ 通用     │   - 通用：流式、清理历史                     │
└──────────┴──────────────────────────────────────────┘
```

## 七、关键交互

### 7.1 主题切换
```js
const root = document.documentElement;
const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
root.dataset.theme = next;
localStorage.setItem('theme', next);
```
首屏脚本优先读取 `localStorage.theme`，再回退到 `prefers-color-scheme`，最后回退到 `light`。

### 7.2 页面切换
单页路由，使用 `history.pushState` + 监听 `popstate`：
- `/chat`
- `/knowledge`
- `/settings`

切换时使用：
- `View Transitions API`（如可用）：`document.startViewTransition(...)`
- 否则使用 `.view-enter` / `.view-leave` 类的 opacity + translateY 过渡

### 7.3 设置表单状态
- 使用原生 form 元素 + `change` 事件
- 改动后实时写入 `localStorage`，并提供"恢复默认"按钮
- 切换模型时弹窗二次确认（避免误操作）

## 八、组件清单

| 组件 | 路径 | 状态 |
| --- | --- | --- |
| TopNav | `components/nav/TopNav.tsx` | 稳定 |
| ThemeToggle | `components/theme/ThemeToggle.tsx` | 稳定 |
| ThreadSidebar | `components/chat/ThreadSidebar.tsx` | 稳定 |
| MessageBubble | `components/chat/MessageBubble.tsx` | 稳定 |
| ThinkingPanel | `components/chat/ThinkingPanel.tsx` | 稳定 |
| Composer | `components/chat/Composer.tsx` | 稳定 |
| KBCategoryTree | `components/knowledge/CategoryTree.tsx` | 新增 |
| KBList | `components/knowledge/KBList.tsx` | 新增 |
| KBDetail | `components/knowledge/KBDetail.tsx` | 新增 |
| ModelPicker | `components/settings/ModelPicker.tsx` | 新增 |
| CapabilitySwitch | `components/settings/CapabilitySwitch.tsx` | 新增 |
| MCPServerList | `components/settings/MCPServerList.tsx` | 新增 |
| SkillsPanel | `components/settings/SkillsPanel.tsx` | 新增 |
| AppearancePanel | `components/settings/AppearancePanel.tsx` | 新增 |

## 九、与后端 API 映射（V2 增强）

| 前端模块 | 后端 API |
| --- | --- |
| TopNav 模型指示 | `GET /api/models` |
| 设置 - 大模型 | `GET /api/models`、`POST /api/models/test` |
| 设置 - 技能 | `GET /api/skills`、`PUT /api/skills/{name}`、`POST /api/skills/install` |
| 设置 - MCP | `GET /api/mcp/config`、`PUT /api/mcp/config` |
| 设置 - 记忆 | `GET /api/memory`、`POST /api/memory/reload` |
| 知识库页面 | `GET /api/knowledge/documents?library=&doc_type=` |
| 知识库检索 | `POST /api/knowledge/search` |
| 知识库索引 | `GET /api/knowledge/index`、`POST /api/knowledge/index/build` |
| 文件读取 | `POST /api/knowledge/files/read` |
| 对话流 | `POST /api/langgraph/threads/{id}/runs/stream` |
| 文件上传 | `POST /api/threads/{id}/uploads` |
| 草稿列表 | `GET /api/proposal-drafts` |
| 草稿读写 | `GET/PUT /api/proposal-drafts/{task}/{section}` |

## 十、本期交付内容（V2）

✅ 单文件 `index.html`，包含：
1. 顶部主导航（对话 / 知识库 / 设置）+ 主题切换按钮
2. 完整双主题 CSS 变量（亮 + 暗），首屏自动适配 + 实时切换
3. 三个全屏页面：
   - **对话页**：双栏 + 行内抽屉（草稿/计划）
   - **知识库页**：分类树 + 列表 + 详情三栏
   - **设置页**：左侧设置组 + 右侧表单
4. 设置 - 大模型：模型选择（6 个真实模型 + 自定义）、温度 slider、max_tokens、top_p、thinking toggle
5. 设置 - 智能体能力：8 项能力开关矩阵
6. 设置 - 技能 / MCP / 外观 / 通用 4 个分组的简化展示
7. 保留：流式光标、思维链脉冲、Markdown 渲染、引用脚注、印章 logo
8. 移除：用户菜单、账号相关元素

❌ 后续待补：
- 真实 API 联调
- View Transitions API 兼容性处理
- 移动端响应式（暂不交付）
