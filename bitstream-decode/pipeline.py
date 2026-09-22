"""Decode captured configuration into a simulator-ready physical netlist.

Never reads the original RTL, checkpoint, or Vivado netlist. It only uses the
captured configuration and the pinned Project X-Ray device database.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def convert(input_path, output_path):
    source, output = Path(input_path).resolve(), Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = ROOT / "third_party/prjxray-db/artix7"
    for label, command in [
        ("decode", [sys.executable, str(ROOT / "bitstream-decode/decode.py"), str(source),
                    "--output", str(output / "design.fasm"), "--db-root", str(database)]),
        ("fasm2bels", [sys.executable, "-m", "fasm2bels", "--connection_database", str(ROOT / "build/xc7a35t.db"),
                        "--db_root", str(database), "--part", "xc7a35tcpg236-1",
                        "--fasm_file", str(output / "design.fasm"),
                        "--verilog_file", str(output / "decoded.v"),
                        "--xdc_file", str(output / "decoded.xdc"), "--iostandard", "LVCMOS33", "--drive", "12"]),
    ]:
        with (output / f"{label}.log").open("w") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    # Fixed filenames in a controlled working directory avoid Yosys command injection.
    command = "read_verilog -lib -nowb +/xilinx/cells_sim.v; read_verilog decoded.v; hierarchy -top top; write_json netlist.json"
    with (output / "yosys.log").open("w") as log:
        subprocess.run(["yosys", "-Q", "-T", "-p", command], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    return output / "netlist.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", default="build/decoded")
    args = parser.parse_args()
    print(convert(args.input, args.output))
