"""Check actual Vivado ILA samples from the eight-bit counter fixtures."""

import argparse
import csv
from pathlib import Path


def check_capture(path, mode):
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        rows = csv.reader(source)
        header = next(rows)
        if len(header) != 4 or header[:2] != ["Sample in Buffer", "Sample in Window"]:
            raise ValueError(f"Expected one counter probe, got CSV columns {header}")
        samples = []
        base = 16
        for row in rows:
            if not row:
                continue
            if row[0].startswith("Radix"):
                base = {"HEX": 16, "BINARY": 2, "UNSIGNED": 10}[row[3].strip().upper()]
                continue
            if len(row) != 4 or int(row[0]) != len(samples):
                raise ValueError("ILA sample indexes are not consecutive")
            samples.append(int(row[3], base))
    if len(samples) != 1024:
        raise ValueError(f"Expected 1024 samples, got {len(samples)}")
    if any(not 0 <= value <= 255 for value in samples):
        raise ValueError("Counter samples exceed the eight-bit probe width")
    if mode == "stopped":
        if any(samples):
            raise ValueError("VIO reset/hold capture contains nonzero samples")
    elif any(current != (previous + 1) % 256 for previous, current in zip(samples, samples[1:])):
        raise ValueError("ILA samples are not consecutive eight-bit counter values")
    return len(samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--mode", choices=("counting", "stopped"), required=True)
    args = parser.parse_args()
    count = check_capture(args.path, args.mode)
    print(f"ILA_CAPTURE_PASS: {args.mode}, {count} samples, {args.path}")
