from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # Do not override variables that are already set by the caller or shell.
    load_dotenv(override=False)
