"""Install pinned decoder dependencies from the repository root.

Windows uses WSL2; the decoder's Linux toolchain is not installed natively.
"""

import os
import subprocess
import sys
from pathlib import Path

from script import run_in_wsl


ROOT = Path(__file__).resolve().parent


def main():
    if os.name == "nt":
        return run_in_wsl(["bash", "setup.sh"])
    return subprocess.call(["bash", str(ROOT / "setup.sh")], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
