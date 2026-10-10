"""Application resources are independent of the caller's working directory."""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resource_path(name):
    return Path(getattr(sys, '_MEIPASS', PROJECT_ROOT)) / name
