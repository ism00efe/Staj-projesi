"""Launch the HTTP API + web UI (convenience wrapper; no editable install needed).

Usage:  python scripts/run_app.py   ->  http://127.0.0.1:7860
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from payment_assistant.api import main

if __name__ == "__main__":
    main()
