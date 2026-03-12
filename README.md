# NiumaAI

Silent watchdog that auto-resumes pinned AI sessions for long-running AI workflows.

NiumaAI acts like a low-latency supervisor for local AI work: it watches a pinned session, detects when work stops, and injects `continue` through Codex CLI in the background so the workflow keeps moving with minimal idle time and no visible console popups.

[English](#english) | [中文](#中文)

## English

### What NiumaAI Is

NiumaAI is a lightweight watchdog for long-running AI workflows and agent automation.

It is designed for people who want to:

- keep AI tasks running for longer without manual intervention
- auto-resume interrupted agent sessions
- reduce friction in local background execution
- build a more reliable loop around AI-assisted work

If you are a human user rather than a script maintainer, the default path is simple: give this repository to Codex, Claude Code, or another coding agent, ask it to install or adapt NiumaAI, pin the session you want kept alive, and then control the workflow through the agent or the Windows tray.

The current proven setup is Windows with a Codex-based local workflow, but the project structure is intentionally small and simple. The core pattern should be portable to other AI runtimes, wrappers, or desktop environments.

### Why This Repo May Be Useful

Many local AI workflows fail for operational reasons rather than model quality:

- a session stops mid-task
- the local app loses continuity
- a command wrapper opens visible console windows
- there is no small watchdog layer to keep the workflow alive

NiumaAI focuses on that operational gap.

### Core Capabilities

- silent auto-resume for interrupted AI workflows
- `start`, `pause`, `resume`, `status`, and `stop` controls
- verification script for setup and silent-mode prerequisites
- repair script for common local configuration issues
- monitor scripts for session visibility
- scheduled-task installer for startup automation

### Quick Start for Humans

For most users, you should not manually study each script first. The practical path is to give this repository to a coding agent and let it install or adapt NiumaAI for the local machine.

Recommended workflow:

1. Give this GitHub repository to Codex and ask it to install or adapt NiumaAI for your environment.
2. In Codex, pin the session you want to keep running.
3. Ask Codex to start, pause, resume, or inspect NiumaAI.
4. Use the Windows tray icon to pause, continue, open the live session monitor, or open an interactive Codex CLI attached to the current workflow.
5. NiumaAI performs resume work through Codex CLI in the background, so it does not depend on keeping the foreground app open.

Important notes:

- the current Codex app may not show background progress in real time
- for live status, use the tray monitor
- if you want to take over directly, open the interactive CLI from the tray

### How It Works

NiumaAI does not replace the agent. It adds a thin operational layer around an existing workflow.

The current default logic is:

1. you pin the session or thread you want to keep alive
2. the watchdog targets the first pinned thread by default (`thread_scope = pinned:first`)
3. it polls local state every 2 seconds by default
4. when it detects stoppage or an interrupted resumable state, it launches a background command equivalent to `codex exec resume <thread_id> continue --json`
5. status, pause, resume, monitoring, and manual takeover are exposed through agent commands and the Windows tray

That is why the project is useful: it is a small wrapper around a real workflow, not a separate AI runtime.

### Validation Status

This repository has been practically validated in a real Codex + Windows environment.

That matters for confidence, but the repository is not positioned as Codex-only. The architecture is straightforward:

1. observe local state
2. detect interruption or stoppage
3. resume through a stable local interface
4. keep the process quiet and inspectable

That pattern is generic enough to be migrated to other AI environments with relatively low effort.

### Repository Structure

- `skill/`: skill definition and agent metadata
- `scripts/`: PowerShell and Python watchdog scripts
- `examples/`: sample config you can adapt locally

### Porting To Other Environments

The current proven workflow is Codex on Windows.

If you want to use the same idea in other environments such as macOS, Claude Code, or another local agent runtime, the recommended path is to give this repository to the target coding agent and ask it to adapt the watchdog to that environment.

The underlying pattern is simple:

1. detect interruption or stoppage
2. resume through a stable local interface
3. keep background execution quiet
4. expose status and manual control

### Requirements

These requirements matter if you or your agent are doing a manual Windows install.

- Windows
- Python 3.12+
- local Codex installation
- Node runtime under `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64`
- a working local Codex login

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

### Manual Install

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_to_codex_home.ps1
```

This copies the skill into `%USERPROFILE%\.codex\skills\codex-continue-watchdog` and the scripts into `%USERPROFILE%\.codex\scripts`.

### Configure

Copy the example config:

```powershell
Copy-Item .\examples\continue-watchdog.example.json "$env:USERPROFILE\.codex\continue-watchdog.json"
```

If your main workspace is not `%USERPROFILE%\Desktop\Projects`, set:

```powershell
$env:NIUMAAI_DEFAULT_CWD = "D:\path\to\workspace"
```

### Direct Script Control (Optional)

```powershell
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" start
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" status
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" pause
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" resume
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" stop
```

Verification:

```powershell
python "$env:USERPROFILE\.codex\scripts\verify_silent_watchdog.py"
```

Repair:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\scripts\setup_silent_watchdog.ps1"
```

### Search Keywords

Relevant search and discovery terms for this project:

- long-running AI workflows
- AI agent watchdog
- auto resume interrupted AI tasks
- local AI automation
- background AI agent execution
- silent watchdog for AI workflows
- Windows agent automation

### Current Constraints

- Windows-focused
- currently validated around a Codex local workflow
- assumes the target thread or workflow is intentionally kept alive by the user
- MCP setup logic is opinionated and optimized for direct `node.exe` execution

## 中文

### NiumaAI 是什么

NiumaAI 是一个面向长时间运行 AI 工作流的静默 watchdog，可以自动续跑被 pin 住的 session。

你也可以把它理解成一个低延迟的 AI 监工层：它会持续观察目标 session，一旦发现工作停住，就通过后台 Codex CLI 注入 `continue`，尽量把空转时间压短，同时避免反复弹出可见控制台窗口。

它的目标不是改进模型本身，而是解决本地 AI 持续运行时常见的“运行层问题”，例如：

- 任务中途停掉
- 会话被打断后没人继续
- 本地执行时不断弹出控制台窗口
- 缺少一个足够轻量的守护层去维持 AI 持续工作

如果你想让本地 AI agent、自动化任务、长流程生成或持续执行型工作流更稳定，它就是一个很直接的起点。

如果你是人类用户，而不是准备自己长期维护这些脚本的人，默认建议其实很简单：把这个仓库直接交给 Codex、Claude Code 或其他 coding agent，让它帮你安装或适配；把需要持续工作的 session pin 住；后续再通过 agent 或 Windows 托盘去控制运行状态。

### 目前验证过的环境

当前已经在真实的 Codex + Windows 本地环境里实测通过。

这说明它在这个组合下不是“概念代码”，而是跑过的版本。但这个项目并不想只服务于 Codex。它的结构很简单，核心逻辑本质上是：

1. 观察本地状态
2. 识别中断或停滞
3. 通过稳定入口恢复执行
4. 尽量保持静默、可监控、可修复

正因为结构简单，它也更容易被迁移到其他 AI 运行环境、桌面自动化场景或本地 agent 框架中。

### 核心能力

- 自动恢复被打断的 AI 工作流
- 提供 `start`、`pause`、`resume`、`status`、`stop` 控制
- 提供验证脚本检查静默运行前提
- 提供修复脚本处理常见本地配置问题
- 提供监控脚本观察当前会话状态
- 支持开机或登录后自动启动

### 面向人类用户的快速使用方式

对大多数人来说，不建议一上来就手动逐个研究脚本。更省事也更符合实际的方式，是把这个仓库直接交给 coding agent，让它在你的机器上安装或适配。

推荐流程：

1. 把这个 GitHub 仓库链接交给 Codex，让它帮你安装或适配 NiumaAI。
2. 在 Codex 里把你希望持续运行的 session 先 pin 住。
3. 直接让 Codex 帮你执行 NiumaAI 的启动、暂停、继续、状态检查等动作。
4. 在 Windows 右下角托盘里，你可以暂停、继续、打开实时监控，或者直接打开接管当前工作流的交互式 Codex CLI。
5. NiumaAI 通过后台的 Codex CLI 执行恢复动作，因此不依赖前台 app 一直开着。

需要注意：

- 当前 Codex app 不一定会实时显示后台运行状态
- 如果你要看实时状态，优先使用托盘里的监控入口
- 如果你要人工接管，优先从托盘打开交互式 CLI

### 工作原理

NiumaAI 并不是要替代 agent 本身，而是在现有 agent 工作流外面补一层很薄的运行保障。

当前默认逻辑是：

1. 先由你 pin 住要持续工作的 session 或 thread
2. watchdog 默认盯住第一个 pinned thread（`thread_scope = pinned:first`）
3. 默认每 2 秒轮询一次本地状态
4. 一旦识别到停滞或可恢复的中断状态，就在后台执行等价于 `codex exec resume <thread_id> continue --json` 的续跑命令
5. 暂停、继续、状态查看、实时监控、人工接管入口都暴露给 agent 命令和 Windows 托盘

这也是它和“重新做一个 AI runtime”不同的地方：它更像是在真实工作流外面包了一层轻量、可控、可迁移的运行保障。

### 仓库结构

- `skill/`：skill 定义和 agent 元数据
- `scripts/`：PowerShell 与 Python 守护脚本
- `examples/`：可直接改用的示例配置

### 迁移到其他环境

当前已经验证过的主要路径是 Windows 上的 Codex 本地工作流。

如果你想迁移到其他环境，比如 macOS、Claude Code，或者别的本地 agent 运行时，推荐做法不是手改所有细节，而是把这个仓库直接交给对应的 coding agent，让它基于目标环境完成适配。

底层模式其实很简单：

1. 识别中断或停滞
2. 通过稳定入口恢复执行
3. 保持后台静默运行
4. 暴露状态与人工接管入口

### 依赖要求

这些要求主要针对你或 agent 需要手动在 Windows 上安装的情况。

- Windows
- Python 3.12+
- 已安装本地 Codex
- `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64` 下有 Node
- 本地 Codex 已登录

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

### 手动安装

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_to_codex_home.ps1
```

它会把 skill 复制到 `%USERPROFILE%\.codex\skills\codex-continue-watchdog`，并把脚本复制到 `%USERPROFILE%\.codex\scripts`。

### 配置

复制示例配置：

```powershell
Copy-Item .\examples\continue-watchdog.example.json "$env:USERPROFILE\.codex\continue-watchdog.json"
```

如果你的主要工作目录不是 `%USERPROFILE%\Desktop\Projects`，可以设置：

```powershell
$env:NIUMAAI_DEFAULT_CWD = "D:\path\to\workspace"
```

### 直接脚本控制（可选）

```powershell
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" start
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" status
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" pause
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" resume
powershell -File "$env:USERPROFILE\.codex\scripts\codex_continue_watchdog.ps1" stop
```

验证：

```powershell
python "$env:USERPROFILE\.codex\scripts\verify_silent_watchdog.py"
```

修复：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\scripts\setup_silent_watchdog.ps1"
```

### 有助于被搜索到的关键词

- 长时间运行 AI 工作流
- AI agent 守护进程
- 自动恢复中断的 AI 任务
- 本地 AI 自动化
- 后台持续运行 AI agent
- 静默 watchdog
- Windows AI 自动化

### 当前限制

- 当前版本以 Windows 为主
- 目前实测环境主要是 Codex 本地工作流
- 默认假设用户明确希望维持某个线程或任务持续运行
- MCP 配置逻辑偏向直接 `node.exe` 调用

## License

MIT
