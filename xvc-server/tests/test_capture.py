import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_ila_csv import check_capture


class CaptureTest(unittest.TestCase):
    def capture(self, values, radix="HEX"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "capture.csv"
        with path.open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["Sample in Buffer", "Sample in Window", "TRIGGER", "count[7:0]"])
            writer.writerow(["Radix - UNSIGNED", "UNSIGNED", "UNSIGNED", radix])
            for i, value in enumerate(values):
                writer.writerow([i, i, int(i == 0), format(value, "x") if radix == "HEX" else value])
        return path

    def test_counting_across_rollover_in_both_radices(self):
        for radix in ("HEX", "UNSIGNED"):
            path = self.capture([(251 + i) % 256 for i in range(1024)], radix)
            self.assertEqual(check_capture(path, "counting"), 1024)

    def test_vio_reset_capture_and_failed_reset(self):
        self.assertEqual(check_capture(self.capture([0] * 1024), "stopped"), 1024)
        with self.assertRaisesRegex(ValueError, "nonzero"):
            check_capture(self.capture([1] * 1024), "stopped")

    def test_corrupted_and_truncated_capture(self):
        with self.assertRaisesRegex(ValueError, "1024 samples"):
            check_capture(self.capture(range(256)), "counting")
        values = [i % 256 for i in range(1024)]
        values[500] ^= 4
        with self.assertRaisesRegex(ValueError, "not consecutive"):
            check_capture(self.capture(values), "counting")


if __name__ == "__main__":
    unittest.main()
