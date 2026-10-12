"""Production-style local startup entry point for ChronosMatch."""
from __future__ import annotations

import logging
from importlib import import_module

from .config import load_settings


def main() -> None:
    uvicorn = import_module("uvicorn")
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "src.api:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
