"""Math Question System - PDF ingestion.

Checks the interpreter version up front. Without this, an old Python fails deep
inside a module with a message that says nothing about the real cause - a type
annotation raising "unsupported operand type(s) for |".
"""

import sys

MINIMUM_PYTHON = (3, 9)

if sys.version_info < MINIMUM_PYTHON:
    _needed = ".".join(str(n) for n in MINIMUM_PYTHON)
    _found = ".".join(str(n) for n in sys.version_info[:3])
    raise RuntimeError(
        f"Math Question System needs Python {_needed} or newer, but this is "
        f"Python {_found} ({sys.executable}).\n"
        "On macOS the system python3 is usually older than one you installed "
        "yourself. Try a newer interpreter directly:\n"
        "    python3.11 -m venv .venv && source .venv/bin/activate\n"
        "    pip install -r requirements.txt"
    )
