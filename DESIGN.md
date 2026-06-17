# Streamlit Data Server — 设计文档

> 版本：v0.2  
> 日期：2026-06-17  
> 状态：开放问题已确认  
> 参考项目：[streamlit_file_downloader](https://github.com/KaffeeCat/streamlit_file_downloader)

---

## 1. 项目概述

### 1.1 目标

将 Streamlit 网站打造成一个**轻量级在线数据库服务**，让多用户通过浏览器或 API 共享结构化数据：

| 角色 | 场景 |
|------|------|
| **A 用户（上传方）** | 将本机 CSV / Excel / JSON 等数据上传到服务器，或直接在网页上建表、写入数据 |
| **B 用户（获取方）** | 在网页查看最新上传的数据，或导出为文件；也可通过 API / SQL 查询获取 |
| **所有用户** | 像使用数据库一样：查表、执行 SELECT；**写操作需 Write Key** |
| **授权用户** | 持 Write Key 者可建表、上传、增删改、执行写 SQL、删表 |

### 1.2 定位

- **不是**生产级 OLTP 数据库，而是面向小团队 / 个人项目的**数据中转与协作面板**
- 借鉴 `streamlit_file_downloader` 的「文件代理 + 清单索引 + 分享链接」模式，升级为「**数据代理 + SQLite 存储 + REST API**」
- 部署简单：单进程 Streamlit + 多 SQLite 文件，可运行于本机、VPS 或 Streamlit Cloud
- **权限模型**：读操作公开；写操作需 `WRITE_API_KEY`（UI 与 API 一致）

### 1.3 非目标（首版不做）

- 细粒度 RBAC（按表/按用户分配不同权限）
- 高并发、分布式、主从复制
- 实时推送 / WebSocket 订阅
- 复杂事务、存储过程、触发器

---

## 2. 参考项目分析

### 2.1 streamlit_file_downloader 架构摘要

```
app.py                  # st.App 入口，注册自定义 Starlette 路由
├── ui.py               # Streamlit 页面（上传、历史、下载、侧边栏）
├── download_service.py # 核心业务：manifest 读写、文件存取、URL 校验
├── download_route.py   # REST 直链：GET /api/download/{stored_name}
├── visit_stats.py      # 访问统计（JSON 持久化）
└── static/downloads/   # 文件存储 + manifest.json 索引
```

**可复用的设计模式：**

| 模式 | 说明 | 本项目映射 |
|------|------|-----------|
| 服务层与 UI 分离 | `download_service.py` 不依赖 Streamlit | `data_service.py` 封装 SQLite 操作 |
| Manifest 索引 | JSON 记录元数据，文件存磁盘 | `datasets` 元数据表 + SQLite 数据文件 |
| 自定义路由 | `st.App(routes=...)` 暴露 REST API | `/api/tables`、`/api/query` 等 |
| 分享链接 | `?dl=stored_name` 深链直达 | `?table=xxx` 深链到表详情 |
| 缓存失效 | `@st.cache_data` + mtime 触发刷新 | 表 schema / 行数变更时清缓存 |
| 启动清理 | `cleanup_orphan_files()` | 清理孤立上传临时文件 |
| 环境变量 | `PUBLIC_BASE_URL`、`STREAMLIT_SERVER_PORT` | 同上，另加 `WRITE_API_KEY`、`MAX_UPLOAD_MB` |
| 多库管理 | manifest 索引多文件 | `_meta_databases` 注册多个 `.sqlite3` 文件 |

### 2.2 与目标需求的差距

参考项目解决的是**二进制文件**分发；本项目需解决**结构化数据**的持久化、schema 演进与 SQL 查询，因此引入 **SQLite** 作为存储引擎，并在 UI 层增加表格编辑器与 SQL 控制台。

---

## 3. 需求分析

### 3.1 功能需求

#### FR-1 数据上传（A 用户）

- 支持上传 **CSV、TSV、Excel (.xlsx)、JSON、JSON Lines**
- **需 Write Key** 方可执行上传与写入
- 上传时可选择：
  - **创建新表**（指定表名、所属数据库、列类型、**最大行数上限**）
  - **追加到已有表**（列名需兼容，追加后不得超过表级 `max_rows`）
  - **替换表**（清空后导入，保留表名与 `max_rows` 配置）
- 显示上传进度与结果摘要（行数、列数、耗时）
- **必填用户昵称**：存入 `created_by` / `uploaded_by`，会话内记住（`st.session_state`）

#### FR-2 数据获取（B 用户）

- **表列表页**：展示所有表，按「最后更新时间」排序，标记「最新上传」
- **表详情页**：分页预览数据、列统计、schema 信息
- **导出**：CSV / JSON / Excel 一键下载（复用 `st.download_button`）
- **获取最新**：侧边栏或首页提供「最近更新」快捷入口

#### FR-3 在线数据库能力

| 操作 | 权限 | UI 方式 | API 方式 |
|------|------|---------|----------|
| 建库 | 写 | 表单创建新 SQLite 文件 | `POST /api/databases` |
| 建表 | 写 | 表单定义列名、类型、`max_rows` | `POST /api/tables` |
| 查表 | 读 | 表格预览 + 筛选 | `GET /api/tables/{name}/rows` |
| 增 | 写 | 表单新增一行 | `POST /api/tables/{name}/rows` |
| 删行 | 写 | 勾选行删除 | `DELETE /api/tables/{name}/rows/{id}` |
| 改 | 写 | 行内编辑（或弹窗） | `PATCH /api/tables/{name}/rows/{id}` |
| 删表 | 写 | 二次确认对话框 | `DELETE /api/tables/{name}?confirm=true` |
| SQL SELECT | 读 | SQL 编辑器 | `POST /api/query`（无 key） |
| SQL 写 | 写 | SQL 编辑器 + Write Key | `POST /api/query` + key |

#### FR-4 元数据与审计

- 每张表记录：`created_at`、`updated_at`、`row_count`、`created_by`（**必填**）、`max_rows`（建表时设定，0=不限）
- 每个数据库文件记录：`db_id`、`display_name`、`file_path`、`created_by`、`created_at`
- 每次上传 / 批量变更写入 `upload_log` 表
- 可选访问统计（复用 `visit_stats` 模式）

### 3.2 非功能需求

| 类别 | 要求 |
|------|------|
| 易部署 | `pip install -r requirements.txt && streamlit run app.py` |
| 数据持久化 | 多 SQLite 文件，位于 `data/databases/*.sqlite3`，元数据库 `data/meta.sqlite3` |
| 上传限制 | 默认单文件 ≤ 50 MB（可配置） |
| 并发 | 适合 ≤ 10 并发用户；写操作串行化（SQLite WAL 模式） |
| 兼容性 | Streamlit ≥ 1.58，与参考项目一致 |

---

## 4. 系统架构

### 4.1 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      客户端                                  │
│   浏览器 (Streamlit UI)    │    脚本 / curl (REST API)       │
└─────────────┬───────────────────────────┬───────────────────┘
              │                           │
              ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Streamlit App (app.py)                     │
│  ┌──────────────┐    ┌──────────────────────────────────┐   │
│  │   ui.py      │    │  api_routes.py (Starlette)       │   │
│  │  - 上传      │    │  GET  /api/databases             │   │
│  │  - 表管理    │    │  GET  /api/tables                │   │
│  │  - 数据编辑  │    │  POST /api/tables  (需 key)      │   │
│  │  - SQL 控制台│    │  POST /api/query                 │   │
│  │  - 导出下载  │    │  GET  /api/export/{name}         │   │
│  └──────┬───────┘    └──────────────┬───────────────────┘   │
│         └────────────┬──────────────┘                        │
│                      ▼                                       │
│         data_service.py + auth.py                            │
│    (多库路由 / schema / CRUD / import / export / SQL)        │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
              ┌───────────────────────┐
              │  data/meta.sqlite3    │  ← 元数据（库/表/日志）
              │  data/databases/      │  ← 用户 SQLite 文件
              │  data/uploads/ (临时)  │
              │  data/visits.json     │
              └───────────────────────┘
```

### 4.2 模块职责

| 模块 | 职责 |
|------|------|
| `app.py` | 应用入口，`st.App("ui.py", routes=build_api_routes())` |
| `ui.py` | 全部 Streamlit 页面与交互 |
| `data_service.py` | 多库连接管理、DDL/DML、导入导出、行数上限校验 |
| `auth.py` | Write Key 校验（UI session + API Header/Query） |
| `api_routes.py` | REST 端点，读公开 / 写需鉴权 |
| `schema.py` | 表名/列名校验、类型映射、Pydantic 或 dataclass 模型 |
| `import_parsers.py` | CSV / Excel / JSON 解析为 DataFrame |
| `visit_stats.py` | 访问统计（从参考项目复制并微调） |

---

## 5. 数据模型

### 5.1 元数据库（`data/meta.sqlite3`，系统表用户不可删）

#### `_meta_databases` — 用户数据库注册

| 列 | 类型 | 说明 |
|----|------|------|
| `db_id` | TEXT PK | 短 UUID，如 `a1b2c3d4` |
| `name` | TEXT UNIQUE | 库名（slug，如 `sales_2026`） |
| `display_name` | TEXT | 展示名称 |
| `file_path` | TEXT | 相对路径，如 `databases/a1b2c3d4_sales.sqlite3` |
| `created_at` | TEXT ISO8601 | 创建时间 |
| `created_by` | TEXT | 创建者昵称（**必填**） |
| `description` | TEXT | 可选描述 |

#### `_meta_tables` — 用户表注册信息

| 列 | 类型 | 说明 |
|----|------|------|
| `name` | TEXT | 表名（库内唯一） |
| `db_id` | TEXT FK | 所属数据库 |
| PK | (`db_id`, `name`) | 联合主键 |
| `display_name` | TEXT | 展示名称 |
| `description` | TEXT | 可选描述 |
| `created_at` | TEXT ISO8601 | 创建时间 |
| `updated_at` | TEXT ISO8601 | 最后修改时间 |
| `created_by` | TEXT | 创建者昵称（**必填**） |
| `row_count` | INTEGER | 缓存行数 |
| `max_rows` | INTEGER | 行数上限，**建表时设定**；`0` 表示不限制 |

#### `_upload_log` — 上传与变更日志

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | TEXT PK | UUID |
| `table_name` | TEXT | 目标表 |
| `action` | TEXT | `create` / `append` / `replace` / `delete_rows` / `sql` |
| `source_filename` | TEXT | 原始文件名 |
| `rows_affected` | INTEGER | 影响行数 |
| `uploaded_at` | TEXT | 时间戳 |
| `uploaded_by` | TEXT | 操作者昵称（**必填**） |
| `db_id` | TEXT | 所属数据库 |

### 5.2 用户数据表（位于各 `data/databases/*.sqlite3`）

- 每张用户表自动包含隐藏主键列 `_rowid INTEGER PRIMARY KEY AUTOINCREMENT`
- 用户定义的列在 `_meta_tables.columns_json` 中登记
- **表名规范**：`^[a-z][a-z0-9_]{0,62}$`，保留字黑名单（`sqlite_`、`_meta` 等）
- **行数上限**：写入前检查 `row_count + 新增行数 <= max_rows`（`max_rows=0` 时跳过）
- **跨库隔离**：表名在不同库可重复；API/UI 通过 `db_id` 或 `db_name` 定位

### 5.3 Schema 存储示例

`_meta_tables.columns_json` 示例：

```json
[
  {"name": "name", "type": "TEXT", "nullable": true},
  {"name": "age", "type": "INTEGER", "nullable": true},
  {"name": "score", "type": "REAL", "nullable": true}
]
```

---

## 6. 功能模块详细设计

### 6.1 上传模块

**流程：**

```
用户选择文件 → 解析预览 (pandas) → 选择目标表与模式
    → data_service.import_dataframe() → 更新 _meta_tables / _upload_log
    → UI 刷新表列表
```

**列类型推断规则：**

| pandas dtype | SQLite 类型 |
|--------------|-------------|
| int64 | INTEGER |
| float64 | REAL |
| bool | INTEGER (0/1) |
| datetime64 | TEXT (ISO8601) |
| object / string | TEXT |

**冲突处理：**

- 追加模式：列集合必须是已有表的子集或完全一致；多余列忽略并 warning
- 替换模式：事务内 `DELETE FROM table` + 批量 `INSERT`
- **行数校验**：导入完成后 `row_count` 不得超过建表时设定的 `max_rows`，否则整批回滚并报错

### 6.2 查询与展示模块

- 默认 `SELECT * FROM {table} ORDER BY _rowid DESC LIMIT 100 OFFSET {page*100}`
- UI 提供：列筛选、简单 WHERE（列 = 值）、排序
- `@st.cache_data` 缓存表列表；`updated_at` 或 `row_count` 变化时 `clear()`

### 6.3 SQL 控制台

- 文本框输入 SQL，选择目标数据库，点击执行
- **权限与安全：**
  - **无 Key**：仅允许 `SELECT`、`PRAGMA`（读）
  - **有 Write Key**（侧边栏已验证）：允许 `INSERT/UPDATE/DELETE/CREATE/DROP`
  - 禁止 `ATTACH`、`LOAD_EXTENSION` 等危险语句（关键字黑名单）
  - 单条语句执行（不允许多语句 `;` 分隔）
  - 写 SQL 同样受表级 `max_rows` 约束（INSERT 前校验）
- 结果以 `st.dataframe` 展示；写操作显示 `rows_affected`

### 6.6 多数据库管理

- 侧边栏或「数据库」Tab 列出 `_meta_databases`
- **创建数据库**（需 Write Key）：输入库名、展示名、昵称 → 生成新 `.sqlite3` 文件并注册
- **切换当前库**：UI 全局 selector；API 通过 `?db={name}` 或 path 前缀 `/api/databases/{db}/tables`
- 删库（需 Write Key + 二次确认）：删除注册记录及对应 `.sqlite3` 文件

### 6.4 导出模块

- 内存中生成文件字节，通过 `st.download_button` 提供（与参考项目 `_make_file_reader` 模式一致）
- API：`GET /api/export/{table_name}?format=csv|json|xlsx`

### 6.5 「最新数据」语义

满足需求「B 用户获取最新上传数据」的两种解读，首版同时支持：

1. **按表维度**：表列表按 `updated_at DESC` 排序，首页展示 Top N
2. **按上传日志**：`_upload_log` 时间倒序，展示最近 N 次上传及跳转链接

深链：`/?table=sales_data` 直达表详情。

---

## 7. REST API 设计

Base URL：`{PUBLIC_BASE_URL}` 或 `http://localhost:8501`

### 7.1 鉴权

| 操作类型 | 是否需要 Key | 传递方式 |
|----------|-------------|----------|
| 读（GET、SELECT query） | 否 | — |
| 写（POST/PATCH/DELETE、写 SQL） | **是** | Header `X-Write-Key: {key}` 或 Query `?key={key}` |

服务端通过环境变量 `WRITE_API_KEY` 配置；未设置时写操作全部拒绝（只读模式）。

写请求 body 中 **`actor`（用户昵称）必填**，写入审计日志。

### 7.2 端点

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/databases` | 读 | 列出所有数据库 |
| POST | `/api/databases` | 写 | 建库 `{name, display_name, actor}` |
| DELETE | `/api/databases/{db}` | 写 | 删库 `?confirm=true` |
| GET | `/api/databases/{db}/tables` | 读 | 列出该库下所有表 |
| POST | `/api/databases/{db}/tables` | 写 | 建表 `{name, columns, max_rows, actor}` |
| DELETE | `/api/databases/{db}/tables/{name}` | 写 | 删表 `?confirm=true&actor=` |
| GET | `/api/databases/{db}/tables/{name}/schema` | 读 | 获取 schema（含 `max_rows`） |
| GET | `/api/databases/{db}/tables/{name}/rows` | 读 | 分页 `?limit=&offset=&order=` |
| POST | `/api/databases/{db}/tables/{name}/rows` | 写 | 插入 `{actor, ...columns}` |
| PATCH | `/api/databases/{db}/tables/{name}/rows/{id}` | 写 | 更新一行 |
| DELETE | `/api/databases/{db}/tables/{name}/rows/{id}` | 写 | 删除一行 |
| POST | `/api/databases/{db}/import/{name}` | 写 | multipart + `?mode=append\|replace&actor=` |
| GET | `/api/databases/{db}/export/{name}` | 读 | `?format=csv\|json\|xlsx` |
| POST | `/api/databases/{db}/query` | 读/写 | `{sql, actor}`；写 SQL 需 key |
| GET | `/api/uploads/recent` | 读 | 最近上传日志 `?limit=` |

**响应格式：**

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

错误时 HTTP 4xx/5xx，`ok: false`，`error` 为可读消息。

---

## 8. UI 设计

### 8.1 页面结构（单页多 Tab，与参考项目 wide layout 一致）

```
┌────────────────────────────────────────────────────────────┐
│  Header: Streamlit Data Server — Online Database           │
├──────────────┬─────────────────────────────────────────────┤
│  Sidebar     │  Main                                       │
│  - 用户昵称*  │  Tab: [上传] [数据表] [SQL] [最近更新]        │
│  - Write Key │                                             │
│  - 当前数据库 │  ...                                        │
│  - 服务器信息 │                                             │
│  - 访问统计   │                                             │
│  - 关于      │                                             │
└──────────────┴─────────────────────────────────────────────┘
```

### 8.2 Tab 说明

| Tab | 内容 |
|-----|------|
| **上传** | 需昵称 + Write Key；选库/建表、`max_rows`、预览、建表/追加/替换 |
| **数据表** | 左：表列表（含行数/上限）；右：预览、增删改（写需 key）、导出 |
| **SQL** | 选库 + SQL 输入；无 key 仅 SELECT，有 key 可写 |
| **最近更新** | `_upload_log` 时间线，展示操作者与所属库 |

### 8.3 视觉风格

复用参考项目 CSS 变量与 card 组件（`_card_open`、`btn-primary`、`_meta_chip`），保持同一作者系列产品的视觉一致性。

---

## 9. 技术选型

| 层次 | 选型 | 理由 |
|------|------|------|
| Web 框架 | Streamlit ≥ 1.58 | 与参考项目一致；快速构建数据应用 |
| HTTP 路由 | Starlette（`st.App` routes） | 参考项目已验证 REST 直链方案 |
| 数据库 | SQLite 3 + WAL | 零配置、单文件、支持 SQL |
| 数据处理 | pandas | 导入导出、类型推断 |
| Excel | openpyxl | 读写 xlsx |
| HTTP 客户端 | requests | 侧边栏 IP 地理信息（可选） |

**requirements.txt（规划）：**

```
streamlit>=1.58.0
pandas>=2.0.0
openpyxl>=3.1.0
requests>=2.31.0
```

---

## 10. 目录结构（规划）

```
streamlit_data_server/
├── app.py                 # 入口
├── ui.py                    # Streamlit UI
├── data_service.py          # 多库 SQLite 业务逻辑
├── auth.py                  # Write Key 校验
├── api_routes.py            # REST API
├── schema.py                # 校验与类型
├── import_parsers.py        # 文件解析
├── visit_stats.py           # 访问统计
├── requirements.txt
├── .streamlit/
│   └── config.toml          # maxMessageSize 等
├── data/
│   ├── meta.sqlite3         # 元数据库（gitignore）
│   ├── databases/           # 用户 SQLite 文件（gitignore）
│   ├── uploads/             # 上传临时文件（gitignore）
│   └── visits.json
├── DESIGN.md                # 本文档
└── README.md
```

---

## 11. 安全与风险

### 11.1 权限策略（已确认）

```
┌─────────────────────────────────────────┐
│  读操作（SELECT / GET / 导出 / 预览）     │  → 公开，无需 Key
├─────────────────────────────────────────┤
│  写操作（建库表 / 上传 / CRUD / 写SQL）   │  → 需 WRITE_API_KEY
├─────────────────────────────────────────┤
│  审计字段 actor（用户昵称）               │  → 所有写操作必填
└─────────────────────────────────────────┘
```

- **UI**：侧边栏输入昵称（必填）与 Write Key；Key 验证通过后存入 `st.session_state.write_authorized`
- **API**：写请求携带 `X-Write-Key`；`actor` 写入 `_upload_log`
- **未配置 Key**：`WRITE_API_KEY` 为空时服务以**只读模式**运行，写 UI 禁用并提示

### 11.2 必要防护

| 风险 | 措施 |
|------|------|
| 未授权写入 | 所有写端点经 `auth.require_write_key()` |
| Key 泄露 | README 建议定期轮换；HTTPS 部署 |
| SQL 注入 | 参数化 CRUD；自由 SQL 用黑名单 + 单语句 |
| 路径遍历 | 库名/表名严格正则；文件路径仅由 `db_id` 映射 |
| 超大上传 | `MAX_UPLOAD_MB` + Streamlit `maxMessageSize` |
| 磁盘占满 | 表级 `max_rows` + 可选全局库大小软限制 |
| 误删库表 | UI 二次确认；API 需 `confirm=true` |

### 11.3 后续可选增强

- 多 Key 轮换（`WRITE_API_KEYS` 逗号分隔，任一有效即可）
- 表级只读标记（`read_only` 列，覆盖全局写权限）
- 按库分配不同 Write Key

---

## 12. 部署

### 12.1 本地

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 12.2 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `PUBLIC_BASE_URL` | 空 | 公网访问基础 URL |
| `STREAMLIT_SERVER_PORT` | 8501 | 端口 |
| `META_DB_PATH` | `data/meta.sqlite3` | 元数据库路径 |
| `DATABASES_DIR` | `data/databases` | 用户库文件目录 |
| `WRITE_API_KEY` | 空 | 写操作密钥；空=只读模式 |
| `MAX_UPLOAD_MB` | 50 | 上传大小上限 |

### 12.3 Streamlit Cloud

- `data/` 目录在 redeploy 后会丢失 → README 说明需挂载持久化卷或使用外部 SQLite 路径
- 与参考项目相同：`PUBLIC_BASE_URL` 设为 Cloud 应用 URL

---

## 13. 开发里程碑

### Phase 1 — MVP（核心闭环）

- [ ] 元数据库 + 默认用户库初始化
- [ ] `auth.py`：Write Key 校验 + 昵称必填
- [ ] CSV 上传 → 建表（含 `max_rows`）/ 追加
- [ ] 表列表 + 分页预览（读公开）
- [ ] CSV 导出下载
- [ ] 基础 UI（侧边栏昵称/Key + 上传 + 数据表 Tab）

### Phase 2 — 多库 + CRUD + API

- [ ] 多数据库创建 / 切换 / 删除
- [ ] Excel / JSON 导入
- [ ] 行级增删改（写需 Key）+ 行数上限校验
- [ ] REST API 全套端点（读/写分离鉴权）
- [ ] SQL 控制台（无 Key SELECT / 有 Key 写）

### Phase 3 — 体验与运维

- [ ] 最近更新 Tab + 深链 `?db=&table=`
- [ ] 侧边栏服务器信息 / 访问统计
- [ ] 删库删表二次确认
- [ ] README 与部署文档

### Phase 4 — 可选增强

- [ ] 多 Key 轮换、表级只读
- [ ] 表 schema 在线修改（加列）
- [ ] Python SDK 示例脚本（`upload.py` / `fetch_latest.py`）

---

## 14. 典型用户故事

### 故事 A：CSV 共享

1. A 在侧边栏填写昵称「Alice」、Write Key，本地准备 `sales_q1.csv`
2. 上传 Tab → 库 `default` → 创建表 `sales_q1`，`max_rows=100000` → 上传
3. B **无需 Key** → 数据表 Tab → 预览 → 下载 CSV
4. B：`curl {base}/api/databases/default/export/sales_q1?format=csv -o sales_q1.csv`

### 故事 B：协作维护一张表

1. 授权用户创建库 `warehouse`，建表 `inventory`（`max_rows=50000`）
2. 持 Key 用户通过 UI/API 增删改；写入时校验行数上限
3. 任意用户 SQL Tab（无 Key）：`SELECT warehouse, SUM(qty) FROM inventory GROUP BY warehouse`
4. 「最近更新」显示：`Bob · warehouse/inventory · append 200 rows · 5 min ago`

### 故事 C：脚本自动化

```python
import requests

BASE = "http://localhost:8501"
KEY = "your-write-key"
headers = {"X-Write-Key": KEY}

# 写：上传（需 key + actor）
files = {"file": open("data.csv", "rb")}
r = requests.post(
    f"{BASE}/api/databases/default/import/my_table?mode=replace&actor=Alice",
    files=files,
    headers=headers,
)

# 读：无需 key
r = requests.get(f"{BASE}/api/uploads/recent?limit=1")
entry = r.json()["data"][0]
db, table = entry["db_id"], entry["table_name"]
r = requests.get(f"{BASE}/api/databases/{db}/export/{table}?format=json")
```

---

## 15. 已确认决策

| # | 问题 | **确认结果** |
|---|------|-------------|
| 1 | 用户昵称 / 身份标识 | **需要**。所有写操作必填 `actor`，UI 侧边栏强制输入，会话内记住 |
| 2 | 删表 / 删库 | **允许**。UI 二次确认；API 需 `confirm=true` + Write Key |
| 3 | 公网读写权限 | **读公开、写需 Key**。GET/SELECT/导出无需密钥；POST/PATCH/DELETE/写 SQL 需 `WRITE_API_KEY` |
| 4 | 单表最大行数 | **建表时设定** `max_rows`（0=不限），写入时强制校验，超限拒绝并回滚 |
| 5 | 多 SQLite 文件 | **支持**。元库 `meta.sqlite3` 管理多个 `data/databases/*.sqlite3`，UI/API 可建库切换 |

---

## 16. 总结

本项目在 `streamlit_file_downloader` 的**轻量 Streamlit + 本地持久化 + REST 路由**架构上，将「文件 manifest」升级为「**元数据库 + 多 SQLite 用户库**」，用 pandas 打通导入导出，用 SQL 控制台与 REST API 满足程序化访问。权限上采用**读公开、写需 Key + 昵称审计**，表级 `max_rows` 在创建时配置，适合公网只读分享 + 小团队授权写入的场景。

下一步：按 Phase 1 里程碑开始编码实现。
