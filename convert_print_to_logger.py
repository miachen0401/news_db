"""
convert_print_to_logger.py

Usage:
    python3 convert_print_to_logger.py <path>

This script:
  - Recursively finds all .py files under <path>
  - Replaces print(...) with logger.info(...)
  - Adds logger setup at top if missing
  - Creates .bak backup for each file
"""

import os
import sys
import re

LOGGER_SETUP = """import logging
logger = logging.getLogger(__name__)
"""

PRINT_REGEX = re.compile(r'(^\s*)print\((.*?)\)\s*$', re.MULTILINE)

def add_logger_setup(content):
    """Insert logger setup after imports if not present."""
    if "logger = logging.getLogger" in content:
        return content  # Already exists

    lines = content.split("\n")
    insert_idx = 0

    # Find where to inject logger setup
    for i, line in enumerate(lines):
        if line.startswith("import") or line.startswith("from"):
            insert_idx = i + 1

    lines.insert(insert_idx, LOGGER_SETUP)
    return "\n".join(lines)


def replace_print_with_logger(content):
    """Replace print(...) with logger.info(...) while preserving indentation."""

    def repl(match):
        indent = match.group(1)
        inside = match.group(2).strip()
        
        if inside == "" or inside.strip() == "":
            inside = '""'
        # Heuristic:
        # - If print starts with STEP / banner / emoji → keep as info
        # - Otherwise → debug (detailed stats)
        if inside.startswith(("'", '"')) and (
            "STEP" in inside or "📊" in inside or "🔍" in inside
        ):
            level = "info"
        else:
            level = "debug"

        return f"{indent}logger.{level}({inside})"

    return PRINT_REGEX.sub(repl, content)


def process_file(path):
    """Process a single .py file."""
    with open(path, "r", encoding="utf-8") as f:
        orig = f.read()

    updated = add_logger_setup(orig)
    updated = replace_print_with_logger(updated)

    if updated == orig:
        return False  # no changes

    # Backup
    backup = path + ".bak"
    with open(backup, "w", encoding="utf-8") as f:
        f.write(orig)

    # Write updated
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"[UPDATED] {path} (backup: {backup})")
    return True


def walk_path(target):
    if os.path.isfile(target) and target.endswith(".py"):
        process_file(target)
        return

    for root, _, files in os.walk(target):
        for f in files:
            if f.endswith(".py"):
                process_file(os.path.join(root, f))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 convert_print_to_logger.py <path>")
        sys.exit(1)

    walk_path(sys.argv[1])
    print("Done.")
    