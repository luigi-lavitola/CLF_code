"""
Common setup for the hardware-free unit tests.

- the repository root goes on sys.path (the code imports `lib.*`)
- modules not needed by the logic under test are replaced by stubs when missing
- several modules create `TimedRotatingFileHandler('logs/...')` at import time:
  the handler is replaced by one that writes nothing, so tests leave no log files
  (this must happen before test collection imports `lib.*`)
"""

import logging
import logging.handlers
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

try:
    import gps  # noqa: F401
except ImportError:
    stub = types.ModuleType("gps")
    stub.WATCH_ENABLE = 1
    stub.WATCH_NEWSTYLE = 2
    stub.gps = lambda *args, **kwargs: None
    sys.modules["gps"] = stub


class _NoFileHandler(logging.NullHandler):
    def __init__(self, *args, **kwargs):
        super().__init__()


logging.handlers.TimedRotatingFileHandler = _NoFileHandler
