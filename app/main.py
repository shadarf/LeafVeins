#!/usr/bin/env python3
"""
LeafVeins - Standalone LaTeX Editor for Windows
A native Windows application for LaTeX document writing and typesetting.
"""

import sys
import os

# Add app directory to path
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from core.app import main

if __name__ == "__main__":
    sys.exit(main())