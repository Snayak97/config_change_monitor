"""
Main entry point for running the Configuration Change Monitoring Service.
Can be executed directly: python -m src.main or python src/main.py
"""

import sys
import os
import uvicorn

# Ensure the root project directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import get_settings


def run():
    settings = get_settings()
    uvicorn.run(
        "src.api.app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    run()
