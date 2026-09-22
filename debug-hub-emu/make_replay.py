"""Generate bounded Verilog calls that replay selected raw XVC vectors."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("start", type=int)
    parser.add_argument("end", type=int, help="exclusive XVC record index")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.trace.read_text().splitlines() if line]
    calls = []
    chunk_bits = 2048
    for index in range(args.start, args.end):
        record = records[index]
        width = record["bits"]
        tms = int.from_bytes(bytes.fromhex(record["tms"]), "little")
        tdi = int.from_bytes(bytes.fromhex(record["tdi"]), "little")
        for offset in range(0, width, chunk_bits):
            chunk_width = min(chunk_bits, width - offset)
            mask = (1 << chunk_width) - 1
            chunk_tms = (tms >> offset) & mask
            chunk_tdi = (tdi >> offset) & mask
            calls.append(
                f"    replay_record({index}, {offset}, {chunk_width}, "
                f"2048'h{chunk_tms:0512x}, 2048'h{chunk_tdi:0512x});"
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(calls) + "\n")


if __name__ == "__main__":
    main()
