#!/usr/bin/env python3
"""
Convert a Python (.py) file to a Jupyter Notebook (.ipynb).

Splits the file into cells using these conventions:
  - Module docstrings and block comments (# %% or # ---) become markdown cells
  - Consecutive comment lines (# ...) at the start of a section become markdown cells
  - Everything else becomes code cells
  - "# %%" or "# ---" markers force a new cell boundary

Usage:
    python py2notebook.py script.py                  # Creates script.ipynb
    python py2notebook.py script.py -o output.ipynb  # Custom output path
    python py2notebook.py script.py --no-markers     # Don't require markers, split on functions/classes too
"""

import argparse
import json
import re
import sys
from pathlib import Path


NBFORMAT_VERSION = 4
NBFORMAT_MINOR = 5


def make_notebook(cells: list[dict]) -> dict:
    """Build a notebook dict in nbformat v4 schema."""
    return {
        "nbformat": NBFORMAT_VERSION,
        "nbformat_minor": NBFORMAT_MINOR,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12.0",
            },
        },
        "cells": cells,
    }


def make_cell(cell_type: str, source: list[str]) -> dict:
    """Create a single notebook cell with cleaned-up newlines."""
    source = _trim_blank_lines(source)
    if not source:
        return None
    if cell_type == "markdown":
        source = _fix_markdown_newlines(source)
    # Ensure the last line ends with a newline
    if source and not source[-1].endswith("\n"):
        source[-1] += "\n"
    return {
        "cell_type": cell_type,
        "metadata": {},
        "source": source,
        **({"outputs": [], "execution_count": None} if cell_type == "code" else {}),
    }


def _trim_blank_lines(lines: list[str]) -> list[str]:
    """Strip leading and trailing blank lines, collapse 3+ consecutive blanks to 2."""
    # Strip leading blank lines
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    # Strip trailing blank lines
    while lines and lines[-1].strip() == "":
        lines = lines[:-1]
    # Collapse runs of 3+ blank lines down to 2 (one visual gap)
    result = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)
    return result


def _fix_markdown_newlines(lines: list[str]) -> list[str]:
    """Fix markdown line breaks: wrap indented blocks in code fences,
    and add two trailing spaces on non-blank lines for <br> line breaks."""
    result = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        content = line.rstrip("\n")

        # Detect start of an indented block (4+ spaces or tab)
        if content.startswith("    ") or content.startswith("\t"):
            # Collect the full indented block
            result.append("```\n")
            while i < n:
                ln = lines[i].rstrip("\n")
                if ln.startswith("    ") or ln.startswith("\t") or ln.strip() == "":
                    # Strip exactly 4 leading spaces for the code block
                    if ln.startswith("    "):
                        result.append(ln[4:] + "\n")
                    elif ln.startswith("\t"):
                        result.append(ln[1:] + "\n")
                    else:
                        # Blank line inside indented block — check if block continues
                        if i + 1 < n and (lines[i + 1].startswith("    ") or lines[i + 1].startswith("\t")):
                            result.append("\n")
                        else:
                            break
                    i += 1
                else:
                    break
            # Trim trailing blanks inside code fence
            while result and result[-1].strip() == "" and result[-2] != "```\n":
                result.pop()
            result.append("```\n")
            continue

        # For non-indented, non-blank lines followed by another non-blank line,
        # add two trailing spaces to force a markdown <br>
        if content and i + 1 < n and lines[i + 1].strip() != "":
            result.append(content + "  \n")
        else:
            result.append(line)
        i += 1

    return result


def is_cell_marker(line: str) -> bool:
    """Check if a line is an explicit cell boundary marker."""
    stripped = line.strip()
    return stripped in ("# %%", "# ---", "# <codecell>", "# <markdowncell>") or \
        stripped.startswith("# %%") or stripped.startswith("# ---")


def is_markdown_marker(line: str) -> bool:
    """Check if this marker explicitly starts a markdown cell."""
    stripped = line.strip()
    return stripped == "# <markdowncell>" or stripped.startswith("# %% [markdown]")


def strip_comment_prefix(lines: list[str]) -> list[str]:
    """Strip '# ' prefix from comment lines to produce markdown text."""
    result = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("# "):
            result.append(stripped[2:] + "\n")
        elif stripped == "#":
            result.append("\n")
        else:
            result.append(stripped + "\n")
    return result


def extract_docstring(lines: list[str], start: int) -> tuple[list[str], int]:
    """Extract a triple-quoted docstring starting at `start`. Returns (content_lines, end_index)."""
    first = lines[start].strip()
    for quote in ('"""', "'''"):
        if first.startswith(quote):
            # Check single-line docstring
            rest = first[3:]
            if quote in rest:
                content = rest[:rest.index(quote)]
                return [content + "\n"], start + 1

            # Multi-line docstring
            content = [rest + "\n"] if rest else []
            i = start + 1
            while i < len(lines):
                line = lines[i]
                if quote in line:
                    before = line[:line.index(quote)].strip()
                    if before:
                        content.append(before + "\n")
                    return content, i + 1
                content.append(line)
                i += 1
            return content, i
    return [], start


def parse_py_to_cells(source: str, auto_split: bool = True) -> list[dict]:
    """Parse Python source into notebook cells."""
    lines = source.splitlines(keepends=True)
    # Ensure last line has newline
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    cells = []
    i = 0
    n = len(lines)

    # Handle shebang line — skip it
    if lines and lines[0].startswith("#!"):
        i = 1

    # Handle module-level docstring as first markdown cell
    while i < n and lines[i].strip() == "":
        i += 1
    if i < n and (lines[i].strip().startswith('"""') or lines[i].strip().startswith("'''")):
        doc_lines, i = extract_docstring(lines, i)
        if doc_lines:
            cell = make_cell("markdown", doc_lines)
            if cell:
                cells.append(cell)

    # Process remaining lines
    buf = []        # current buffer of lines
    buf_type = None # "code" or "markdown"

    def flush():
        nonlocal buf, buf_type
        if not buf:
            return
        cell = make_cell(buf_type, buf)
        if cell is not None:
            cells.append(cell)
        buf = []
        buf_type = None

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Explicit cell markers
        if is_cell_marker(stripped):
            flush()
            marker_text = stripped.lstrip("# ").lstrip("%").lstrip("-").strip()
            # If marker has a title like "# %% My Section", make it a markdown heading
            if is_markdown_marker(stripped):
                buf_type = "markdown"
            elif marker_text and not marker_text.startswith("["):
                cell = make_cell("markdown", [f"## {marker_text}\n"])
                if cell:
                    cells.append(cell)
                i += 1
                continue
            i += 1
            continue

        # Block of consecutive comment lines → markdown cell
        if stripped.startswith("#") and not stripped.startswith("#!"):
            comment_lines = []
            j = i
            while j < n and (lines[j].strip().startswith("#") or lines[j].strip() == ""):
                if lines[j].strip() == "" and (j + 1 >= n or not lines[j + 1].strip().startswith("#")):
                    break
                comment_lines.append(lines[j])
                j += 1

            if len(comment_lines) >= 2 or (len(comment_lines) == 1 and buf_type != "code"):
                flush()
                md_lines = strip_comment_prefix(comment_lines)
                cell = make_cell("markdown", md_lines)
                if cell:
                    cells.append(cell)
                i = j
                continue

        # Auto-split on top-level def/class/if __name__ if enabled
        if auto_split and buf and stripped and \
                (stripped.startswith("def ") or stripped.startswith("class ") or
                 stripped.startswith("async def ") or
                 stripped.startswith("if __name__")):
            # Only split if previous buffer has content
            if buf_type == "code" and any(l.strip() for l in buf):
                flush()

        # Code line
        if buf_type is None:
            buf_type = "code"
        if buf_type == "markdown":
            flush()
            buf_type = "code"
        buf.append(line)
        i += 1

    flush()
    return cells


def convert_file(input_path: str, output_path: str = None, auto_split: bool = True):
    """Convert a .py file to .ipynb."""
    src = Path(input_path)
    if not src.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    source = src.read_text(encoding="utf-8")
    cells = parse_py_to_cells(source, auto_split=auto_split)

    if not cells:
        print("Warning: no cells generated", file=sys.stderr)

    notebook = make_notebook(cells)

    if output_path is None:
        output_path = str(src.with_suffix(".ipynb"))

    Path(output_path).write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    print(f"Created {output_path} ({len(cells)} cells)")


def main():
    parser = argparse.ArgumentParser(description="Convert a Python file to a Jupyter Notebook.")
    parser.add_argument("input", help="Input .py file")
    parser.add_argument("-o", "--output", help="Output .ipynb file (default: same name with .ipynb)")
    parser.add_argument("--no-split", action="store_true",
                        help="Don't auto-split on def/class boundaries")
    args = parser.parse_args()
    convert_file(args.input, args.output, auto_split=not args.no_split)


if __name__ == "__main__":
    main()
