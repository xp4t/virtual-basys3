import random
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tap import IDCODE, Instruction, State, Tap
from server import XvcServer, recv_exact


def clocks(tap, tms, tdi=None):
    return [tap.clock(m, d) for m, d in zip(tms, tdi or [0] * len(tms))]


def number(bits):
    return sum(bit << i for i, bit in enumerate(bits))


def reset(tap):
    clocks(tap, [1] * 5 + [0])


def scan(tap, value, width, ir=False):
    clocks(tap, [1, 1, 0, 0] if ir else [1, 0, 0])
    result = clocks(tap, [0] * (width - 1) + [1],
                    [(value >> i) & 1 for i in range(width)])
    clocks(tap, [1, 0])
    return number(result)


class TapTests(unittest.TestCase):
    def test_five_ones_reset_from_every_state(self):
        for state in State:
            tap = Tap()
            tap.state = state
            tap.instruction = Instruction.BYPASS
            clocks(tap, [1] * 5)
            self.assertEqual(tap.state, State.RESET)
            self.assertEqual(tap.instruction, Instruction.IDCODE)

    def test_idcode_and_ir_capture(self):
        tap = Tap()
        reset(tap)
        self.assertEqual(scan(tap, 0, 32), IDCODE)
        self.assertEqual(scan(tap, Instruction.IDCODE, 6, ir=True), 0x11)
        self.assertEqual(scan(tap, 0, 64), IDCODE)

    def test_bypass_is_one_bit_delay_and_recaptures_zero(self):
        tap = Tap()
        reset(tap)
        scan(tap, Instruction.BYPASS, 6, ir=True)
        self.assertEqual(scan(tap, 0xA35B, 16), (0xA35B << 1) & 0xFFFF)
        self.assertEqual(scan(tap, 0, 1), 0)

    def test_last_shift_bit_and_pause_preserve_register(self):
        tap = Tap()
        reset(tap)
        clocks(tap, [1, 1, 0, 0])
        clocks(tap, [0, 0, 1], [1, 1, 1])
        clocks(tap, [0, 0, 0, 1, 0])  # EXIT1 -> PAUSE -> EXIT2 -> SHIFT
        clocks(tap, [0, 0, 1], [1, 1, 1])
        self.assertEqual(tap.instruction, Instruction.IDCODE)
        clocks(tap, [1])
        self.assertEqual(tap.instruction, Instruction.BYPASS)

    def test_chunk_boundaries_do_not_change_behavior(self):
        rng = random.Random(901)
        a, b = Tap(), Tap()
        for _ in range(100):
            n = rng.randrange(1, 150)
            tms = rng.randbytes((n + 7) // 8)
            tdi = rng.randbytes((n + 7) // 8)
            expected = number([b.clock((tms[i // 8] >> (i % 8)) & 1,
                                      (tdi[i // 8] >> (i % 8)) & 1) for i in range(n)])
            self.assertEqual(int.from_bytes(a.shift(n, tms, tdi), "little"), expected)
            self.assertEqual(a.state, b.state)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.server = XvcServer(("127.0.0.1", 0), max_bits=8192, timeout_seconds=2)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.sock = socket.create_connection(self.server.server_address, timeout=2)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def tearDown(self):
        self.sock.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_fragmented_and_coalesced_commands(self):
        for c in b"getinfo:":
            self.sock.sendall(bytes([c]))
        self.assertEqual(recv_exact(self.sock, 20), b"xvcServer_v1.0:2048\n"[:20])

    def test_pipelined_settck_and_reset_idcode(self):
        # Six reset/idle clocks + SELECT/CAPTURE/SHIFT + 32 data clocks.
        tms = [1] * 5 + [0, 1, 0, 0] + [0] * 31 + [1]
        size = (len(tms) + 7) // 8
        packed = number(tms).to_bytes(size, "little")
        self.sock.sendall(b"settck:" + struct.pack("<I", 250) + b"shift:" +
                          struct.pack("<I", len(tms)) + packed + bytes(size))
        self.assertEqual(recv_exact(self.sock, 4), struct.pack("<I", 250))
        self.assertEqual(int.from_bytes(recv_exact(self.sock, size), "little") >> 9, IDCODE)

    def test_oversized_shift_closes_without_allocating_payload(self):
        self.sock.sendall(b"shift:" + struct.pack("<I", 0xFFFFFFFF))
        self.assertEqual(self.sock.recv(1), b"")

    def test_unknown_command_closes(self):
        self.sock.sendall(b"bogus:")
        self.assertEqual(self.sock.recv(1), b"")

    def test_zero_shift_and_unused_padding(self):
        self.sock.sendall(b"shift:" + struct.pack("<I", 0) + b"getinfo:")
        self.assertEqual(recv_exact(self.sock, len(b"xvcServer_v1.0:2048\n")),
                         b"xvcServer_v1.0:2048\n")
        self.sock.sendall(b"shift:" + struct.pack("<I", 1) + b"\xff\xff")
        self.assertEqual(recv_exact(self.sock, 1), b"\x00")


if __name__ == "__main__":
    unittest.main()
