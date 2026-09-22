import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frames import decode_frames, frame_addresses, packets, to_bitdata


def small_part():
    return {"idcode": 0x0362D093, "global_clock_regions": {"top": {"rows": {
        str(row): {"configuration_buses": {"CLB_IO_CLK": {
            "configuration_columns": {"0": {"frame_count": 2}}
        }}} for row in range(2)
    }}}}


def image(device_id=0x0362D093):
    # Two rows of two frames each, followed by two zero padding frames per row.
    frame0 = [0] * 101
    frame0[0], frame0[50] = 0x10, 0x2001
    words = [0xAA995566, 0x30018001, device_id, 0x30002001, 0,
             0x30008001, 1, 0x30004000, 0x50000000 | 808]
    words += frame0 + [0] * 303 + [1] * 101 + [0] * 303
    return struct.pack(f">{len(words)}I", *words)


class FrameTests(unittest.TestCase):
    def test_far_increment_and_row_padding(self):
        self.assertEqual(frame_addresses(small_part()), [0, 1, 0x20000, 0x20001])
        frames, report = decode_frames(image(), small_part())
        self.assertTrue(report["complete"])
        self.assertEqual(report["padding_frames"], 4)
        self.assertEqual(frames[0x20000], (1,) * 101)
        self.assertEqual(to_bitdata(frames)[0][1], {4, 1613})

    def test_wrong_id_and_truncated_frames_rejected(self):
        for data in (image(0x123), image()[:-4], image()[:-1]):
            with self.assertRaises(ValueError):
                decode_frames(data, small_part())

    def test_missing_sync_rejected(self):
        with self.assertRaises(ValueError):
            list(packets(b"not a configuration"))

    def test_capture_matches_bitfile_frames(self):
        root = Path(__file__).resolve().parents[2]
        capture = root / "build/configuration.bin"
        bitfile = root / "build/counter/counter.bit"
        partfile = root / "third_party/prjxray-db/artix7/xc7a35tcpg236-1/part.json"
        if not all(p.exists() for p in (capture, bitfile, partfile)):
            self.skipTest("Run real Phase 2 acceptance and install the database first")
        import json
        part = json.loads(partfile.read_text())
        a, report_a = decode_frames(capture.read_bytes(), part)
        b, report_b = decode_frames(bitfile.read_bytes(), part)
        self.assertEqual(a, b)
        self.assertEqual(report_a, report_b)
        self.assertEqual(len(a), 5408)


if __name__ == "__main__":
    unittest.main()
