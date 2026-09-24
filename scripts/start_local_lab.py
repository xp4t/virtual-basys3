"""Start the virtual Basys3, board page, and hw_server from any directory.

Vivado remains responsible for selecting and programming the bitstream. The
local analyzer uses supported reconstructed fabric and does not need an LTX.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def wait_for_port(process, port):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited ({process.returncode}) while opening port {port}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Service did not open port {port}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xvc-port", type=int, default=2542)
    parser.add_argument("--board-port", type=int, default=8080)
    parser.add_argument("--hw-port", type=int, default=3121)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-hw-server", action="store_true",
                        help="use an existing hw_server, such as one started by Windows Vivado")
    parser.add_argument("--vivado-root", type=Path,
                        default=os.environ.get("XILINX_VIVADO"))
    args = parser.parse_args()
    if os.name == "nt":
        parser.error("Run the root script.py on Windows so the decoder starts in WSL2")
    python = ROOT / ".venv/bin/python"
    if not python.is_file():
        python = Path(sys.executable)
    hw_server = None
    if not args.no_hw_server:
        if args.vivado_root:
            hw_server = args.vivado_root / "bin/hw_server"
        elif shutil.which("hw_server"):
            hw_server = Path(shutil.which("hw_server"))
        else:
            hw_server = Path.home() / "Xilinx/2025.1/Vivado/bin/hw_server"
        if not hw_server.is_file():
            if os.environ.get("WSL_DISTRO_NAME") and not args.vivado_root:
                args.no_hw_server = True
                print("WSL detected without Linux hw_server; using Windows Vivado's hw_server.", flush=True)
            else:
                parser.error(f"hw_server not found: {hw_server}; use --vivado-root or --no-hw-server")
    ports = (args.xvc_port, args.board_port) if args.no_hw_server else (
        args.xvc_port, args.board_port, args.hw_port)
    if len(set(ports)) != len(ports):
        parser.error("XVC, board, and hardware-server ports must differ")
    for port in ports:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    processes = []

    def start(command):
        process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
        processes.append(process)
        return process

    try:
        xvc = start([str(python), "xvc-server/server.py", "--simulate",
                     "--host", args.host, "--port", str(args.xvc_port),
                     "--board-port", str(args.board_port)])
        wait_for_port(xvc, args.xvc_port)
        wait_for_port(xvc, args.board_port)
        if not args.no_hw_server:
            hardware = start([str(hw_server), "-s", f"tcp::{args.hw_port}",
                              "-e", "set xvc-timeout 600"])
            wait_for_port(hardware, args.hw_port)
        print(f"LOCAL_LAB_READY: board=http://127.0.0.1:{args.board_port} "
              f"xvc=127.0.0.1:{args.xvc_port} "
              f"hw_server={'external' if args.no_hw_server else f'127.0.0.1:{args.hw_port}'}", flush=True)
        print("In Vivado's Tcl console:", flush=True)
        print("  open_hw_manager", flush=True)
        if args.no_hw_server:
            print("  connect_hw_server", flush=True)
            print(f"  open_hw_target -xvc_url 127.0.0.1:{args.xvc_port}", flush=True)
        else:
            print(f"  set ::env(HW_SERVER_URL) {{TCP:127.0.0.1:{args.hw_port}}}", flush=True)
            print(f"  source {{{ROOT / 'scripts/connect_xvc.tcl'}}}", flush=True)
            print(f"  connect_virtual_target 127.0.0.1:{args.xvc_port}", flush=True)
        print("Choose your bitstream in Vivado's Program Device dialog. "
              "The localhost analyzer does not require an LTX.", flush=True)
        print("Press Ctrl-C to stop the services.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("A local lab service exited unexpectedly")
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    main()
