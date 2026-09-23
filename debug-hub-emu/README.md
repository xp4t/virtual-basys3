# Debug Hub / ILA / VIO

Native Vivado debugging uses the XSI bridge and a compiled functional netlist
of the matching counter design. The standalone `--debug-hub` option remains a
limited discovery model: its hard-coded ILA metadata does not implement capture
or VIO and should not be used for native debug acceptance.

The bridge runs the actual generated Debug Hub, ILA and VIO logic. It is a
Vivado-dependent development path, separate from the bitstream decoder and
browser board simulator. It does not automatically turn arbitrary bitstreams
into debug models. The supplied XSI top instantiates the `counter` fixture with
its switch enable asserted and a 100 MHz fabric clock.

## Build and test with matching LTX files

Load your Vivado environment (`XILINX_VIVADO` selects its installation), then
run these commands from the repository root.

ILA-only counter:

```sh
INCLUDE_ILA=1 vivado -mode batch -source scripts/build_counter.tcl
bash scripts/build_xsi_oracle.sh
python3 scripts/accept_phase5.py
```

Counter with both ILA and VIO:

```sh
INCLUDE_ILA=1 INCLUDE_VIO=1 vivado -mode batch -source scripts/build_counter.tcl
DEBUG_DESIGN_DIR=build/debug_vio_counter DEBUG_XSI_DIR=build/debug_vio_xsi \
  bash scripts/build_xsi_oracle.sh
python3 scripts/accept_phase5.py \
  --design-dir build/debug_vio_counter --xsi-dir build/debug_vio_xsi --expected-vios 1
```

The build produces `counter.bit`, `counter.ltx`, and `funcsim.v` together. The
XSI build records their hashes, and acceptance rejects a mismatched file before
starting any services. For an older ILA build that lacks `funcsim.v`, run
`vivado -mode batch -source scripts/export_debug_oracle.tcl` first.

The acceptance runner starts and cleans up its own XSI, XVC, and hardware-server
processes. Its default ports are 2548 and 3127; use `--xvc-port` and `--hw-port`
if those are occupied. Logs are written to the design's `acceptance/` directory.
Expect several minutes of gate-level simulation; a full run can take over ten
minutes on a small host.

Acceptance checks the LTX probe mapping, one eight-bit ILA port, depth 1024,
and 1024 consecutive counter samples including wraparound. With VIO, it also
asserts reset, reads back zero, captures a stopped counter, and releases enable
before checking the counting capture. CSV files are saved beside the LTX file.
A discovered core alone is not a passing result.

## Verified results

The native acceptance flow was run with Vivado 2025.1 and matching artifacts.
Both combinations passed the LTX and XSI hash check before programming:

| Fixture | Discovery | Capture and control result |
| --- | --- | --- |
| `build/debug_counter` | 1 ILA, 0 VIO | 1024 consecutive counting samples, including rollover |
| `build/debug_vio_counter` | 1 ILA, 1 VIO | Reset/readback, stopped zero capture, enable/hold control, and 1024 consecutive counting samples |

The acceptance logs are `build/ila-accept-run.log` and
`build/vio-accept-run.log`. Generated CSV captures are stored in
`build/debug_counter/` and `build/debug_vio_counter/` beside their matching
`.bit` and `.ltx` files. The regular regression checks also pass:

```text
24 XVC/debug unit tests: OK
5 simulation-core unit tests: OK
plain RTL counter check: 1024 samples, reset/enable/hold/rollover: PASS
```

These results cover the XSI-based native debug fixture. The standalone
`--debug-hub` model remains discovery-only and is not included in these capture
results.

## Interactive debugging

Start the bridge in its build directory:

```sh
cd build/debug_xsi
LD_LIBRARY_PATH="$XILINX_VIVADO/lib/lnx64.o:$XILINX_VIVADO/lib/lnx64.o/Default" \
  ./xsi_bridge /tmp/fpga-sim-xsi.sock
```

From another terminal at the repository root, start XVC:

```sh
python3 xvc-server/server.py --debug-oracle-socket /tmp/fpga-sim-xsi.sock
```

Start the hardware server in a third terminal:

```sh
hw_server -s tcp::3127 -e 'set xvc-timeout 600'
```

Connect Hardware Manager to `localhost:3127` and XVC `127.0.0.1:2542`. Program
with the exact `counter.bit` and `counter.ltx` used to build that XSI model.
For the combined fixture, run the bridge from `build/debug_vio_xsi` and select
the files in `build/debug_vio_counter` instead.

Gate-level simulation can take longer than a hardware cable transaction.
The XVC server therefore advertises 1024-bit transfers in XSI mode and bounds
pure idle delays. The hardware server also needs the extended `xvc-timeout`
shown above; otherwise valid register responses can arrive after the driver
has already failed initialization. AMD documents this setting in
[UG908, Advanced Options](https://docs.amd.com/r/2024.1-English/ug908-vivado-programming-debugging/Advanced-Options).

## Diagnostics

`probe_phase5.tcl` accepts `DEBUG_DESIGN_DIR`, `BIT_FILE`, `LTX_FILE`,
`XVC_URL`, `HW_SERVER_URL`, `EXPECTED_ILAS`, and `EXPECTED_VIOS` environment
variables. It fails if cores or LTX probes are missing. `DEBUG_ACCEPT=1` adds
the counter acceptance checks; `SKIP_PROGRAM=1` is only for diagnostics on an
already programmed target. The acceptance runner always programs its fixture.

`trace.py` reconstructs IR and DR transactions from a server `--trace` JSONL
file:

```sh
python3 debug-hub-emu/trace.py build/phase5-xvc.jsonl
python3 debug-hub-emu/trace.py --json build/phase5-xvc.jsonl
```
