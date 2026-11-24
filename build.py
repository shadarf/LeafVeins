#!/usr/bin/env python3
"""Build script for creating Windows executable using PyInstaller."""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def main():
    """Build the LeafVeins executable."""
    project_root = Path(__file__).parent
    app_dir = project_root / "app"
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    
    # Clean previous builds
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=LeafVeins",
        "--onefile",
        "--windowed",
        "--icon=app/resources/icons/app.ico",
        "--add-data=app/resources;resources",
        "--hidden-import=pypdfium2",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--collect-all=PIL",
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=sqlite3",
        "--hidden-import=json",
        "--hidden-import=pathlib",
        "--hidden-import=datetime",
        "--hidden-import=subprocess",
        "--hidden-import=shutil",
        "--hidden-import=fnmatch",
        "--collect-all=pypdfium2",
        "--collect-all=PyQt6",
        "app/main.py",
    ]
    
    # Run PyInstaller
    print("Building LeafVeins executable...")
    result = subprocess.run(cmd, cwd=project_root)
    
    if result.returncode == 0:
        print(f"\nBuild successful! Executable created in: {dist_dir}")
        print(f"Run: {dist_dir / 'LeafVeins.exe'}")
    else:
        print("\nBuild failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()