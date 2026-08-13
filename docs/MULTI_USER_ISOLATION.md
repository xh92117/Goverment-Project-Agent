# 多用户隔离与公共知识库部署指南

本项目的服务器部署默认采用“共享运行框架、私有用户数据、管理员维护公共资源”的模型。生产 Docker Compose 默认设置：

```dotenv
GATEWAY_ENABLE_LOCAL_AUTH=true
AGENT_BASE_STRICT_USER_CONTEXT=true
```

只要部署面向不互信用户，就不要关闭这两个开关。严格模式下，文件或持久化代码在没有用户上下文时会直接失败，不会回退到一个所有人共享的 `default` 目录。

## 1. 隔离模型

共享资源：

- 智能体运行框架、内置工具和 `skills/public`；
- 模型、MCP、Skills、系统设置和渠道配置；
- 管理员维护的公共知识库；
- 仅运维人员可见的容器标准输出和系统级监控。

用户私有资源：

- 线程、上传文件、工作区、产物和沙箱；
- 项目、旧版申报草稿、自定义智能体和长期记忆；
- 用户知识库、索引、解析缓存和图像证据；
- 运行记录、MCP 有状态会话、应用日志和审计日志。

共享配置的写操作要求管理员角色。普通用户可以调用管理员已配置的模型、工具、MCP 和 Skills，但不能修改这些共享定义。

## 2. 磁盘布局

`AGENT_BASE_HOME` 是私有状态根目录。典型结构如下：

```text
AGENT_BASE_HOME/
├─ data/agent_base.db
├─ users/
│  └─ {user_id}/
│     ├─ threads/{thread_id}/
│     │  ├─ user-data/{workspace,uploads,outputs}/
│     │  └─ acp-workspace/
│     ├─ projects/
│     ├─ proposal_drafts/
│     ├─ knowledge_base/
│     ├─ agents/
│     ├─ memory.json
│     └─ logs/{application.jsonl,audit.jsonl}
└─ migration-conflicts/
```

公共知识库不放在任何用户目录内，其根目录由 `AGENT_BASE_KNOWLEDGE_ROOT` 指定。生产环境应把整个 `AGENT_BASE_HOME` 挂载为持久卷，并限制为 Gateway/Provisioner 服务账号可读写；不要通过静态文件服务器暴露 `users/`。

## 3. 公共与私有知识库

知识库 API 的单库操作使用查询参数：

- `scope=private`：当前用户私有库，也是写操作的默认值；
- `scope=public`：公共库；读取允许已认证用户，创建、上传、构建索引、修改和删除仅允许管理员；
- 文件读取接口可使用 `scope=auto`：先查私有库，未命中再查公共库。

`POST /api/knowledge/search` 和 `POST /api/knowledge/index/search` 会自动合并当前用户私有库与公共库的结果，并在每条结果上返回 `scope`。同路径资源冲突时，自动读取优先选择私有资源。智能体的知识检索工具同样执行组合检索，因此普通用户无需切换配置即可同时使用公共政策资料和自己的申报材料。

管理员维护公共库的示例：

```http
POST /api/knowledge/files/upload?scope=public
POST /api/knowledge/index/process-incoming?scope=public
GET  /api/knowledge/index?scope=public
```

公共库应只存放所有用户都可以看到的政策、指南、模板和通用资料；企业证照、申报底稿、人员信息等必须进入私有库。

## 4. 请求、缓存与沙箱边界

认证中间件会把服务端解析出的用户同时写入 `request.state.user` 和任务本地 `ContextVar`。客户端提交的 `user_id`、运行时 `context.user_id` 或 `configurable.thread_id` 不能覆盖服务端身份和路由线程号。

- 线程和运行记录的读取、取消、等待与流式恢复都校验当前用户；
- RunManager 的内存索引按 `user_id + thread_id` 过滤；
- MCP 有状态连接池按 `user_id + thread_id` 建立会话；
- LocalSandbox 与 AIO Sandbox 的缓存键、确定性容器 ID和锁均包含用户；
- Kubernetes hostPath 与 PVC subPath 均使用 `users/{user_id}/threads/{thread_id}`；
- 私有知识解析缓存位于用户知识库目录，不与公共库或其他用户共用。

每个认证请求返回 `X-Request-ID`。请求期间的应用日志写入该用户的 `application.jsonl`，HTTP 审计写入 `audit.jsonl`。日志只记录方法、路径、状态码、耗时和请求 ID，不记录请求正文或查询参数中的密钥。

## 5. 生产部署步骤

1. 为数据库、`AGENT_BASE_HOME`、公共知识库和配置文件创建备份。
2. 配置足够长且唯一的 `BETTER_AUTH_SECRET` 与 `AGENT_BASE_INTERNAL_AUTH_TOKEN`。
3. 保持 `GATEWAY_ENABLE_LOCAL_AUTH=true` 和 `AGENT_BASE_STRICT_USER_CONTEXT=true`。
4. 单节点可以使用 SQLite；多 Gateway 节点建议使用 PostgreSQL，并为所有节点挂载同一私有状态卷或对象存储方案。
5. 设置 `AGENT_BASE_KNOWLEDGE_ROOT` 作为公共知识库目录。
6. Kubernetes hostPath 模式设置 `USERS_HOST_PATH`；生产 Compose 已映射为 `${AGENT_BASE_HOME}/users`。PVC 模式会自动使用用户级 subPath。
7. 启动服务，通过首次初始化页面创建管理员，再创建普通用户并分别进行冒烟测试。
8. 用两个账号创建相同名称的项目和相同线程号，确认物理目录、检索结果、运行记录及日志互不可见。

## 6. 旧数据迁移

先停止 Gateway，完成备份，再查出将继承旧数据的内部用户 ID（不是邮箱）。先执行预演：

```powershell
Set-Location backend
$env:PYTHONPATH = "packages/harness;."
..\.venv\Scripts\python.exe scripts\migrate_user_isolation.py --dry-run --user-id <管理员用户ID>
```

确认报告后去掉 `--dry-run`。若 SQLite 不在默认位置，增加 `--db-path <agent_base.db>`。脚本会迁移旧线程、全局记忆、自定义智能体、项目和申报草稿；已有目标数据不会被覆盖，而会移入 `AGENT_BASE_HOME/migration-conflicts/` 供人工核对。脚本可重复运行。

旧 `AGENT_BASE_KNOWLEDGE_ROOT` 保留为公共知识库，不会迁入某个用户。如旧知识库包含私密材料，应在启用多用户服务前手工移入对应用户的 `knowledge_base/`。

## 7. 验收清单

- 未登录请求访问受保护 API 返回 401；普通用户修改共享配置或公共知识库返回 403。
- 用户 A 猜测用户 B 的线程、项目、文件、运行 ID 时返回 404/403，不返回内容。
- 两个用户使用相同 `thread_id` 时获得不同沙箱 ID、目录和 MCP 会话。
- 私有检索只合并“本人私有 + 公共”，不会出现其他用户条目。
- `users/{user_id}/logs/`、记忆、缓存和产物只包含该用户数据。
- 服务重启后，数据库归属、文件目录和运行历史仍保持一致。

出现问题时先停止写入并恢复备份，不要通过关闭严格用户上下文来临时绕过错误；这会重新引入跨用户共享目录风险。
