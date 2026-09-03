"""Stable installed entry point for the root-owned FogBot helper."""

from __future__ import annotations

from .runtime import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
