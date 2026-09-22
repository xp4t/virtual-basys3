# Reference provenance

Reviewed before implementation on 2026-09-13:

- [XAPP1251](https://docs.amd.com/v/u/en-US/xapp1251-xvc-zynq-petalinux),
  v1.0, April 30, 2015: XVC transport and Vivado connection workflow.
- [Official XVC protocol](https://github.com/Xilinx/XilinxVirtualCable/blob/ee2e5ffa90e09e1dbb88071222af3724cbaeb246/README.md)
  and [reference xvcServer.c](https://github.com/Xilinx/XilinxVirtualCable/blob/ee2e5ffa90e09e1dbb88071222af3724cbaeb246/jtag/zynq7000/XAPP1251/src/xvcServer.c).
  The downloaded C file retains its CC0 provenance; our server is an independent Python implementation.
- [UG470](https://docs.amd.com/v/u/en-US/ug470_7Series_Config), v1.17, December 5, 2023:
  Table 1-1 (7A35T IDCODE X362D093, revision 0 or later, IR length 6);
  Chapter 10 (TAP, opcodes, IR capture); Table 6-5 (JTAG register readback).
- Installed AMD BSDL:
  `/home/xpat/Xilinx/2025.1/Vivado/data/parts/xilinx/artix7/public/bsdl/xc7a35t_cpg236.bsd`.
  Lines 479–520 confirm IR length/opcodes/status; lines 553–558 encode
  `XXXX 0011011 000101101 00001001001 1`, i.e. `0xX362D093`.
  Revision 0 is selected for this virtual device, giving `0x0362D093`.
- [Project X-Ray](https://github.com/f4pga/prjxray) and
  [device databases](https://github.com/f4pga/prjxray-db): reviewed their purpose and
  Artix-7 database layout; fabric decoding remains gated on Phase 1–2 acceptance.
- [Digilent Basys3 master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Basys-3-Master.xdc),
  downloaded here as `Basys-3-Master.xdc`. Root `basys3.jpg` was supplied in the workspace.

Correction: [XAPP1252](https://docs.amd.com/v/u/en-US/xapp1252-burst-clk-data-recovery)
is AMD's burst-mode clock/data recovery application note, not an XVC specification.

XVC vectors and integers are little-endian; configuration packet words have their own
MSB-first JTAG serialization. Those are separate layers and must not share a blanket
byte-order conversion. The server keeps TAP state across requests and reconnects,
and admits only one controlling TCP client at a time.
