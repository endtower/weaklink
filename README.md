# 弱链接 / WeakLink

在 [最新发布](https://github.com/endtower/weaklink/releases/latest) 下载 **AbyssLauncher.exe** 并双击运行。启动器统一管理 Core、消息接入和 SnowLuma。让 AI 帮你安装时，请它先读 [安装指南](dev/docs/AGENT-INSTALL.md)。

已经在本地工作区装好程序时，可以双击根目录的 `启动弱链接.cmd` 打开本地运行版。

## 源码在哪

全部源码在 [`dev/`](dev/) 下，按组件分目录：

| 组件 | 位置 | 说明 |
|---|---|---|
| **Core**（大脑） | [`dev/brain/`](dev/brain/) | 决策层 `brain/pfc/`、注意层 `brain/att/`、记忆、人格、视觉等 |
| | [`dev/adapt/`](dev/adapt/) | 平台接入：QQ（OneBot）、微信桥、网页 |
| | [`dev/memory/`](dev/memory/) | 记忆存储与向量检索 |
| | [`dev/config/`](dev/config/) | 模型接入、角色设定等配置 |
| **管理服务** | [`dev/manager_service.py`](dev/manager_service.py) | 后台 HTTP 服务（端口 49990），启动器通过它控制各组件 |
| | [`dev/manager_updates.py`](dev/manager_updates.py) | 组件更新、下载、安装与回滚 |
| | [`dev/startup_workflow.py`](dev/startup_workflow.py) | 一键启动流程执行器 |
| **启动器**（桌面窗口） | [`dev/launcher/`](dev/launcher/) | WPF 界面，C# / .NET 8 |
| **更新器** | [`dev/updater/`](dev/updater/) | 安装事务与回滚 |
| **网页界面** | [`dev/web_frontend/`](dev/web_frontend/) | 管理控制台前端（Vue + Vite） |
| **构建脚本** | [`dev/scripts/`](dev/scripts/) | 打发布包、生成组件 ZIP 与更新清单 |

入口文件：`dev/main.py`（Core）、`dev/manager.py`（管理服务）。

## 组件更新的独立性

Core、SnowLuma、启动器各自有独立的版本号和更新清单，**互不牵动**：

| 更新谁 | 会暂停谁 |
|---|---|
| Core | Core 与消息接入（ingress）；SnowLuma 登录状态保留 |
| SnowLuma | 只有它自己 |
| 启动器 | 只重开窗口，后台服务不动 |
| 管理服务 | 它管着的进程会短暂停止，之后按原状态恢复 |

组件版本在 [`dev/component_versions.json`](dev/component_versions.json) 统一登记，
发布说明在 [`dev/releases/`](dev/releases/)。

## 本地工作区的七个区域

| 目录 | 内容 |
|---|---|
| `app/` | 正在使用的启动器、各组件源码和自带运行环境 |
| `data/` | 个人配置、记忆、人格、会话、附件、日志和界面设置；不要删除或移动 |
| `external/` | 第三方程序；内部配置、登录状态和数据位置遵循上游 |
| `dev/` | 开发源码、公共默认值、构建脚本、测试与发布说明 |
| `cache/` | 下载、构建、隔离测试和工具链；旧产物暂存于 `legacy-*` 中 |
| `backups/` | 更新、源码、历史数据与本次目录整理的备份 |
| `private/` | 私人资料、历史交接、参考图、实验项目和旧构建工具 |

`app/AbyssLauncher.exe` 是打包的桌面入口。管理服务、Core 和消息接入以源码运行，程序随包提供所需的运行环境。

> `app / data / external / cache / backups / private` 都在 `.gitignore` 里，不进仓库。

## 历史

项目原名 N_Touch（界面叫 Abyss），2026-11 更名为「弱链接 / WeakLink」。
改名前的最后状态保存在 [`n-touch-final` 标签](https://github.com/endtower/weaklink/tree/n-touch-final)。

## 给接手的 Agent

**帮普通用户装机**（从零装、配模型、可选接 QQ）：读 [dev/docs/AGENT-INSTALL.md](dev/docs/AGENT-INSTALL.md)。

开发和改运行版源码：先读 [AGENTS.md](AGENTS.md)。通过 `GET /v1/storage` 确认真实运行位置；管理服务未启动时，检查 `app/abyss-data-dir.txt`、`app/abyss-storage-dir.txt` 和组件目录。

- 修改用户正在使用的功能：操作 `app/components/<组件>/source/`，先备份，修改后重启对应服务。
- 开发公开版本与构建安装包：操作 `dev/`，入口见 [开发与发布指南](dev/README.md)。本机运行版的通用修复需回填 `dev/` 并提交 Git；本机定制留在安装实例。
- 用户数据始终归 `data/`；SnowLuma 安装在 `external/snowluma/`，不接管其内部存储。
- 本地源码修改保护继续有效；不能通过重置安装基线绕过保护。

完整存储规则见 [存储说明](dev/docs/STORAGE.md)。
