# Github Repository: https://github.com/HFOXH/code_review_agent

# Code Review Agent 🤖🔍

> **Cambrian College — Graduate Certificate in AI | NLP Assignment**  
> Option B: AI Agent with Multi-Tool Orchestration & MCP

---

## Description

The **Code Review Agent** is an AI-powered pipeline that automatically reviews Python source files. Given a `.py` file path, the agent:

1. **Reads** the file through a standardized MCP server (never touching the file system directly).
2. **Lints** the code using [Ruff](https://docs.astral.sh/ruff/), the fastest Python linter available.
3. **Analyzes** complexity using Python's built-in `ast` module — counting functions, classes, branches, and nesting depth.
4. **Generates** a detailed, structured code review using an LLM (OpenAI, Anthropic, or Gemini — your choice).
5. **Saves** the full review as a Markdown report via the MCP server.

---

## Architecture

```
User Input (file path)
        │
        ▼
┌───────────────┐
│   lint_node   │  ← MCP: read_file()  +  Ruff subprocess
└───────┬───────┘
        │  source_code + lint_results
        ▼
┌───────────────┐
│ analyze_node  │  ← Python ast module (no external calls)
└───────┬───────┘
        │  complexity_metrics
        ▼
┌───────────────┐
│  review_node  │  ← LLM API (OpenAI / Anthropic / Gemini)
└───────┬───────┘
        │  review (Markdown text)
        ▼
┌───────────────┐
│  report_node  │  ← MCP: write_report()
└───────┬───────┘
        │
        ▼
   /reports/<file>_<timestamp>.md

────────────────────────────────────────────────────
         ┌─────────────────────────────┐
         │        MCP Server           │
         │  (separate stdio process)   │
         │                             │
         │  ● read_file(path)          │
         │  ● write_report(name, md)   │
         │  ● list_reports()           │
         └─────────────────────────────┘
```

**LangGraph** orchestrates the 4-node directed graph.  
**MCP Server** runs as a subprocess; the agent communicates with it over stdin/stdout using the MCP Python SDK.

---

## Project Structure

```
code_review_agent/
├── agent.py          # LangGraph workflow (4 nodes)
├── mcp_server.py     # MCP server exposing read_file, write_report, list_reports
├── config.py         # Environment variable loading
├── sample_script.py  # Example file to review
├── reports/          # Generated .md review reports (auto-created)
├── .env.example      # Template for API keys
├── requirements.txt  # Pinned Python dependencies
└── README.md         # This file
```

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone <your-github-repo-url>
cd code_review_agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your API keys

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

```env
LLM_PROVIDER=anthropic          # or "openai" or "gemini"
ANTHROPIC_API_KEY=sk-ant-...    # your key here
```

You only need the key for the provider you choose. The others can stay empty.

### 5. (Optional) Install Ruff for linting

Ruff is included in `requirements.txt` and installed with `pip install -r requirements.txt`. If for any reason it's missing:

```bash
pip install ruff
```

---

## Usage

```bash
python agent.py <path_to_python_file.py>
```

### Example

```bash
python agent.py sample_script.py
```

**Expected terminal output:**

```
============================================================
  Code Review Agent — sample_script.py
============================================================

[lint_node] Reading file: sample_script.py
[lint_node] Lint output:
  sample_script.py:8:1: E401 Multiple imports on one line
  sample_script.py:11:1: S105 Possible hardcoded password...
  ...

[analyze_node] Analysing AST complexity…
[analyze_node] Metrics:
  {
    "total_lines": 58,
    "num_functions": 3,
    "num_async_functions": 0,
    "num_classes": 1,
    ...
  }

[review_node] Calling LLM for code review…
[review_node] Review received ✅

[report_node] Saving report via MCP…
[report_node] Report saved → /path/to/reports/sample_script_20240101_120000.md

============================================================
  ✅  Review complete!
  📄  Report saved to: /path/to/reports/sample_script_20240101_120000.md
============================================================
```

The generated `.md` report will contain:
- A metrics table (lines, functions, classes, nesting depth)
- Full Ruff lint output
- LLM sections: Summary, Issues Found, Suggestions, Complexity Assessment, Overall Quality Score

---

## MCP Server Tools

The MCP server (`mcp_server.py`) exposes three tools to the agent:

| Tool | Arguments | Description |
|------|-----------|-------------|
| `read_file` | `file_path: str` | Reads a `.py` file from disk. Validates existence and extension. Returns source code or an `ERROR:` message. |
| `write_report` | `filename: str`, `content: str` | Saves a Markdown report to `/reports/`. Appends a timestamp to avoid collisions. Returns the absolute saved path. |
| `list_reports` | *(none)* | Returns a JSON array of all saved reports with filename, creation time, and size. |

> **Why MCP?** The agent never touches the file system directly. If you later swap local storage for S3 or a database, only `mcp_server.py` changes — `agent.py` stays untouched. That's the value of the MCP abstraction layer.

---

## Team Contributions

Santiago Cardenas

---

## GitHub Repository

🔗 **https://github.com/<your-username>/code-review-agent**

---

## Academic Integrity Declaration

Portions of this project were developed with AI assistance (Claude by Anthropic). All generated code has been reviewed, understood, and is explainable line-by-line by the submitting student(s).
