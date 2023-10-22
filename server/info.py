"""
Static meta information about the container/process
"""

import os
import platform

PYTHON_VERSION = platform.python_version()

# Environment variables
VERSION = os.getenv("VERSION") or "dev"
CONTAINER_NAME = os.getenv("CONTAINER_NAME") or "faf-python-server"
