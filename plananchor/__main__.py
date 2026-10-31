"""Allow ``python -m plananchor`` to behave like the ``plananchor`` binary."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
