# 智策 · 前端 UI 改造实施计划

## 概述

对"智策 · 政府科研项目申报助手"前端进行增量式 UI 改造，分 **10 个步骤**，每步独立构建验证。核心目标：

1. **双主题系统**：深色主题 "Midnight Forest"（深绿黑 + 翠绿高亮）+ 浅色主题 "Clean White"（纯白 + 翡翠绿品牌色），按钮一键切换
2. **现代 AI Agent 布局**：参考 Trae/Codex，用 Icon Rail（48px）+ Side Panel（240px）+ Center Canvas + Right Panel（320px）四栏布局取代传统顶栏+侧栏

## 当前状态分析

| 维度 | 现状 |
|------|------|
| 布局 | `workspace/layout.tsx` 用 `TopNav`(60px) + `workspace-main` 两行 grid；聊天页有独立 `.chat-layout`（sidebar 280px + workspace）；项目页有独立三栏 `.project-shell` |
| CSS | 单文件 `globals.css` 约 5509 行，包含所有 token + 组件 + 模块样式 |
| 主题 | `useThemeMode()` hook + `ThemeScript` SSR 防闪烁，`data-theme="light"|"dark"` + localStorage key `govdecl-theme` |
| 色板 | 全局深绿 `#1f4a36`，项目模块独立青绿 `#0f766e`（视觉割裂），宣纸黄底 `#faf6ee` |
| 导航 | `TopNav` 含品牌 seal、药丸导航项（项目/知识库/设置）、主题切换 |
| 关键约束 | `streamRun()` SSE 通信（`chat-page.tsx` + `project-workspace-page.tsx`）**不触碰** |

## 实施步骤

---

### 步骤 1：CSS 架构拆分

**目标**：将 `globals.css` 拆分为模块化文件，保持功能完全不变。

**新建文件**（`frontend/src/styles/` 目录下）：

| 文件 | 内容 | 源文件行号范围 |
|------|------|--------------|
| `tokens.css` | 设计 token（颜色/字体/间距/圆角/阴影变量） | 1-103 |
| `base.css` | 重置样式、body、滚动条、`@keyframes` | 105-175 + 4095-4115 |
| `components.css` | `.btn`、`.icon-btn`、`.model-chip`、`.kbd`、`.error-state` 等通用组件 | 散布行汇总 |
| `layout.css` | `.app-shell`、`.workspace-main`、`.topbar`、`.brand*`、`.main-nav*`、`.topbar-right` | 176-505 |
| `chat.css` | `.chat-layout`、`.sidebar*`、`.workspace-head`、`.messages`、`.msg*`、`.composer*`、`.welcome*`、`.drawer*`、`.citation-*`、`.stream-*` | 508-1960 |
| `knowledge.css` | `.kb-layout`、`.kb-*` 所有知识库样式 | 1982-2984 |
| `settings.css` | `.settings-*`、`.ws-layout` 所有设置页样式 | 相关散布行 |
| `projects.css` | `.projects-dashboard*`、`.project-shell`、`.project-*` 所有项目样式 | 2985-5509 |
| `drafts.css` | `.drafts-*` 所有草稿页样式 | 相关散布行 |

**修改文件**：`globals.css` 全部替换为：

```css
@import "tailwindcss";
@source "../../node_modules/streamdown/dist/index.js";

@import "./tokens.css";
@import "./base.css";
@import "./components.css";
@import "./layout.css";
@import "./chat.css";
@import "./knowledge.css";
@import "./settings.css";
@import "./projects.css";
@import "./drafts.css";
```

**验证**：`pnpm build` 成功 → `pnpm dev` 逐一访问所有页面视觉一致 → 明暗主题切换正常

---

### 步骤 2：统一色彩令牌（删除项目模块独立色板）

**目标**：删除 `.projects-dashboard` / `.project-shell` 对 `--c-primary` 等变量的独立覆盖，所有模块共享全局 token。

**修改文件**：`projects.css` — 删除以下两段选择器：

```css
/* 删除 */
.projects-dashboard,
.project-shell {
  --c-primary: #0f766e;
  --c-primary-2: #115e59;
  /* ...全部覆盖变量... */
}

[data-theme="dark"] .projects-dashboard,
[data-theme="dark"] .project-shell {
  --c-primary: #5eead4;
  /* ...全部覆盖变量... */
}
```

**验证**：构建成功 → 项目工作台按钮/链接颜色变为全局深绿（与聊天页一致）→ 明暗主题下色系统一

---

### 步骤 3：新双主题令牌

**目标**：替换 `tokens.css` 中的色彩变量为全新双主题系统。

**修改文件**：`tokens.css` — 替换两套色板：

**浅色主题 "Clean White"**（`:root, [data-theme="light"]`）：

```css
--c-primary:       #166534;   /* 深翡翠绿，品牌核心 */
--c-primary-2:     #14532d;   /* hover 加深 */
--c-primary-50:    #ecfdf5;   /* 极浅绿，选中/hover 背景 */
--c-primary-100:   #d1fae5;   /* 浅绿，tag/chip 底色 */
--c-accent:        #16a34a;   /* 翡翠绿，按钮/链接/高亮 */
--c-accent-2:      #15803d;   /* hover 加深 */
--c-accent-50:     #f0fdf4;   /* 极浅绿底 */
--c-bg:            #ffffff;   /* 纯白底 */
--c-bg-2:          #f9fafb;   /* 极浅灰白，Side Panel */
--c-surface:       #ffffff;   /* 纯白，Center Canvas */
--c-surface-2:     #f3f4f6;   /* 次级白 */
--c-ink:           #111827;   /* 近纯黑文字 */
--c-ink-2:         #374151;   /* 深灰次级文字 */
--c-muted:         #6b7280;   /* 中灰弱化 */
--c-muted-2:       #9ca3af;   /* 浅灰 placeholder */
--c-border:        #e5e7eb;   /* 浅灰边框 */
--c-border-2:      #d1d5db;   /* 加强边框 */
--c-success:       #16a34a;
--c-warning:       #ca8a04;
--c-danger:        #dc2626;
--c-info:          #2563eb;
--scrim:           rgba(0, 0, 0, 0.06);
```

**深色主题 "Midnight Forest"**（`[data-theme="dark"]`）：

```css
--c-primary:       #6ee7b7;   /* 亮翡翠绿，暗色下做文字 */
--c-primary-2:     #a7f3d0;   /* hover 更亮 */
--c-primary-50:    #0d2818;   /* 深墨绿底，选中背景 */
--c-primary-100:   #143d25;   /* 中深绿，tag 底色 */
--c-accent:        #34d399;   /* 明亮翠绿，交互高亮 */
--c-accent-2:      #6ee7b7;   /* hover 更亮 */
--c-accent-50:     #0d2818;   /* 深翠绿透明底 */
--c-bg:            #0a0f0c;   /* 最深底色（近纯黑带微绿偏） */
--c-bg-2:          #111916;   /* 次深底，Side Panel */
--c-surface:       #151f1a;   /* 主内容面，Center Canvas */
--c-surface-2:     #1a2820;   /* 次级面，卡片 */
--c-ink:           #e5e8e2;   /* 主文字高对比 */
--c-ink-2:         #c5cac2;   /* 次级文字 */
--c-muted:         #7e8a82;   /* 弱化文字 */
--c-muted-2:       #4f5750;   /* placeholder */
--c-border:        #1f2e26;   /* 常规边框 */
--c-border-2:      #2d4035;   /* 加强边框 */
--c-success:       #34d399;
--c-warning:       #fbbf24;
--c-danger:        #f87171;
--c-info:          #60a5fa;
--scrim:           rgba(0, 0, 0, 0.45);
```

**修改文件**：`base.css` — body 过渡时间改为 300ms：

```css
body {
  transition: background 0.3s ease, color 0.3s ease;
}
```

**验证**：构建成功 → 切换主题时 Midnight Forest 呈深绿黑底 + 翠绿高亮 → Clean White 呈纯白底 + 深翡翠绿 → 300ms 平滑过渡 → 所有页面色彩正确

---

### 步骤 4：新建 Icon Rail 组件

**目标**：创建左侧 48px 图标轨道组件，取代 TopNav 的导航功能。

**新建文件**：`shared/layout/icon-rail.tsx`

- 顶部：品牌 seal "策"（`--font-serif` 宋体，翡翠绿渐变底）
- 上部图标：对话（MessageSquareIcon）、项目（FolderKanbanIcon）、知识库（BookOpenIcon）、草稿（FileEditIcon）
- 下部图标：设置（Settings2Icon）、主题切换（Sun/Moon）、用户（UserIcon）
- 激活态：`--c-accent` 翡翠色 + `--c-primary-50` 浅底背景
- 使用 `usePathname()` 判断当前路由激活项
- 使用 `useThemeMode()` 的 `toggleTheme` 切换主题

**新建文件**：`styles/icon-rail.css` — Icon Rail 样式

**修改文件**：`globals.css` 添加 `@import "./icon-rail.css";`

**验证**：构建成功 → 组件已创建但尚未被 layout 引用 → CSS 正确加载

---

### 步骤 5：新建 Side Panel 组件

**目标**：创建可折叠侧面板组件，作为各页面的统一侧栏容器。

**新建文件**：`shared/layout/side-panel.tsx`

- Props: `children`, `title?`, `defaultCollapsed?`
- 折叠时宽度从 240px → 48px，显示展开按钮
- 展开时显示 title + 折叠按钮 + children 内容
- 折叠/展开 200ms 过渡动画

**新建文件**：`styles/side-panel.css` — Side Panel 样式

**修改文件**：`globals.css` 添加 `@import "./side-panel.css";`

**验证**：构建成功 → 组件独立可渲染

---

### 步骤 6：四栏布局 Shell 替换 workspace layout

**目标**：用 CSS Grid 四栏布局取代 TopNav + workspace-main 结构。

**新建文件**：`styles/app-grid.css` — 四栏 Grid 布局 + 响应式断点

核心 CSS：

```css
.app-grid {
  display: grid;
  grid-template-columns: 48px auto 1fr;
  height: 100vh;
  overflow: hidden;
}

.app-grid.with-right {
  grid-template-columns: 48px auto 1fr 320px;
}

.app-grid-center {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.app-grid-context-bar {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--c-border);
  backdrop-filter: blur(14px);
  flex-shrink: 0;
}

.app-grid-content { flex: 1; min-height: 0; overflow: hidden; }

.app-grid-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--c-border);
}
```

响应式断点：
- ≥1280px：完整四栏
- 1024-1279px：隐藏 Right Panel
- 768-1023px：Side Panel 改为 overlay 弹出
- <768px：隐藏 Icon Rail，全宽

**修改文件**：`workspace/layout.tsx` — 替换为：

```tsx
import { IconRail } from "@/shared/layout/icon-rail";

export default function WorkspaceLayout({ children }) {
  return (
    <div className="app-grid">
      <IconRail />
      <div className="app-grid-center">
        {children}
      </div>
    </div>
  );
}
```

**关键决策**：TopNav 被完全移除。Side Panel 由各子页面自行提供（因为不同页面需要不同侧栏内容）。

**修改文件**：`globals.css` 添加 `@import "./app-grid.css";`

**验证**：构建成功 → 左侧出现 48px Icon Rail → 导航图标可点击路由 → 主题切换按钮功能正常 → 旧 TopNav 消失 → 各页面内容区可渲染（布局暂不完美，待后续步骤迁移）

---

### 步骤 7：迁移聊天页到四栏布局

**目标**：将 `chat-page.tsx` 从 `.chat-layout`（sidebar + workspace）迁移到新布局体系。

**修改文件**：`features/chat/chat-page.tsx`

结构变更（**所有业务逻辑、state、streamRun 调用保持不变**）：

```
原：<div className="chat-layout"><aside className="sidebar">...</aside><div className="workspace">...</div></div>
新：<><SidePanel title="对话">{原 sidebar 内容}</SidePanel><div className="app-grid-center">{原 workspace 内容}</div></>
```

具体操作：
- import 添加 `SidePanel`
- 外层 div 从 `chat-layout` 改为 `<>` Fragment + SidePanel + app-grid-center
- `.workspace-head` 内容移入 `.app-grid-context-bar`
- `.messages` + `.composer-wrap` 移入 `.app-grid-content`
- 删除 `sidebarWidth`、`sidebarCollapsed` 状态和 resize 逻辑（SidePanel 自管理）
- `.drawer`（草稿/计划面板）保持 overlay 不变

**修改文件**：`styles/chat.css` — 删除 `.chat-layout` grid 定义和 `.sidebar` 面板样式，保留内部内容样式

**验证**：构建成功 → 聊天页呈现 Icon Rail + Side Panel（线程列表）+ 中心画布（消息流 + 输入框）→ Side Panel 可折叠 → 线程选择/重命名/删除正常 → 发送消息/流式回复/停止生成正常 → 草稿抽屉正常弹出

---

### 步骤 8：迁移项目工作台到四栏布局

**目标**：将 `project-workspace-page.tsx` 从三栏 `.project-shell` 迁移到全局四栏布局。

**修改文件**：`features/projects/project-workspace-page.tsx`

结构变更（**streamRun 调用保持不变**）：

```
原：<div className="project-shell"><aside className="project-left"/><main className="project-chat"/><aside className="project-right"/></div>
新：<><SidePanel>{原 project-left}</SidePanel><div className="app-grid-center">{原 project-chat}</div><aside className="app-grid-right">{原 project-right}</aside></>
```

- 删除 `leftCollapsed`、`rightCollapsed`、`leftWidth`、`rightWidth` 状态及 resize 逻辑
- 外层 div 添加 `with-right` class 以启用右侧栏

**修改文件**：`styles/projects.css` — 删除 `.project-shell` grid 定义和独立面板样式，保留内容样式

**验证**：构建成功 → 项目工作台呈现四栏布局 → 项目列表/对话/文件工作台正常 → 文件上传/编辑/保存正常 → 草稿版本管理正常

---

### 步骤 9：迁移知识库、设置、草稿页

**目标**：将剩余三个页面适配到四栏布局。

**修改文件**：

1. **`features/knowledge/knowledge-page.tsx`**：`.kb-side` → `SidePanel`，`.kb-main` → `app-grid-center`
2. **`features/settings/settings-page.tsx`**：`.settings-nav` → `SidePanel`，`.settings-main` → `app-grid-center`
3. **`features/drafts/drafts-page.tsx`**：侧栏 → `SidePanel`，主区域 → `app-grid-center`

**修改对应 CSS 文件**：`knowledge.css`、`settings.css`、`drafts.css` — 删除各自的外层 grid 定义，保留内部样式

**验证**：每个页面分别验证 → 知识库分类/搜索/文档管理正常 → 设置各 tab 功能正常 → 草稿编辑/版本正常

---

### 步骤 10：响应式优化与最终调优

**目标**：完善四档响应式断点 + 全局视觉调优。

**修改文件**：`styles/app-grid.css` — 完善媒体查询：

- **≥1280px**：完整四栏
- **1024-1279px**：三栏（Right Panel 隐藏）
- **768-1023px**：两栏（Side Panel overlay + scrim 遮罩）
- **<768px**：单栏（隐藏 Icon Rail，全宽）

**修改文件**：`shared/layout/side-panel.tsx` — 添加 overlay 模式遮罩层点击关闭逻辑

**全局调优清单**：
- 主题过渡动画 300ms 覆盖所有 `var(--c-*)` 使用处
- Icon Rail 活跃指示器动画
- Context Bar 毛玻璃效果一致性
- Right Panel 滑入动画
- 空状态设计统一

**验证**：在 1440px / 1100px / 900px / 600px 四个视口宽度测试每个页面 → 主题切换正常 → 所有功能无回归 → `pnpm build` 无错误

---

## 步骤依赖关系

```
步骤1 (CSS拆分)
  ↓
步骤2 (统一色板) → 步骤3 (新主题令牌)
                         ↓
              步骤4 (Icon Rail) + 步骤5 (Side Panel) [可并行]
                         ↓
                   步骤6 (四栏布局 Shell)
                         ↓
                   步骤7 (聊天页迁移)
                         ↓
                   步骤8 (项目工作台迁移)
                         ↓
                   步骤9 (其余页面迁移)
                         ↓
                   步骤10 (响应式 + 调优)
```

## 文件变更汇总

### 新建文件（14个）

| 文件 | 说明 |
|------|------|
| `styles/tokens.css` | 设计 token |
| `styles/base.css` | 基础重置 |
| `styles/components.css` | 通用组件 |
| `styles/layout.css` | 旧布局过渡期保留 |
| `styles/chat.css` | 聊天模块 |
| `styles/knowledge.css` | 知识库模块 |
| `styles/settings.css` | 设置页 |
| `styles/projects.css` | 项目模块 |
| `styles/drafts.css` | 草稿模块 |
| `styles/icon-rail.css` | Icon Rail 样式 |
| `styles/side-panel.css` | Side Panel 样式 |
| `styles/app-grid.css` | 四栏 Grid 布局 |
| `shared/layout/icon-rail.tsx` | Icon Rail 组件 |
| `shared/layout/side-panel.tsx` | Side Panel 组件 |

### 修改文件（9个）

| 文件 | 变更 |
|------|------|
| `styles/globals.css` | 5500行 → ~15行 import |
| `app/workspace/layout.tsx` | `app-shell + TopNav` → `app-grid + IconRail` |
| `shared/layout/top-nav.tsx` | 不再被引用（可删除或保留） |
| `features/chat/chat-page.tsx` | JSX 结构迁移到 SidePanel + app-grid-center |
| `features/projects/project-workspace-page.tsx` | JSX 结构迁移到四栏 |
| `features/knowledge/knowledge-page.tsx` | JSX 结构迁移 |
| `features/settings/settings-page.tsx` | JSX 结构迁移 |
| `features/drafts/drafts-page.tsx` | JSX 结构迁移 |

### 不修改的文件

| 文件 | 原因 |
|------|------|
| `shared/theme/use-theme.ts` | hook 逻辑不变 |
| `shared/theme/theme-script.tsx` | SSR 防闪烁不变 |
| `features/chat/api.ts` | streamRun SSE 不触碰 |
| `features/chat/message-utils.ts` | 消息处理不变 |
| 所有 API 层文件 | 纯样式改造不动数据流 |

## 风险与缓解

1. **CSS 拆分遗漏** → 每拆分一个文件后立即 `pnpm build` 验证
2. **项目模块删除独立 token 后样式异常** → 步骤 2 先统一、步骤 3 再换色，分步降低风险
3. **TopNav 移除影响 auth 页面** → workspace layout 仅影响 `/workspace/*`，auth 路由独立不受影响
4. **Side Panel 折叠状态跨页面** → 暂不持久化，各页面独立管理
5. **响应式 z-index 冲突** → 统一定义：Icon Rail(z-10) < Side Panel overlay(z-50) < Drawer(z-60) < Modal(z-70)
