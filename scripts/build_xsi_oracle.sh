#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
vivado_root="${XILINX_VIVADO:-/home/xpat/Xilinx/2025.1/Vivado}"
out=build/debug_xsi
mkdir -p "$out"
cd "$out"
"$vivado_root/bin/xvlog" ../debug_counter/funcsim.v ../../debug-hub-emu/xsi_top.v
"$vivado_root/bin/xelab" xsi_top glbl -dll -s debug_xsi -L unisims_ver -L secureip
g++ -O3 -std=c++17 \
  -I"$vivado_root/data/xsim/include" \
  -I"$vivado_root/examples/xsim/verilog/xsi/counter" \
  -c "$vivado_root/examples/xsim/verilog/xsi/counter/xsi_loader.cpp" -o xsi_loader.o
g++ -O3 -std=c++17 \
  -I"$vivado_root/data/xsim/include" \
  -I"$vivado_root/examples/xsim/verilog/xsi/counter" \
  -c ../../debug-hub-emu/xsi_bridge.cpp -o xsi_bridge.o
g++ -o xsi_bridge xsi_bridge.o xsi_loader.o -ldl -lrt
