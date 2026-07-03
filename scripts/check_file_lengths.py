from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_MAX_LINES = 500
DOC_DIRS = {"docs"}
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
SKIP_FILES = {
    ".coverage",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}


def should_skip(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if path.name in SKIP_FILES:
        return True
    if any(part in SKIP_DIRS for part in relative.parts):
        return True
    if relative.parts and relative.parts[0] in DOC_DIRS:
        return True
    return path.suffix.lower() in DOC_SUFFIXES


def count_lines(path: Path) -> int:
    with path.open("rb") as file:
        return sum(1 for _ in file)


def iter_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and not should_skip(path, root)]


def oversized_files(root: Path, max_lines: int) -> list[tuple[Path, int]]:
    oversized = []
    for path in iter_files(root):
        line_count = count_lines(path)
        if line_count > max_lines:
            oversized.append((path, line_count))
    return oversized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check non-documentation files stay under the configured line limit.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help="Maximum allowed lines per non-documentation file.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    oversized = oversized_files(root, args.max_lines)
    if not oversized:
        return 0

    _ = sys.stdout.write(f"Files over {args.max_lines} lines:\n")
    for path, line_count in oversized:
        _ = sys.stdout.write(f"- {path.relative_to(root)}: {line_count}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
