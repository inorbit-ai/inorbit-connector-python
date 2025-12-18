#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
# SPDX-License-Identifier: MIT
"""Fix absolute Mintlify-style links in Sphinx HTML output.

MyST converts absolute paths like /ground-control/robot-integration/connector-framework/X
to anchors like #/ground-control/robot-integration/connector-framework/X.

This script rewrites them to proper relative paths based on the file's location.
"""

import re
import sys
from pathlib import Path

PREFIX = "/ground-control/robot-integration/connector-framework/"
ANCHOR_PATTERN = re.compile(r'href="#' + re.escape(PREFIX) + r'([^"]*)"')


def compute_relative_path(from_file: Path, to_path: str, html_root: Path) -> str:
    """Compute relative path from one file to another."""
    # Get the directory containing the source file, relative to html_root
    from_dir = from_file.parent.relative_to(html_root)
    
    # Compute how many levels up we need to go
    depth = len(from_dir.parts)
    prefix = "../" * depth
    
    # Build the relative path
    # Handle fragment anchors (e.g., "specification/connector#some-anchor")
    if "#" in to_path:
        path_part, fragment = to_path.split("#", 1)
        return f'{prefix}{path_part}.html#{fragment}'
    else:
        return f"{prefix}{to_path}.html"


def fix_file(html_file: Path, html_root: Path) -> int:
    """Fix links in a single HTML file. Returns count of fixes."""
    content = html_file.read_text(encoding="utf-8")
    fixes = 0
    
    def replace_link(match: re.Match) -> str:
        nonlocal fixes
        target = match.group(1)
        relative = compute_relative_path(html_file, target, html_root)
        fixes += 1
        return f'href="{relative}"'
    
    new_content = ANCHOR_PATTERN.sub(replace_link, content)
    
    if fixes > 0:
        html_file.write_text(new_content, encoding="utf-8")
    
    return fixes


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_links.py <html_directory>", file=sys.stderr)
        sys.exit(1)
    
    html_root = Path(sys.argv[1])
    if not html_root.is_dir():
        print(f"Error: {html_root} is not a directory", file=sys.stderr)
        sys.exit(1)
    
    total_fixes = 0
    for html_file in html_root.rglob("*.html"):
        fixes = fix_file(html_file, html_root)
        if fixes > 0:
            print(f"  Fixed {fixes} links in {html_file.relative_to(html_root)}")
            total_fixes += fixes
    
    print(f"Total: {total_fixes} links fixed")


if __name__ == "__main__":
    main()

