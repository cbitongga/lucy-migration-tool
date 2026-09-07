"""Absolute-path entry point for VS Code; works regardless of client cwd."""
from modernizer.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
