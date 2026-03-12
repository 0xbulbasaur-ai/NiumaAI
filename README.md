# NiumaAI

Silent watchdog for long-running AI workflows.

NiumaAI helps keep local AI agents working by automatically resuming interrupted tasks, reducing manual babysitting, and avoiding visible console popups during background execution.

[English](#english) | [中文](#中文)

## English

### What NiumaAI Is

NiumaAI is a lightweight watchdog for long-running AI workflows and agent automation.

It is designed for people who want to:

- keep AI tasks running for longer without manual intervention
- auto-resume interrupted agent sessions
- reduce friction in local background execution
- build a more reliable loop around AI-assisted work

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

### Privacy And Portability

This public copy removes user-specific absolute paths. Runtime paths resolve from `%USERPROFILE%` or `Path.home()`.

Machine-specific data is intentionally not included:

- live `.codex` state databases
- local logs and attempt history
- pinned thread IDs
- local account details

### Requirements

- Windows
- Python 3.12+
- local Codex installation
- Node runtime under `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64`
- a working local Codex login

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

### Install

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

### Usage

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

NiumaAI 是一个面向长时间运行 AI 工作流的静默 watchdog。

它的目标不是改进模型本身，而是解决本地 AI 持续运行时常见的“运行层问题”，例如：

- 任务中途停掉
- 会话被打断后没人继续
- 本地执行时不断弹出控制台窗口
- 缺少一个足够轻量的守护层去维持 AI 持续工作

如果你想让本地 AI agent、自动化任务、长流程生成或持续执行型工作流更稳定，它就是一个很直接的起点。

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

### 仓库结构

- `skill/`：skill 定义和 agent 元数据
- `scripts/`：PowerShell 与 Python 守护脚本
- `examples/`：可直接改用的示例配置

### 隐私与可移植性

这个公开版已经去掉了用户专属绝对路径，运行时路径统一从 `%USERPROFILE%` 或 `Path.home()` 推导。

刻意不包含以下本机数据：

- live `.codex` 状态库
- 本地日志和尝试记录
- pinned thread ID
- 本地账号细节

### 依赖要求

- Windows
- Python 3.12+
- 已安装本地 Codex
- `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64` 下有 Node
- 本地 Codex 已登录

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

### 安装方法

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

### 使用

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
