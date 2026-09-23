import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "xvc-server"), str(ROOT / "debug-hub-emu")]

from hub import DebugHub, ILA_REGISTER_MAP, ILA_REGISTER_WIDTH
from config import Configuration
from tap import Instruction, State, Tap


class DebugHubTest(unittest.TestCase):
    def test_raw_oracle_activates_on_user_selection_and_bounds_idle(self):
        class RawOracle:
            def __init__(self):
                self.calls = []

            def shift_vector(self, count, tms, tdi):
                self.calls.append(count)
                return bytes([0xFF]) * ((count + 7) // 8)

        def packed(bits):
            value = sum(bit << index for index, bit in enumerate(bits))
            return value.to_bytes((len(bits) + 7) // 8, "little")

        config = Configuration()
        config.done = True
        raw = RawOracle()
        tap = Tap(config=config, raw_debug=raw)
        tap.state = State.IDLE  # Matching a post-programming target.

        # One vector selects USER1 and performs an eight-bit DR scan.
        tms = ([1, 1, 0, 0] + [0] * 5 + [1] + [1, 0]
               + [1, 0, 0] + [0] * 7 + [1] + [1, 0])
        tdi = [0] * len(tms)
        for index in range(6):
            tdi[4 + index] = (int(Instruction.USER1) >> index) & 1
        result = int.from_bytes(tap.shift(len(tms), packed(tms), packed(tdi)), "little")
        self.assertEqual(raw.calls, [len(tms)])
        self.assertEqual((result >> 15) & 0xFF, 0xFF)

        # A large status/idle vector must not be mistaken for USER DR traffic
        # merely because USER1 remains the latched instruction.
        idle = [0] * 9000
        tap.shift(len(idle), packed(idle), packed(idle))
        self.assertEqual(raw.calls, [len(tms), 64])

        # Small XVC packets can also carry long idle delays. They must not
        # defeat the idle bound when hw_server fragments a large delay.
        tap.shift(1024, bytes(128), bytes(128))
        self.assertEqual(raw.calls[-1], 64)

        # A control transition at the end of a large vector cannot be dropped:
        # the next vector may continue an IR/DR scan from SELECT_DR.
        idle[-1] = 1
        tap.shift(len(idle), packed(idle), bytes((len(idle) + 7) // 8))
        self.assertEqual(raw.calls[-1], 9000)
        self.assertEqual(tap.state, State.SELECT_DR)

    def test_verified_discovery_sequence_is_gated_by_configuration(self):
        configured = [False]
        hub = DebugHub(lambda: configured[0])
        tap = Tap(debug=hub)
        tap.instruction = Instruction.USER1
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0, 1))
        configured[0] = True
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0x04900101, 32))
        hub.update(Instruction.USER1, 0, 32)
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0x04900101, 32))
        hub.update(Instruction.USER1, 0x04900100, 32)
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0x04900220, 32))
        hub.update(Instruction.USER1, 0, 32)
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0x04900101, 32))
        hub.update(Instruction.USER1, 0x04900180, 32)
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0, 32))
        hub.update(Instruction.USER1, 0, 17)
        tap.capture_dr()
        self.assertEqual(tap.dr_width, 1243)
        self.assertNotEqual(tap.dr, 0)
        hub.update(Instruction.USER1, 0xA9, 1243)
        tap.capture_dr()
        self.assertEqual((tap.dr, tap.dr_width), (0x04900101, 32))

    def test_ila_metadata_register_pipeline(self):
        hub = DebugHub(lambda: True)
        cases = {
            0x400: (37, (0, 0x0060008000, 0x0060008000)),
            0x500: (27, (0, 0x07FF0000, 0x07F00000, 0x07FF0000)),
            0x600: (139, (0x0000000003F480808301000080010008800,
                           0x621FBB4B686A2FB0C7417CB6CCA6FBF7800,
                           0x0000000003F480808301000080010008800,
                           0x621FBB4B686A2FB0C7417CB6CCA6FBF7800)),
        }
        for address, (width, values) in cases.items():
            for value in values:
                self.assertEqual(hub.query(address), (value, width))

    def test_other_user_chain_resets_switch_not_metadata_pipeline(self):
        hub = DebugHub(lambda: True)
        hub.state = "cleanup_status"
        hub.next_value = 0
        hub.query(0x500)
        hub.query(0x500)
        hub.query(0x600)
        hub.query(0x600)
        self.assertEqual(hub.capture(Instruction.USER3), (0, 8192))
        self.assertEqual(hub.state, "identify")
        self.assertEqual(hub.capture(Instruction.USER1), (0x04900101, 32))
        self.assertEqual(hub.query(0x500), (0x07F00000, 27))
        self.assertEqual(
            hub.query(0x600),
            (0x0000000003F480808301000080010008800, 139),
        )
        self.assertEqual(hub.query(0x500), (0x07FF0000, 27))
        self.assertEqual(hub.query(0x400), (0x0060008000, 37))

    def test_ila_open_command_selects_full_register_map(self):
        hub = DebugHub(lambda: True)
        hub.slave_identification = True

        hub.update(Instruction.USER1, 0x04900180, 32)
        hub.update(Instruction.USER1, 0x400, 17)
        self.assertEqual(hub.capture(Instruction.USER1), (0x0060008000, 37))
        hub.update(Instruction.USER1, 0x00060890A9, 37)

        # The intervening status-port transaction does not consume the map.
        hub.update(Instruction.USER1, 0x04900180, 32)
        hub.update(Instruction.USER1, 0x500, 17)
        self.assertEqual(hub.capture(Instruction.USER1), (0x07FF0000, 27))
        hub.update(Instruction.USER1, 0x1A9, 27)

        hub.update(Instruction.USER1, 0x04900180, 32)
        hub.update(Instruction.USER1, 0x600, 17)
        self.assertEqual(
            hub.capture(Instruction.USER1),
            (ILA_REGISTER_MAP, ILA_REGISTER_WIDTH),
        )
        self.assertEqual(ILA_REGISTER_MAP.bit_count(), 134)


if __name__ == "__main__":
    unittest.main()
