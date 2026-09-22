import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import Configuration, DEVICE_ID, SYNC, reverse32
from tap import Tap, Instruction
from test_phase1 import reset, scan, clocks


def send_words(tap, words):
    scan(tap, Instruction.CFG_IN, 6, ir=True)
    wire = sum(reverse32(word) << (32 * i) for i, word in enumerate(words))
    scan(tap, wire, 32 * len(words))


def write(address, count=1):
    return 0x30000000 | (address << 13) | count


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = Configuration()
        self.tap = Tap(self.config)
        reset(self.tap)

    def test_ug470_table_6_5_status_readback(self):
        send_words(self.tap, [SYNC, 0x20000000, 0x2800E001, 0x20000000, 0x20000000])
        scan(self.tap, Instruction.CFG_OUT, 6, ir=True)
        self.assertEqual(reverse32(scan(self.tap, 0, 32)), self.config.status)
        self.assertEqual(self.config.status & 0x7800, 0x1800)

    def configure(self, device_id=DEVICE_ID):
        scan(self.tap, Instruction.JPROGRAM, 6, ir=True)
        # Include a sync-like word in opaque FDRI data: it must not be parsed as a header.
        send_words(self.tap, [SYNC, write(12), device_id, write(2, 0), 0x50000004,
                              SYNC, write(4), 0xDEADBEEF, 0, write(4), 5])

    def test_configuration_and_jtag_reset_preserve_done(self):
        self.configure()
        self.assertEqual(self.config.fdri_words, 4)
        self.assertFalse(self.config.done)
        scan(self.tap, Instruction.JSTART, 6, ir=True)
        clocks(self.tap, [0] * 2000)
        self.assertTrue(self.config.done)
        reset(self.tap)
        self.assertTrue(self.config.done)
        self.assertEqual(self.config.ir_capture, 0x35)
        self.assertEqual(self.config.status & 0x7800, 0x7800)
        scan(self.tap, Instruction.JPROGRAM, 6, ir=True)
        self.assertFalse(self.config.done)
        self.assertEqual(self.config.fdri_words, 0)

    def test_wrong_id_does_not_report_success(self):
        self.configure(0x12345679)
        scan(self.tap, Instruction.JSTART, 6, ir=True)
        clocks(self.tap, [0] * 2000)
        self.assertFalse(self.config.done)
        self.assertTrue(self.config.status & (1 << 15))

    def test_start_without_fdri_does_not_report_success(self):
        scan(self.tap, Instruction.JSTART, 6, ir=True)
        clocks(self.tap, [0] * 2000)
        self.assertFalse(self.config.done)

    def test_desync_and_resync_read_multiple_registers(self):
        send_words(self.tap, [SYNC, write(4), 13, 0x20000000])
        self.assertFalse(self.config.synced)
        send_words(self.tap, [SYNC, 0x28018001, 0x2800E001, 0x20000000, 0x20000000])
        scan(self.tap, Instruction.CFG_OUT, 6, ir=True)
        value = scan(self.tap, 0, 64)
        self.assertEqual(reverse32(value & 0xFFFFFFFF), DEVICE_ID)
        self.assertEqual(reverse32(value >> 32), self.config.status)

    def test_isc_status(self):
        scan(self.tap, Instruction.ISC_ENABLE, 6, ir=True)
        self.assertEqual(self.config.ir_capture, 0x19)
        scan(self.tap, Instruction.ISC_DISABLE, 6, ir=True)
        self.assertEqual(self.config.ir_capture, 0x11)


if __name__ == "__main__":
    unittest.main()
