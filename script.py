"""Start the virtual Basys3 lab from the repository root.

On Windows, use the WSL2 installation of this repository for decoding while
Vivado Hardware Manager runs on Windows.
"""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_in_wsl(command):
    try:
        result = subprocess.run(["wsl.exe", "wslpath", "-a", str(ROOT)],
                                capture_output=True, text=True, check=True)
        linux_root = result.stdout.strip()
        if not linux_root:
            raise RuntimeError("WSL could not resolve the repository path")
        return subprocess.call(["wsl.exe", "--cd", linux_root, *command])
    except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"WSL2 is required for the bitstream decoder: {error}", file=sys.stderr)
        print("Install WSL2 and Ubuntu, then run bash setup.sh in Ubuntu.", file=sys.stderr)
        return 1


def main():
    if os.name == "nt":
        return run_in_wsl(["python3", "script.py", "--no-hw-server", *sys.argv[1:]])
    from scripts.start_local_lab import main as start_local_lab
    return start_local_lab()


if __name__ == "__main__":
    sys.exit(main())
