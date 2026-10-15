#!/usr/bin/env python3
"""The Compact Memory showcase: python3 server.py (settings in cm/config.py, from the environment)."""

import signal
import sys

from cm import web

if __name__ == "__main__":
    # as process 1 of a container, Python ignores SIGTERM: docker stop and a shutdown of the VM would wait for SIGKILL
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    web.main()
