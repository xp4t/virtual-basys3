"""XVC 1.0 TCP endpoint. Standard library only, Python 3.10+."""

import argparse
import json
import logging
import socket
import socketserver
import struct
import threading
import sys
from pathlib import Path
from contextlib import nullcontext

from tap import Tap
from config import Configuration

LOG = logging.getLogger("xvc")
U32 = struct.Struct("<I")


def recv_exact(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise EOFError("peer closed connection")
        data.extend(chunk)
    return bytes(data)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        server = self.server
        if not server.owner.acquire(blocking=False):
            LOG.warning("Rejected concurrent client %s", self.client_address)
            return
        LOG.info("Connected %s", self.client_address)
        try:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.request.settimeout(server.timeout_seconds)
            while True:
                command = bytearray()
                while not command.endswith(b":"):
                    command.extend(recv_exact(self.request, 1))
                    if len(command) > 8:
                        raise ValueError("invalid command")
                if command == b"getinfo:":
                    reply = f"xvcServer_v1.0:{server.vector_length}\n".encode("ascii")
                elif command == b"settck:":
                    requested, = U32.unpack(recv_exact(self.request, 4))
                    # Logical TCK period; this emulator does not sleep per edge.
                    server.period_ns = max(1, requested)
                    reply = U32.pack(server.period_ns)
                elif command == b"shift:":
                    count, = U32.unpack(recv_exact(self.request, 4))
                    if count > server.max_bits:
                        raise ValueError(f"shift {count} exceeds {server.max_bits} bits")
                    size = (count + 7) // 8
                    tms = recv_exact(self.request, size)
                    tdi = recv_exact(self.request, size)
                    before = server.tap.state.name
                    reply = server.tap.shift(count, tms, tdi)
                    if server.trace:
                        server.trace.write(json.dumps({
                            "bits": count, "tms": tms.hex(), "tdi": tdi.hex(),
                            "tdo": reply.hex(), "before": before,
                            "after": server.tap.state.name,
                        }) + "\n")
                        server.trace.flush()
                else:
                    raise ValueError(f"unknown command {bytes(command)!r}")
                self.request.sendall(reply)
        except EOFError:
            pass
        except (OSError, ValueError) as error:
            LOG.warning("Closing %s: %s", self.client_address, error)
        finally:
            server.owner.release()
            LOG.info("Disconnected %s", self.client_address)


class XvcServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, *, tap=None, max_bits=65536, trace=None,
                 timeout_seconds=120):
        if not 4 <= max_bits <= 8 * 1024 * 1024:
            raise ValueError("max_bits must be between 4 and 8388608")
        self.tap = tap if tap is not None else Tap()
        self.max_bits = max_bits
        # Vivado 2025.1 treats getinfo's length as the combined TMS+TDI
        # byte budget, despite the protocol README calling it vector width.
        # Advertising max_bits/4 is conservative for both interpretations.
        self.vector_length = max_bits // 4
        self.trace = trace
        self.timeout_seconds = timeout_seconds
        self.owner = threading.Lock()
        self.period_ns = 100
        super().__init__(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2542)
    parser.add_argument("--max-bits", type=int, default=65536)
    parser.add_argument("--trace", help="write raw XVC shifts to JSONL")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--phase", type=int, choices=(1, 2), default=2)
    parser.add_argument("--capture", default="build/configuration.bin",
                        help="save accepted configuration words at startup (Phase 2)")
    parser.add_argument("--simulate", action="store_true", help="decode programmed fabric and serve the board companion")
    parser.add_argument("--board-port", type=int, default=8080)
    parser.add_argument("--debug-hub", action="store_true",
                        help="enable the experimental USER1 Debug Hub discovery model")
    parser.add_argument("--debug-oracle-socket",
                        help="development only: source USER-chain TDO from an XSI oracle")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    with (open(args.trace, "a", encoding="utf-8") if args.trace else nullcontext()) as trace:
        runtime = http_server = None
        if args.simulate:
            if args.phase != 2:
                parser.error("--simulate requires --phase 2")
            root = Path(__file__).resolve().parents[1]
            sys.path[:0] = [str(root / name) for name in ("sim-core", "bitstream-decode", "board-visualizer")]
            from runtime import BoardRuntime
            from http_server import create_http_server
            runtime = BoardRuntime()
            runtime.endpoint = f"{args.host}:{args.port}"
            http_server = create_http_server((args.host, args.board_port), runtime)
            threading.Thread(target=http_server.serve_forever, daemon=True).start()
            LOG.info("Board companion: http://%s:%d", args.host, args.board_port)
        config = Configuration(args.capture, runtime.programmed if runtime else None,
                               runtime.reset if runtime else None) if args.phase == 2 else None
        debug = None
        if args.debug_hub:
            root = Path(__file__).resolve().parents[1]
            sys.path.insert(0, str(root / "debug-hub-emu"))
            from hub import DebugHub
            debug = DebugHub(lambda: config is not None and config.done)
        raw_debug = None
        if args.debug_oracle_socket:
            root = Path(__file__).resolve().parents[1]
            sys.path.insert(0, str(root / "debug-hub-emu"))
            from xsi_client import XsiDebug
            raw_debug = XsiDebug(args.debug_oracle_socket)
        tap = Tap(config, debug, raw_debug)
        with XvcServer((args.host, args.port), tap=tap, max_bits=args.max_bits, trace=trace) as server:
            LOG.info("Virtual xc7a35t XVC listening on %s:%d", *server.server_address)
            if runtime:
                runtime.connected = server.owner.locked
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                LOG.info("Stopped")
            finally:
                if http_server:
                    http_server.shutdown()
                    http_server.server_close()
                    runtime.close()
                if raw_debug:
                    raw_debug.close()


if __name__ == "__main__":
    main()
