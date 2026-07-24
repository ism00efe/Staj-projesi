"""Launch the Gradio app (convenience wrapper that works without an editable install).

Usage:  python scripts/run_app.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from payment_assistant.ui.app import main

if __name__ == "__main__":
    main()
