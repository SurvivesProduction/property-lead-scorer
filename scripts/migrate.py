#!/usr/bin/env python
"""CLI entry point: run extscorer's SQL migrations against DATABASE_URL.

Usage:
    python scripts/migrate.py
"""
from __future__ import annotations

import sys

from extscorer.migrate import main

if __name__ == "__main__":
    sys.exit(main())
