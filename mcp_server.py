"""
mcp_server.py — MCP (Model Context Protocol) server for the Code Review Agent.

Exposes three standardized tools to the agent:
  - read_file:     Read the contents of a Python source file.
  - write_report:  Save a markdown review report to the /reports directory.
  - list_reports:  List all previously generated review reports.

Run this as a subprocess; it communicates over stdio (stdin/stdout).
"""

import os
import json
import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ── Server init ───────────────────────────────────────────────────────────────
mcp = FastMCP("code-review-agent")

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── Tool: read_file ───────────────────────────────────────────────────────────
@mcp.tool()
def read_file(file_path: str) -> str:
    """
    Read the contents of a Python source file from disk.

    Validates that the file exists and has a .py extension before reading.
    Returns the raw source code as a string, or an error message prefixed
    with 'ERROR:' if validation fails.

    Args:
        file_path: Absolute or relative path to the .py file to read.

    Returns:
        The full source code of the file as a plain string, or an error message.
    """
    path = Path(file_path)

    if not path.exists():
        return f"ERROR: File not found: {file_path}"

    if path.suffix.lower() != ".py":
        return f"ERROR: Not a Python file (expected .py, got {path.suffix}): {file_path}"

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"ERROR: Could not read file: {exc}"


# ── Tool: write_report ────────────────────────────────────────────────────────
@mcp.tool()
def write_report(filename: str, content: str) -> str:
    """
    Save a markdown code-review report to the /reports directory.

    The filename should end with '.md'. A timestamp is appended to the
    filename stem to avoid collisions (e.g. 'my_script_20240101_120000.md').
    Returns the absolute path where the report was saved, or an error message
    prefixed with 'ERROR:'.

    Args:
        filename: Desired filename for the report (e.g. 'my_script_review.md').
        content:  Full markdown content of the review report.

    Returns:
        Absolute path to the saved report file, or an error message.
    """
    stem = Path(filename).stem
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{stem}_{timestamp}.md"
    report_path = REPORTS_DIR / safe_name

    try:
        report_path.write_text(content, encoding="utf-8")
        return str(report_path.resolve())
    except OSError as exc:
        return f"ERROR: Could not write report: {exc}"


# ── Tool: list_reports ────────────────────────────────────────────────────────
@mcp.tool()
def list_reports() -> str:
    """
    List all previously generated code-review reports in the /reports directory.

    Returns a JSON-encoded list of objects, each containing:
      - filename:  The report file name.
      - created:   ISO-8601 creation timestamp of the file.
      - size_kb:   File size in kilobytes (rounded to 2 decimal places).

    Returns an empty JSON array '[]' when no reports exist yet.
    """
    reports = []
    for report_file in sorted(REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = report_file.stat()
        reports.append({
            "filename": report_file.name,
            "created": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_kb": round(stat.st_size / 1024, 2),
        })
    return json.dumps(reports, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
