#!/usr/bin/env python3
"""Build wheel file for DataSpear package."""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd: list[str], cwd: str = None) -> bool:
    """Run a command and return success status."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        if e.stderr:
            print(e.stderr)
        return False


def main():
    """Build the wheel file."""
    script_dir = Path(__file__).parent.absolute()
    project_root = script_dir

    print("=" * 60)
    print("Building DataSpear Wheel")
    print("=" * 60)

    # Check if build module is available
    print("\n[1/4] Checking build dependencies...")
    if not run_command([sys.executable, "-m", "pip", "show", "build", "wheel"]):
        print("Installing build tools...")
        if not run_command([sys.executable, "-m", "pip", "install", "build", "wheel", "-q"]):
            print("Failed to install build tools")
            return 1

    # Clean previous builds. The build/ directory must be removed too: a
    # stale build/lib tree is reused by setuptools and can leak outdated
    # paths (e.g. a renamed "Utils" vs "utils" package) into the wheel.
    print("\n[2/4] Cleaning previous builds...")
    import shutil

    dist_dir = project_root / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print("Removed old dist/ directory")

    build_dir = project_root / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("Removed old build/ directory")

    for egg_info in project_root.glob("src/*.egg-info"):
        shutil.rmtree(egg_info)
        print(f"Removed old {egg_info.name} directory")

    # Build wheel
    print("\n[3/4] Building wheel...")
    if not run_command([sys.executable, "-m", "build", "--wheel", "--no-isolation"], cwd=str(project_root)):
        print("\nAlternative: Trying with pip wheel...")
        if not run_command([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", "dist"], cwd=str(project_root)):
            print("Failed to build wheel")
            return 1

    # Show results
    print("\n[4/4] Build results:")
    print("-" * 40)
    if dist_dir.exists():
        wheel_files = list(dist_dir.glob("*.whl"))
        if wheel_files:
            print(f"✅ Successfully built {len(wheel_files)} wheel file(s):")
            for wf in wheel_files:
                size = wf.stat().st_size / 1024  # KB
                print(f"   • {wf.name} ({size:.1f} KB)")
                print(f"     Path: {wf.absolute()}")
        else:
            print("❌ No wheel files found in dist/")
            return 1
    else:
        print("❌ dist/ directory not created")
        return 1

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
