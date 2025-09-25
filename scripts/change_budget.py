"""Fail CI if the staged diff exceeds repository-wide change budgets."""

from __future__ import annotations

import subprocess  # nosec B404
import sys


MAX_FILES = 50
MAX_LOC = 4000


def main() -> int:
    cmd = ["git", "diff", "--cached"]
    diff = subprocess.check_output(cmd, text=True)  # nosec
    files: set[str] = set()
    loc = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            _, _, rest = line.partition(" ")
            candidate = rest.strip().lstrip("ab/")
            if candidate and candidate != "/dev/null":
                files.add(candidate)
        elif line.startswith("+") or line.startswith("-"):
            if not (line.startswith("+++") or line.startswith("---")):
                loc += 1

    if len(files) > MAX_FILES or loc > MAX_LOC:
        print(f"Budget exceeded: files={len(files)} loc={loc}")
        return 1

    print(f"Budget OK: files={len(files)} loc={loc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
