#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/debug_oracle_sim
oracle_trace="${ORACLE_TRACE:-build/phase5-xvc.jsonl}"
oracle_start="${ORACLE_START:-1420}"
oracle_end="${ORACLE_END:-1433}"
python3 debug-hub-emu/make_replay.py "$oracle_trace" "$oracle_start" "$oracle_end" build/debug_oracle_sim/replay_calls.vh
cd build/debug_oracle_sim
/home/xpat/Xilinx/2025.1/Vivado/bin/xvlog ../../build/debug_counter/funcsim.v ../../debug-hub-emu/oracle_tb.v
/home/xpat/Xilinx/2025.1/Vivado/bin/xelab oracle_tb glbl -s debug_oracle -L unisims_ver -L secureip
/home/xpat/Xilinx/2025.1/Vivado/bin/xsim debug_oracle -R
