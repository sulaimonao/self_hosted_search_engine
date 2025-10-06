"""Pack the backend Flask server into a single binary via PyInstaller."""

from __future__ import annotations

import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "backend" / "app" / "__main__.py"
OUTPUT_DIR = ROOT / "dist-backend"


def main() -> None:
    if not ENTRYPOINT.exists():
        raise SystemExit(f"Backend entrypoint not found: {ENTRYPOINT}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "backend-server",
        "--distpath",
        str(OUTPUT_DIR),
        str(ENTRYPOINT),
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("Built:", OUTPUT_DIR / "backend-server")


if __name__ == "__main__":
    main()
