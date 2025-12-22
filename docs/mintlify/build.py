#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
# SPDX-License-Identifier: MIT
"""Build Mintlify-compatible docs from the shared content files.

This script:
1. Copies content files to the build directory
2. Converts relative links to absolute Mintlify routes
3. Prepares the output for the multirepo action
"""

import re
import shutil
import sys
from pathlib import Path

# Mintlify route prefix for connector framework docs
PREFIX = "/ground-control/robot-integration/connector-framework"

# Pattern to match markdown links: [text](path) or [text](path#anchor)
# Excludes: absolute URLs (http://, https://), absolute paths (/...), and pure anchors (#...)
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((?!https?://|mailto:|/|#)([^)]+)\)")


def convert_link(match: re.Match, file_path: Path, content_root: Path) -> str:
    """Convert a relative link to an absolute Mintlify route."""
    text = match.group(1)
    target = match.group(2)

    # Get the directory of the current file relative to content root
    file_dir = file_path.parent.relative_to(content_root)

    # Resolve the relative path
    if target.startswith("../"):
        # Go up directories
        resolved = (file_dir / target).as_posix()
        # Normalize path (remove ../)
        parts = []
        for part in resolved.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)
        resolved = "/".join(parts)
    else:
        # Same directory or subdirectory
        if str(file_dir) == ".":
            resolved = target
        else:
            resolved = f"{file_dir}/{target}".replace("./", "")

    # Strip .md extension for Mintlify routes
    if resolved.endswith(".md"):
        resolved = resolved[:-3]
    # Also handle .md before anchors (e.g., "file.md#anchor" -> "file#anchor")
    resolved = re.sub(r"\.md(#)", r"\1", resolved)

    # Build absolute Mintlify route
    absolute_path = f"{PREFIX}/{resolved}"

    return f"[{text}]({absolute_path})"


def process_file(src_file: Path, dst_file: Path, content_root: Path) -> int:
    """Process a single file, converting links. Returns count of conversions."""
    content = src_file.read_text(encoding="utf-8")
    count = 0

    def replace_link(match: re.Match) -> str:
        nonlocal count
        count += 1
        return convert_link(match, src_file, content_root)

    new_content = LINK_PATTERN.sub(replace_link, content)

    dst_file.parent.mkdir(parents=True, exist_ok=True)
    dst_file.write_text(new_content, encoding="utf-8")

    return count


def main():
    if len(sys.argv) < 3:
        print("Usage: build.py <content_dir> <output_dir>", file=sys.stderr)
        sys.exit(1)

    content_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not content_dir.is_dir():
        print(f"Error: {content_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Clean output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    total_links = 0
    total_files = 0

    # Process all markdown files
    for src_file in content_dir.rglob("*.md"):
        rel_path = src_file.relative_to(content_dir)
        dst_file = output_dir / rel_path

        links = process_file(src_file, dst_file, content_dir)
        if links > 0:
            print(f"  {rel_path}: {links} links converted")
        total_links += links
        total_files += 1

    # Copy non-markdown files (images, etc.) but skip _static/
    # The _static/ folder contains branding assets that the main docs repo
    # already has - we don't need to copy them
    for src_file in content_dir.rglob("*"):
        if src_file.is_file() and src_file.suffix != ".md":
            rel_path = src_file.relative_to(content_dir)
            if rel_path.parts[0] == "_static":
                continue
            dst_file = output_dir / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)

    # Copy navigation.json (Mintlify-specific, lives in mintlify/ folder)
    script_dir = Path(__file__).parent
    nav_src = script_dir / "navigation.json"
    if nav_src.exists():
        shutil.copy2(nav_src, output_dir / "navigation.json")

    print(f"\nTotal: {total_files} files, {total_links} links converted")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
