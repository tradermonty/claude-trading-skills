# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A daily market dashboard application built with Streamlit and Claude Agent SDK. It runs 5 trading skills (FTD Detector, Uptrend Analyzer, Market Breadth, Theme Detector, VCP Screener) in parallel to generate a unified dashboard, then provides an interactive chat interface for discussing the results with a market-advisor agent. No API keys are required for 3 of 5 skills; FTD Detector and VCP Screener show N/A without `FMP_API_KEY` (free tier sufficient).

## Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env   # Set ANTHROPIC_API_KEY (optional if using subscription)

# Generate dashboard
python3 generate_dashboard.py --project-root ../..
python3 generate_dashboard.py --project-root ../.. --lang ja

# Run
streamlit run app.py
```

## Architecture

```
app.py                  Streamlit UI (entry point) — Dashboard tab + Chat tab
  ↓ uses
agent/client.py         ClaudeChatAgent: wraps SDK streaming responses
  ↓ uses
agent/async_bridge.py   AsyncBridge: runs async coroutines in Streamlit's sync context
agent/attachments.py    Server-side attachment persistence for txt/md/csv/json
agent/knowledge.py      knowledge/*.md listing + on-demand rg search
agent/context_builder.py Prompt context composer with character budget
agent/sanitizer.py      Output sanitizer: redacts secrets and system paths
agent/_sdk_patch.py     Monkey-patch for unrecognized SDK message types
config/settings.py      .env → environment variable loading and constants

generate_dashboard.py   5-skill parallel execution → unified markdown report
```

### Streamlit ↔ async Integration

Streamlit reruns scripts synchronously, so `AsyncBridge` maintains a persistent `asyncio` event loop and dispatches SDK coroutines via `run_until_complete()`. Both `AsyncBridge` and `ClaudeChatAgent` are stored in `st.session_state` to survive reruns.

### SDK Client Flow

`ClaudeChatAgent.send_message_streaming()` connects to `ClaudeSDKClient` and normalizes `StreamEvent` (text deltas), `AssistantMessage` (complete text), `ToolUseBlock` (tool calls), and `ResultMessage` (errors/completion) into `StreamChunk` dicts that the UI consumes.

### Sandbox Trade-off

- SDK sandbox mode is controlled by `CLAUDE_SDK_SANDBOX_ENABLED` (`false` by default).
- Default `false` keeps behavior aligned with project-level permission policies in `.claude/settings.json`.
- For stricter runtime isolation, set `CLAUDE_SDK_SANDBOX_ENABLED=true`.

## Configuration

| Location | Purpose |
|---|---|
| `.env` | `ANTHROPIC_API_KEY`, `FMP_API_KEY`, `CLAUDE_MODEL`, `APP_LOCALE`, knowledge/context settings |
| `.claude/agents/market-advisor.md` | Market advisor persona (frontmatter + system prompt) |
| `.claude/skills` | Symlink to `../../skills/` — all trading skills available |
| `.mcp.json` | MCP server definitions (optional) |
| `.claude/settings.json` | Project-level permission rules |
| `knowledge/*.md` | Auto-generated dashboards referenced at answer time |

## Sandbox Rules — Code Execution via Chat UI

This project runs a Claude Agent through a Streamlit chat UI. When the agent creates and executes scripts on behalf of the user, it **must** follow these rules.

### File Creation Rules

- User-requested scripts must be placed in the **`scripts/` directory**
- The following files and directories must **never** be overwritten, modified, or deleted:
  - `app.py`, `generate_dashboard.py`
  - `agent/` (all files)
  - `config/` (all files)
  - `.claude/` (all files)
  - `.env`, `.env.example`
  - `requirements.txt`
  - `CLAUDE.md`, `README.md`
  - `.mcp.json`

### Security Rules (Mandatory)

The following rules **must never be violated under any circumstances**.

1. **No access to secrets**
   - Never write code that reads, displays, or outputs the contents of `.env`
   - Never display, log, or write authentication credentials such as `ANTHROPIC_API_KEY`

2. **No exposure of internal paths or system information**
   - Never include absolute paths (`/Users/...`, `/home/...`) in responses
   - Always use project-relative paths (e.g., `scripts/demo.py`, `knowledge/`)
   - Summarize tool outputs in your own words; never paste raw output containing system paths

## Key Dependencies

- `streamlit` >= 1.42.0
- `claude-agent-sdk` >= 0.1.35
- `python-dotenv` >= 1.0.0
- `requests` >= 2.31.0
