# NiumaAI

Keep pinned AI coding sessions moving by auto-resuming interrupted work in the background.

NiumaAI is a small watchdog layer for local AI workflows. It watches a pinned session, detects when work has stopped, and quietly resumes it through the CLI. On Windows it can run without visible console popups, exposes tray controls, and gives you a live monitor plus a manual takeover path.

[English](#english) | [中文](#中文)

## English

### At A Glance

- Keeps a pinned AI session moving without constant babysitting
- Resumes interrupted work in the background
- Exposes pause, resume, status, and monitoring controls
- Lets you take over the same session manually when needed

### Best Way To Use It

For most people, the right path is not manual setup.

1. Give this repository to Codex, Claude Code, or another coding agent and ask it to install or adapt NiumaAI.
2. Pin the session you want kept alive.
3. Ask the agent to start, pause, resume, or inspect NiumaAI.
4. Use the Windows tray icon for live status, pause and resume, or manual takeover.

If you are using the current Codex app, do not assume the foreground UI will always reflect background progress in real time. The tray monitor is the more reliable place to check live state.

### What The Watchdog Actually Does

NiumaAI does not replace the agent. It adds a thin operational layer around an existing workflow.

The current default behavior is:

1. target the first pinned thread (`thread_scope = pinned:first`)
2. poll local state every 2 seconds by default
3. detect stoppage or an interrupted resumable state
4. launch a background command equivalent to `codex exec resume <thread_id> continue --json`
5. expose status, pause, resume, monitoring, and manual takeover through scripts and the Windows tray

This is why the project is useful: it is a lightweight wrapper around a real working session, not a separate AI runtime.

### Why It Exists

Many local AI workflows fail for operational reasons rather than model quality:

- a session stalls mid-task
- the app loses continuity
- visible console windows are noisy and distracting
- nobody notices the stopped state until much later

NiumaAI focuses on that operational gap.

### Current Status

The practically validated setup today is Codex on Windows.

That is the environment where the watchdog, tray controls, and resume flow have been exercised together. The project is still structured to be portable: the core pattern is simple enough that another coding agent should be able to adapt it to other local runtimes.

### Good Fit

NiumaAI is a good fit if you want:

- longer-running AI coding or content-generation sessions
- a local agent workflow that keeps moving in the background
- a quiet resume path that does not keep flashing terminal windows
- tray-based monitoring and manual takeover on Windows

### Porting To Other Environments

The current proven path is Codex on Windows, but the design is intentionally small and direct.

If you want to use the same idea on macOS, Claude Code, or another local agent runtime, the recommended approach is to give this repository to the target coding agent and ask it to adapt the watchdog for that environment.

The underlying pattern is:

1. observe local state
2. detect stoppage
3. resume through a stable local interface
4. keep the background path quiet
5. expose status and manual takeover

### Manual Install

This section is mainly for people who want to install or inspect the Windows setup directly.

Requirements:

- Windows
- Python 3.12+
- local Codex installation
- Node runtime under `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64`
- a working local Codex login

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

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

### Repository Structure

- `skill/`: skill definition and agent-facing metadata
- `scripts/`: PowerShell and Python watchdog scripts
- `examples/`: sample config you can adapt locally

### Current Boundaries

- Windows-first
- practically validated on Codex + Windows today
- built around the pinned-session or pinned-thread model
- helper scripts currently assume a local Codex install and its CLI layout

## 中文

### 一句话理解

NiumaAI 是一个给本地 AI 工作流补“运行保障层”的小型 watchdog，可以在后台自动续跑被 pin 住的 session。

它更像一个低延迟监工层：持续观察目标 session，一旦发现工作停住，就通过后台 CLI 注入 `continue`，尽量缩短空转时间，同时避免反复弹出可见控制台窗口。

### 最推荐的人类使用方式

对大多数人来说，最合适的做法不是自己先研究脚本，而是：

1. 把这个仓库链接交给 Codex、Claude Code 或其他 coding agent，让它帮你安装或适配。
2. 把需要持续工作的 session 先 pin 住。
3. 直接让 agent 帮你执行启动、暂停、继续、状态检查等动作。
4. 需要看实时状态、暂停继续或人工接管时，再使用 Windows 右下角的托盘入口。

如果你用的是当前版本的 Codex app，不要默认它一定会实时反映后台运行进度。想看更可靠的实时状态，优先看托盘监控。

### 它实际上在做什么

NiumaAI 不是替代 agent，而是在现有工作流外面补一层很薄的运行控制。

当前默认逻辑是：

1. 默认盯住第一个 pinned thread（`thread_scope = pinned:first`）
2. 默认每 2 秒轮询一次本地状态
3. 识别停滞或可恢复的中断状态
4. 在后台执行等价于 `codex exec resume <thread_id> continue --json` 的续跑命令
5. 通过脚本和 Windows 托盘暴露状态查看、暂停继续、实时监控和人工接管入口

所以它的价值不在于“另起一套 AI runtime”，而在于给真实在跑的 session 加上一层轻量、可控、可迁移的运行保障。

### 为什么会需要它

很多本地 AI 工作流出问题，并不是模型本身不行，而是运行层很脆：

- session 中途停掉
- app 状态断掉了但没人及时发现
- 后台命令总弹控制台窗口
- 过了很久才发现任务早就停了

NiumaAI 处理的就是这类运行层问题。

### 当前状态

现在真正跑通过、验证过的环境，是 Windows 上的 Codex 本地工作流。

也正因为如此，README 里会明确说它在这个组合下是实测可用的。但项目本身并不打算只服务于 Codex。它的核心结构很小，逻辑也直接，后续让别的 coding agent 迁移到其他环境并不难。

### 适合什么场景

如果你想要下面这些能力，这个项目就比较对路：

- 让 AI coding session 或长流程任务尽量持续推进
- 让本地 agent 在后台继续工作
- 用更安静的方式处理中断恢复，不反复打扰前台
- 在 Windows 上通过托盘看状态和接管当前 session

### 迁移到其他环境

当前验证过的主要路径是 Windows + Codex，但设计本身并不复杂。

如果你想迁移到 macOS、Claude Code 或其他本地 agent 运行时，推荐做法不是手改所有细节，而是把这个仓库直接交给目标 coding agent，让它根据目标环境完成适配。

底层模式就是：

1. 观察本地状态
2. 识别停滞
3. 通过稳定入口恢复执行
4. 保持后台路径尽量安静
5. 暴露状态与人工接管入口

### 手动安装

这一节主要面向希望自己直接安装或检查 Windows 方案的人。

依赖要求：

- Windows
- Python 3.12+
- 已安装本地 Codex
- `%USERPROFILE%\.codex\tools\node-v24.13.1-win-x64` 下有 Node
- 本地 Codex 已登录

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

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

### 仓库结构

- `skill/`：skill 定义和面向 agent 的元数据
- `scripts/`：PowerShell 与 Python watchdog 脚本
- `examples/`：可本地改用的示例配置

### 当前边界

- 当前以 Windows 为主
- 目前真正实测通过的是 Codex + Windows
- 设计建立在 pinned session 或 pinned thread 模型之上
- 现有辅助脚本默认围绕本地 Codex 安装和 CLI 路径展开

## License

MIT
