#!/usr/bin/env python3
"""ASAV — Windows antivirus GUI using the KicomAV engine."""

import argparse
import sys


def main() -> int:
    if sys.version_info < (3, 10):
        print("ASAV requires Python 3.10 or newer.")
        return 1
    if sys.version_info >= (3, 14):
        print("ASAV does not support Python 3.14+ yet.")
        print("KicomAV needs yara-python, which has no Windows wheel for 3.14.")
        print("Install Python 3.12, then run: py -3.12 -m pip install -r requirements.txt")
        print("Or run install.bat after: py install 3.12")
        return 1

    parser = argparse.ArgumentParser(description="ASAV antivirus")
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Start hidden in the system tray (used by Windows startup)",
    )
    args = parser.parse_args()

    try:
        from gui.splash import run_startup_splash
    except ImportError as exc:
        print("Missing dependencies. Run: pip install -r requirements.txt")
        print(exc)
        return 1

    preload = run_startup_splash()

    try:
        from gui.app import run_app
    except ImportError as exc:
        print("Missing dependencies. Run: pip install -r requirements.txt")
        print(exc)
        return 1

    run_app(start_hidden=args.tray, preload=preload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
