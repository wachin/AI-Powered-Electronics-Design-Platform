#!/usr/bin/env python3
"""
Root-level entry point for the AI-Powered Electronics Design Platform.

This is a thin shim kept for backwards compatibility with existing docs and
scripts (`python main.py -p "..."`). The implementation lives in `src/cli.py` so
that an installed copy also exposes the `ai-electronics-design` console command.
"""

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
