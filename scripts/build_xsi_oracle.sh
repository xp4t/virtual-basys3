#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
vivado_root="${XILINX_VIVADO:-/home/xpat/Xilinx/2025.1/Vivado}"
root="$PWD"
design_dir="$(realpath "${DEBUG_DESIGN_DIR:-build/debug_counter}")"
out="$(realpath -m "${DEBUG_XSI_DIR:-build/debug_xsi}")"
for name in counter.bit counter.ltx funcsim.v; do
  if [[ ! -f "$design_dir/$name" ]]; then
    echo "Missing $design_dir/$name; build/export the matching debug design first" >&2
    exit 1
  fi
done
mkdir -p "$out"
cd "$out"
"$vivado_root/bin/xvlog" "$design_dir/funcsim.v" "$root/debug-hub-emu/xsi_top.v"
# XSI advances only half a JTAG cycle per call. Worker synchronization costs
# more than the RTL evaluation here and can make register reads time out in
# hw_server, even though the simulated core eventually returns valid data.
"$vivado_root/bin/xelab" xsi_top glbl -dll -s debug_xsi -L unisims_ver -L secureip -mt off
g++ -O3 -std=c++17 \
  -I"$vivado_root/data/xsim/include" \
  -I"$vivado_root/examples/xsim/verilog/xsi/counter" \
  -c "$vivado_root/examples/xsim/verilog/xsi/counter/xsi_loader.cpp" -o xsi_loader.o
g++ -O3 -std=c++17 \
  -I"$vivado_root/data/xsim/include" \
  -I"$vivado_root/examples/xsim/verilog/xsi/counter" \
  -c "$root/debug-hub-emu/xsi_bridge.cpp" -o xsi_bridge.o
g++ -o xsi_bridge xsi_bridge.o xsi_loader.o -ldl -lrt
python3 - "$design_dir" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

design = Path(sys.argv[1])
files = {name: hashlib.sha256((design / name).read_bytes()).hexdigest()
         for name in ("counter.bit", "counter.ltx", "funcsim.v")}
Path("design.json").write_text(json.dumps(files, indent=2) + "\n")
PY
