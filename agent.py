"""
agent.py — Code Review Agent using LangGraph + MCP.

LangGraph workflow (4 nodes in sequence):
  lint_node     → Read the Python file via MCP, run Ruff linter, collect issues.
  analyze_node  → Use Python's ast module to compute complexity metrics.
  review_node   → Send code + lint + metrics to the LLM; get a structured review.
  report_node   → Save the review as a .md report via MCP; return the file path.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import config

# ── LLM factory ──────────────────────────────────────────────────────────────

def _build_llm():
    """Instantiate the configured LLM client (OpenAI / Anthropic / Gemini)."""
    provider = config.LLM_PROVIDER.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=config.OPENAI_MODEL, api_key=config.OPENAI_API_KEY)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config.ANTHROPIC_MODEL, api_key=config.ANTHROPIC_API_KEY)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=config.GEMINI_MODEL, google_api_key=config.GEMINI_API_KEY)

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Choose 'openai', 'anthropic', or 'gemini'.")


llm = _build_llm()

# ── State definition ──────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """Shared state that flows through every LangGraph node."""
    file_path: str                   # (input)  Path provided by the user
    source_code: str                 # lint_node output
    lint_results: str                # lint_node output
    complexity_metrics: dict         # analyze_node output
    review: str                      # review_node output
    report_path: str                 # report_node output
    error: str                       # Non-empty if a node encountered a fatal error


# ── MCP helper ────────────────────────────────────────────────────────────────

async def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Launch the MCP server as a subprocess and call a single tool.

    Opens a fresh stdio session, calls `tool_name` with `arguments`, then
    closes the session.  Returns the tool's text output as a string.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[config.MCP_SERVER_SCRIPT],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            # result.content is a list of TextContent / BlobContent objects
            parts = [c.text for c in result.content if hasattr(c, "text")]
            return "\n".join(parts)


# ── Node 1: lint_node ─────────────────────────────────────────────────────────

async def lint_node(state: AgentState) -> AgentState:
    """
    Read the Python file via MCP, then run Ruff to collect lint issues.

    Updates state with:
      - source_code:  raw Python source text
      - lint_results: formatted Ruff output (or a message if no issues found)
      - error:        set if reading fails
    """
    print(f"\n[lint_node] Reading file: {state['file_path']}")

    # 1. Read source via MCP
    source = await _call_mcp_tool("read_file", {"file_path": state["file_path"]})

    if source.startswith("ERROR:"):
        return {**state, "error": source}

    state = {**state, "source_code": source}

    # 2. Run Ruff linter via subprocess
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", state["file_path"], "--output-format=text"],
            capture_output=True,
            text=True,
        )
        lint_output = proc.stdout.strip() or proc.stderr.strip()
        lint_results = lint_output if lint_output else "No lint issues found. ✅"
    except FileNotFoundError:
        lint_results = "WARNING: Ruff not installed. Run `pip install ruff` to enable linting."
    except Exception as exc:
        lint_results = f"WARNING: Ruff failed: {exc}"

    print(f"[lint_node] Lint output:\n{textwrap.indent(lint_results, '  ')}")
    return {**state, "lint_results": lint_results}


# ── Node 2: analyze_node ──────────────────────────────────────────────────────

def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    """Recursively compute the maximum nesting depth in an AST."""
    nesting_nodes = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
    if isinstance(node, nesting_nodes):
        depth += 1
    return max(
        [depth] + [_max_nesting(child, depth) for child in ast.iter_child_nodes(node)]
    )


async def analyze_node(state: AgentState) -> AgentState:
    """
    Use Python's built-in `ast` module to compute complexity metrics.

    Counts: total lines, functions, classes, async functions, branches,
    and maximum nesting depth.

    Updates state with:
      - complexity_metrics: dict of computed metrics
      - error:              set if AST parsing fails
    """
    if state.get("error"):
        return state  # propagate earlier error

    print("\n[analyze_node] Analysing AST complexity…")

    try:
        tree = ast.parse(state["source_code"])
    except SyntaxError as exc:
        return {**state, "error": f"ERROR: SyntaxError while parsing file: {exc}"}

    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    async_funcs = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    branches = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With))
    ]

    metrics: dict = {
        "total_lines": len(state["source_code"].splitlines()),
        "num_functions": len(functions),
        "num_async_functions": len(async_funcs),
        "num_classes": len(classes),
        "num_branches": len(branches),
        "max_nesting_depth": _max_nesting(tree),
        "function_names": [n.name for n in functions + async_funcs],
        "class_names": [n.name for n in classes],
    }

    print(f"[analyze_node] Metrics: {json.dumps(metrics, indent=2)}")
    return {**state, "complexity_metrics": metrics}


# ── Node 3: review_node ───────────────────────────────────────────────────────

_REVIEW_SYSTEM = """\
You are an expert Python code reviewer. Given source code, lint results, and \
complexity metrics, produce a detailed, constructive code review in Markdown.

Your review MUST contain these sections (use the exact headings):
## Summary
## Issues Found
## Suggestions for Improvement
## Complexity Assessment
## Overall Quality Score  (integer 1–10, with brief justification)

Be specific, cite line numbers when relevant, and always be constructive.
"""


async def review_node(state: AgentState) -> AgentState:
    """
    Send source code + lint results + complexity metrics to the LLM.

    Constructs a prompt and calls the configured LLM to produce a structured
    Markdown code review.

    Updates state with:
      - review:  full Markdown review text
      - error:   set if the LLM call fails
    """
    if state.get("error"):
        return state

    print("\n[review_node] Calling LLM for code review…")

    metrics = state["complexity_metrics"]
    user_prompt = f"""\
## File: `{state['file_path']}`

### Source Code
```python
{state['source_code']}
```

### Lint Results (Ruff)
```
{state['lint_results']}
```

### Complexity Metrics
- Total lines: {metrics.get('total_lines')}
- Functions: {metrics.get('num_functions')} synchronous, {metrics.get('num_async_functions')} async
- Classes: {metrics.get('num_classes')}
- Branches (if/for/while/try/with): {metrics.get('num_branches')}
- Max nesting depth: {metrics.get('max_nesting_depth')}
- Function names: {', '.join(metrics.get('function_names', [])) or 'none'}
- Class names: {', '.join(metrics.get('class_names', [])) or 'none'}

Please write a thorough code review following the required section structure.
"""

    try:
        messages = [
            SystemMessage(content=_REVIEW_SYSTEM),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.ainvoke(messages)
        review_text: str = response.content
    except Exception as exc:
        return {**state, "error": f"ERROR: LLM call failed: {exc}"}

    print("[review_node] Review received ✅")
    return {**state, "review": review_text}


# ── Node 4: report_node ───────────────────────────────────────────────────────

async def report_node(state: AgentState) -> AgentState:
    """
    Save the complete review as a Markdown file via MCP.

    Constructs a full report document (metadata header + review body) and
    sends it to the MCP server's `write_report` tool.

    Updates state with:
      - report_path:  absolute path to the saved .md file
      - error:        set if the MCP write call fails
    """
    if state.get("error"):
        return state

    print("\n[report_node] Saving report via MCP…")

    from pathlib import Path
    import datetime

    file_stem = Path(state["file_path"]).stem
    metrics = state["complexity_metrics"]

    report_content = f"""\
# Code Review Report: `{Path(state['file_path']).name}`

**Reviewed on:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**File:** `{state['file_path']}`

---

## Complexity Metrics

| Metric | Value |
|--------|-------|
| Total Lines | {metrics.get('total_lines')} |
| Functions (sync) | {metrics.get('num_functions')} |
| Functions (async) | {metrics.get('num_async_functions')} |
| Classes | {metrics.get('num_classes')} |
| Branches | {metrics.get('num_branches')} |
| Max Nesting Depth | {metrics.get('max_nesting_depth')} |

---

## Lint Results

```
{state['lint_results']}
```

---

{state['review']}
"""

    saved_path = await _call_mcp_tool(
        "write_report",
        {"filename": f"{file_stem}_review.md", "content": report_content},
    )

    if saved_path.startswith("ERROR:"):
        return {**state, "error": saved_path}

    print(f"[report_node] Report saved → {saved_path}")
    return {**state, "report_path": saved_path}


# ── Build LangGraph ───────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Assemble and compile the 4-node LangGraph workflow."""
    graph = StateGraph(AgentState)

    graph.add_node("lint_node", lint_node)
    graph.add_node("analyze_node", analyze_node)
    graph.add_node("review_node", review_node)
    graph.add_node("report_node", report_node)

    graph.set_entry_point("lint_node")
    graph.add_edge("lint_node", "analyze_node")
    graph.add_edge("analyze_node", "review_node")
    graph.add_edge("review_node", "report_node")
    graph.add_edge("report_node", END)

    return graph.compile()


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_agent(file_path: str) -> None:
    """Run the full code-review pipeline for a given Python file."""
    graph = build_graph()

    initial_state: AgentState = {
        "file_path": file_path,
        "source_code": "",
        "lint_results": "",
        "complexity_metrics": {},
        "review": "",
        "report_path": "",
        "error": "",
    }

    print(f"\n{'='*60}")
    print(f"  Code Review Agent — {file_path}")
    print(f"{'='*60}")

    final_state = await graph.ainvoke(initial_state)

    print(f"\n{'='*60}")
    if final_state.get("error"):
        print(f"  ❌  Agent failed: {final_state['error']}")
    else:
        print(f"  ✅  Review complete!")
        print(f"  📄  Report saved to: {final_state['report_path']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python agent.py <path_to_python_file.py>")
        sys.exit(1)

    asyncio.run(run_agent(sys.argv[1]))
