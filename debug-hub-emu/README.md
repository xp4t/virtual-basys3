# Debug Hub / BSCAN emulator

Phase 5 is experimental and has not passed native Vivado ILA discovery yet.
The standalone model implements the observed USER1 BSCAN-switch discovery
exchange and reaches one `hw_ila` with the expected UUID, but its ILA property
register stream is not complete. A development-only XSI bridge can instead run
the generated Debug Hub/ILA functional netlist. Vivado receives the real core
map, UUID, and 35,083-bit ILA register-presence stream through that bridge, but
currently fails while initializing the downstream CseXsdb slave. This is not a
Phase 5 acceptance result.

`trace.py` reconstructs IR and DR transactions from a server `--trace` JSONL
file. It is used to isolate the USER-chain discovery traffic from configuration
traffic while developing the XSDB/Debug Hub model:

```sh
python3 debug-hub-emu/trace.py build/phase5-xvc.jsonl
python3 debug-hub-emu/trace.py --json build/phase5-xvc.jsonl
```

The ILA acceptance design is produced with `INCLUDE_ILA=1`:

```sh
INCLUDE_ILA=1 vivado -mode batch -source scripts/build_counter.tcl
vivado -mode batch -source scripts/probe_phase5.tcl
```

`probe_phase5.tcl` is diagnostic until it finds one `hw_ila`; its output marker
reports the number of native Hardware Manager cores discovered.

To build and run the XSI oracle (Vivado 2025.1 paths are the defaults):

```sh
bash scripts/build_xsi_oracle.sh
cd build/debug_xsi
LD_LIBRARY_PATH=/home/xpat/Xilinx/2025.1/Vivado/lib/lnx64.o:/home/xpat/Xilinx/2025.1/Vivado/lib/lnx64.o/Default \
  ./xsi_bridge /tmp/fpga-sim-xsi.sock
```

Then, from the repository root, start XVC with
`--debug-oracle-socket /tmp/fpga-sim-xsi.sock`. The XSI path is a protocol
oracle for developing the standalone emulator, not a runtime dependency of the
finished virtual target.
