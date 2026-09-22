"""Turn raw XVC vectors into IR/DR scans for Debug Hub investigation."""

import argparse
import json
from collections import Counter
from enum import IntEnum
from pathlib import Path


class State(IntEnum):
    RESET = 0; IDLE = 1; SELECT_DR = 2; CAPTURE_DR = 3
    SHIFT_DR = 4; EXIT1_DR = 5; PAUSE_DR = 6; EXIT2_DR = 7
    UPDATE_DR = 8; SELECT_IR = 9; CAPTURE_IR = 10; SHIFT_IR = 11
    EXIT1_IR = 12; PAUSE_IR = 13; EXIT2_IR = 14; UPDATE_IR = 15


NEXT = (
    (State.IDLE, State.RESET), (State.IDLE, State.SELECT_DR),
    (State.CAPTURE_DR, State.SELECT_IR), (State.SHIFT_DR, State.EXIT1_DR),
    (State.SHIFT_DR, State.EXIT1_DR), (State.PAUSE_DR, State.UPDATE_DR),
    (State.PAUSE_DR, State.EXIT2_DR), (State.SHIFT_DR, State.UPDATE_DR),
    (State.IDLE, State.SELECT_DR), (State.CAPTURE_IR, State.RESET),
    (State.SHIFT_IR, State.EXIT1_IR), (State.SHIFT_IR, State.EXIT1_IR),
    (State.PAUSE_IR, State.UPDATE_IR), (State.PAUSE_IR, State.EXIT2_IR),
    (State.SHIFT_IR, State.UPDATE_IR), (State.IDLE, State.SELECT_DR),
)


def bit(data, index):
    return (data[index // 8] >> (index % 8)) & 1


def packed(value, width):
    return f"0x{value:0{max(1, (width + 3) // 4)}x}"


def scans(records):
    state, instruction = State.RESET, 0x09
    active = None
    for record_index, record in enumerate(records):
        tms, tdi, tdo = (bytes.fromhex(record[name]) for name in ("tms", "tdi", "tdo"))
        for index in range(record["bits"]):
            if state in (State.SHIFT_IR, State.SHIFT_DR):
                kind = "IR" if state == State.SHIFT_IR else "DR"
                if active is None:
                    active = {"kind": kind, "instruction": instruction,
                              "bits": 0, "tdi_value": 0, "tdo_value": 0,
                              "keep": kind == "IR" or instruction in (0x02, 0x03, 0x22, 0x23),
                              "record": record_index}
                if active["keep"]:
                    active["tdi_value"] |= bit(tdi, index) << active["bits"]
                    active["tdo_value"] |= bit(tdo, index) << active["bits"]
                active["bits"] += 1
            state = NEXT[state][bit(tms, index)]
            if active is not None and state in (State.UPDATE_IR, State.UPDATE_DR):
                if active["keep"]:
                    active["tdi_hex"] = packed(active.pop("tdi_value"), active["bits"])
                    active["tdo_hex"] = packed(active.pop("tdo_value"), active["bits"])
                    active.pop("keep")
                    if active["kind"] == "IR":
                        instruction = int(active["tdi_hex"], 16) & 0x3F
                    yield active
                active = None
            if state == State.RESET:
                instruction = 0x09


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    records = [json.loads(line) for line in args.trace.read_text().splitlines() if line]
    result = list(scans(records))
    if args.json:
        print(json.dumps(result, indent=2))
        return
    counts = Counter((scan["kind"],
                      int(scan["tdi_hex"], 16) & 0x3F if scan["kind"] == "IR" else scan["instruction"],
                      scan["bits"]) for scan in result)
    print(f"{len(records)} XVC vectors -> {len(result)} completed scans")
    for (kind, instruction, width), count in sorted(counts.items()):
        label = f"IR 0x{instruction:02x}" if kind == "IR" else f"DR @ IR 0x{instruction:02x}"
        print(f"{count:5d}  {label:14s}  {width:7d} bits")


if __name__ == "__main__":
    main()
