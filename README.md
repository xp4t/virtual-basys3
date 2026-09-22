# Virtual Basys3 FPGA for Vivado

This project makes Vivado Hardware Manager see a software-only Artix-7 FPGA.
Vivado connects to it through Xilinx Virtual Cable (XVC), so no physical board
or USB cable is required.

The easiest working demo is the included eight-bit counter. You program it from
Vivado, then use a Basys3 board page in your browser to control its switches and
watch its LEDs.

## What you need

- Linux
- Python 3.10 or newer, including `venv` and `pip`
- Git, a C/C++ compiler, and build tools
- Yosys available on `PATH`
- Vivado with support for `xc7a35tcpg236-1`
- About 5 GB of free disk space and 4 GB of available RAM

The project has been tested with Vivado 2025.1.

On Ubuntu, the non-Vivado tools can usually be installed with:

```sh
sudo apt install python3 python3-venv python3-pip git build-essential yosys
```

If your shell cannot find `vivado`, load your installation's environment first,
for example `source /tools/Xilinx/Vivado/2025.1/settings64.sh`.

## First-time setup

Open a terminal and run:

```sh
git clone https://github.com/xp4t/virtual-basys3.git
cd virtual-basys3
bash scripts/setup_phase3.sh
```

This creates `.venv`, installs the Python packages, and downloads the pinned
Project X-Ray databases and decoder tools. It can take several minutes.

Next, build the included counter bitstream with Vivado:

```sh
vivado -mode batch -source scripts/build_counter.tcl -log build/counter-build.log
```

The finished file is `build/counter/counter.bit`.

## Run the virtual FPGA

Start the XVC server and board page:

```sh
.venv/bin/python xvc-server/server.py --simulate
```

Leave this terminal running. You should see messages containing:

```text
Board companion: http://127.0.0.1:8080
Virtual xc7a35t XVC listening on 127.0.0.1:2542
```

Open <http://127.0.0.1:8080> in a browser. The page initially says that the
device is not configured.

## Connect Vivado

In Vivado:

1. Open **Hardware Manager**.
2. Select **Open Target**, then **Add Xilinx Virtual Cable**.
3. Enter host `127.0.0.1` and port `2542`.
4. Let Vivado auto-connect. It should find one `xc7a35t` device.
5. Select **Program Device**.
6. Choose `build/counter/counter.bit` and start programming.

You can also connect from Vivado's Tcl console:

```tcl
open_hw_manager
connect_hw_server
open_hw_target -xvc_url 127.0.0.1:2542
```

After programming, the server decodes the bitstream and builds its simulation
model. The first decode is slow and may use about 3 GB of RAM; later runs reuse
the generated files. Wait until the browser page reports **Ready**.

Turn on switch **SW0** to enable the demo counter. LEDs 0 through 7 will count.
The browser's Run, Pause, Step, and speed controls change the simulated clock.
Press the center button to reset the counter.

Stop the server with `Ctrl+C` when finished.

## Using your own bitstream

Program an unencrypted, uncompressed Basys3 `xc7a35t` bitstream in the same way.
The simulator currently supports the fabric needed by the included counter:
LUTs, common flip-flops, carry logic, muxes, basic I/O, routing, and simple clock
buffers.

Designs using unsupported resources such as BRAM, DSP, or MMCM blocks will show
an explicit error on the board page. This project does not synthesize or route
your design; Vivado still creates the bitstream.

## Common problems

### Vivado finds no device

Keep the XVC server running, close the hardware target, and open it again. Vivado
2025.1 occasionally needs a second connection while a new XVC target is being
registered. If that does not help, restart the `hw_server` process and reconnect.

### Programming succeeds, but the board page never becomes ready

Read the error shown on the page and the server terminal. The usual causes are a
missing setup dependency or a resource that the simulator does not support yet.

### Port 2542 or 8080 is already in use

Stop the older server, or select different ports:

```sh
.venv/bin/python xvc-server/server.py --simulate --port 2543 --board-port 8081
```

Use the same XVC port in Vivado and open the matching board-page URL.

### Vivado is on another computer

Start the server so it listens on the network:

```sh
.venv/bin/python xvc-server/server.py --simulate --host 0.0.0.0
```

Connect Vivado to this computer's IP address. XVC has no authentication, so only
do this on a trusted network or behind a firewall.

## Current status

| Feature | Status |
| --- | --- |
| Vivado XVC connection and `xc7a35t` detection | Working |
| Programming with a `.bit` file | Working |
| Counter bitstream decoding and simulation | Working |
| Browser-based Basys3 switches, buttons, and LEDs | Working |
| General Artix-7 resource coverage | Partial |
| ILA/VIO debugging in Hardware Manager | Experimental; not working end to end |

ILA development is documented in
[`debug-hub-emu/README.md`](debug-hub-emu/README.md). It is not required for the
working counter and board-visualizer demo.

## Tests and validation

The quick regression suites are:

```sh
python3 -m unittest discover -s xvc-server/tests -v
python3 -m unittest discover -s sim-core/tests -v
```

Real Vivado acceptance scripts are also available:

```sh
vivado -mode batch -source scripts/accept_phase1.tcl -log build/phase1.log
vivado -mode batch -source scripts/accept_phase2.tcl -log build/phase2.log
```

Reference documents and database provenance are listed in
[`references/README.md`](references/README.md).
