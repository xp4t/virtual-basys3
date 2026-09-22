"""Compare bitstream-derived simulation against Vivado xsim behavioral RTL."""

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim-core"))
from logic import Simulator
from pins import BoardPins


def main():
    output = ROOT / "build/counter"
    for command in (
        ["xvlog", str(ROOT / "examples/counter/counter.v"), str(ROOT / "examples/counter/reference_tb.v")],
        ["xelab", "reference_tb", "-s", "reference_sim"],
        ["xsim", "reference_sim", "-tclbatch", str(ROOT / "scripts/xsim_run.tcl")],
    ):
        with (output / f"{command[0]}-accept.log").open("w") as log:
            subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    simulator = Simulator.load(output / "netlist.json")
    board = BoardPins(simulator, ROOT / "third_party/prjxray-db/artix7/xc7a35tcpg236-1/package_pins.csv",
                      ROOT / "references/Basys-3-Master.xdc")
    simulator.drive({name: 0 for name, port in simulator.ports.items() if port["direction"] == "input"})
    count = 0
    with (output / "reference.csv").open() as reference, (output / "simulated.csv").open("w") as result:
        writer = csv.writer(result)
        writer.writerow(["cycle", "reset", "enable", "led"])
        for sample in csv.DictReader(reference):
            board.drive({"btnC": int(sample["reset"]), "sw[0]": int(sample["enable"])})
            board.cycle()
            actual, expected = board.led_word(), int(sample["led"])
            if actual != expected:
                raise AssertionError(f"Cycle {sample['cycle']}: reconstructed netlist={actual}, Vivado RTL={expected}")
            writer.writerow([sample["cycle"], sample["reset"], sample["enable"], actual])
            count += 1
    if count != 1024:
        raise AssertionError(f"Expected 1024 samples, got {count}")
    report = {"status": "PASS", "samples": count, "reference": "Vivado xsim behavioral RTL",
              "implementation": "JTAG capture -> prjxray frames/FASM -> fasm2bels -> primitive simulation",
              "cells": dict(Counter(cell["type"] for cell in simulator.cells.values())),
              "frames": json.loads((output / "counter.decode.json").read_text()),
              "scope": "eight-bit counter, synchronous reset and enable; no timing simulation"}
    (output / "phase3-acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PHASE3_PASS: {count} samples match Vivado xsim; {len(simulator.cells)} cells, {len(simulator.flops)} flip-flops")


if __name__ == "__main__":
    main()
