"""Run native Vivado ILA/VIO acceptance with matching BIT, LTX and XSI files."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def wait_for_socket(process, address, family=socket.AF_INET):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with status {process.returncode}; check acceptance logs")
        try:
            with socket.socket(family, socket.SOCK_STREAM) as connection:
                connection.settimeout(1)
                connection.connect(address)
            return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Service did not start at {address}")


def main():
    # Ensure externally stopped interactive sessions still run the cleanup
    # block that terminates the bridge, XVC, and hw_server process groups.
    def stop_session(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_session)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design-dir", type=Path, default=ROOT / "build/debug_counter")
    parser.add_argument("--xsi-dir", type=Path, default=ROOT / "build/debug_xsi")
    parser.add_argument("--vivado-root", type=Path,
                        default=os.environ.get("XILINX_VIVADO", "/home/xpat/Xilinx/2025.1/Vivado"))
    parser.add_argument("--xvc-port", type=int, default=2548)
    parser.add_argument("--hw-port", type=int, default=3127)
    parser.add_argument("--expected-vios", type=int, choices=(0, 1), default=0)
    parser.add_argument("--interactive", action="store_true",
                        help="keep the matching XSI/XVC/hw_server stack running for Vivado GUI")
    args = parser.parse_args()
    design, xsi, vivado = (path.resolve() for path in
                           (args.design_dir, args.xsi_dir, args.vivado_root))
    manifest = json.loads((xsi / "design.json").read_text())
    for name in ("counter.bit", "counter.ltx", "funcsim.v"):
        digest = hashlib.sha256((design / name).read_bytes()).hexdigest()
        if manifest.get(name) != digest:
            raise ValueError(f"XSI model does not match {design / name}; rebuild the oracle")
    # Fail before starting anything if another target already owns these ports.
    for port in (args.xvc_port, args.hw_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    logs = design / ("interactive" if args.interactive else "acceptance")
    logs.mkdir(exist_ok=True)
    processes, outputs = [], []

    def start(command, name, cwd=ROOT, env=None):
        output = (logs / name).open("w")
        outputs.append(output)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process

    try:
        with tempfile.TemporaryDirectory(prefix="basys3-debug-") as temporary:
            oracle_socket = str(Path(temporary) / "xsi.sock")
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = ":".join([
                str(vivado / "lib/lnx64.o"), str(vivado / "lib/lnx64.o/Default"),
                env.get("LD_LIBRARY_PATH", "")])
            bridge = start([str(xsi / "xsi_bridge"), oracle_socket], "xsi.log", xsi, env)
            wait_for_socket(bridge, oracle_socket, socket.AF_UNIX)
            server = start(["python3", "xvc-server/server.py", "--port", str(args.xvc_port),
                            "--debug-oracle-socket", oracle_socket,
                            "--capture", str(logs / "configuration.bin")], "xvc.log")
            wait_for_socket(server, ("127.0.0.1", args.xvc_port))
            hardware = start([str(vivado / "bin/hw_server"), "-s", f"tcp::{args.hw_port}",
                              "-e", "set xvc-timeout 600"], "hw-server.log")
            wait_for_socket(hardware, ("127.0.0.1", args.hw_port))
            if args.interactive:
                print(f"DEBUG_STACK_READY: hw_server=127.0.0.1:{args.hw_port} "
                      f"xvc=127.0.0.1:{args.xvc_port}", flush=True)
                print("In Vivado's Tcl console, connect the virtual target:", flush=True)
                print("  open_hw_manager", flush=True)
                print(f"  set ::env(HW_SERVER_URL) {{TCP:127.0.0.1:{args.hw_port}}}",
                      flush=True)
                print(f"  source {{{ROOT / 'scripts/connect_xvc.tcl'}}}", flush=True)
                print(f"  connect_virtual_target 127.0.0.1:{args.xvc_port}", flush=True)
                print("Then use Vivado's Program Device dialog to choose:", flush=True)
                print(f"  BIT: {design / 'counter.bit'}", flush=True)
                print(f"  LTX: {design / 'counter.ltx'}", flush=True)
                print("The files are chosen in Vivado; this launcher only starts the matching fixture model.", flush=True)
                print("Keep this terminal open; press Ctrl-C to stop the stack.", flush=True)
                try:
                    while all(process.poll() is None for process in (bridge, server, hardware)):
                        time.sleep(0.5)
                except KeyboardInterrupt:
                    pass
                else:
                    raise RuntimeError(f"Debug service exited; check {logs}")
                return
            env.update(XVC_URL=f"127.0.0.1:{args.xvc_port}",
                       HW_SERVER_URL=f"127.0.0.1:{args.hw_port}",
                       DEBUG_DESIGN_DIR=str(design), EXPECTED_ILAS="1",
                       EXPECTED_VIOS=str(args.expected_vios), DEBUG_ACCEPT="1")
            # Always program the fixture in acceptance, regardless of the shell's
            # diagnostic settings.
            for key in ("SKIP_PROGRAM", "BIT_FILE", "LTX_FILE"):
                env.pop(key, None)
            client = start([str(vivado / "bin/vivado"), "-mode", "batch", "-source",
                            "scripts/probe_phase5.tcl", "-log", str(logs / "vivado.log"),
                            "-journal", str(logs / "vivado.jou")], "console.log", env=env)
            print(f"Testing {design / 'counter.ltx'}; logs: {logs}", flush=True)
            code = client.wait(timeout=3600)
            console = (logs / "console.log").read_text()
            passed = any(line.startswith("PHASE5_ACCEPT_PASS:") for line in console.splitlines())
            if code or not passed:
                raise RuntimeError(f"Native debug acceptance failed; see {logs / 'console.log'}")
            print("\n".join(line for line in console.splitlines()
                            if line.startswith(("PHASE5_", "ILA_CAPTURE_PASS:"))))
    finally:
        for process in reversed(processes):
            # Only terminate process groups created by this runner.
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
        for output in outputs:
            output.close()


if __name__ == "__main__":
    main()
