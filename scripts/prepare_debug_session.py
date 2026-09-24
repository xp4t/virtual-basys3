"""Prepare a Vivado GUI command for a matching BIT/LTX pair on a real Basys3."""

import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def choose_file(folder: Path, suffix: str, explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.resolve()
    else:
        matches = sorted(folder.glob(f"*{suffix}"))
        if len(matches) != 1:
            raise ValueError(f"Expected one {suffix} file in {folder}, found {len(matches)}; pass --{suffix[1:]} explicitly")
        candidate = matches[0].resolve()
    if not candidate.is_file() or candidate.suffix.lower() != suffix:
        raise ValueError(f"Missing {suffix} file: {candidate}")
    return candidate


def debug_core_counts(ltx: Path) -> tuple[int, int]:
    data = json.loads(ltx.read_text())
    cores = [core for item in data["ltx_root"]["ltx_data"]
             if item.get("active", True) for core in item.get("debug_cores", [])]
    ilas = sum(core.get("type", "").startswith("ILA_") for core in cores)
    vios = sum(core.get("type", "").startswith("VIO_") for core in cores)
    if not ilas:
        raise ValueError(f"{ltx} contains no active ILA core")
    return ilas, vios


def tcl_text(value: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"[encoding convertfrom utf-8 [binary decode base64 {{{encoded}}}]]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bit", type=Path, help="bitstream (defaults to the sole .bit in this folder)")
    parser.add_argument("--ltx", type=Path, help="probes file (defaults to the sole .ltx in this folder)")
    parser.add_argument("--target", choices=("physical", "virtual"), default="physical")
    parser.add_argument("--hw-server-url", default="TCP:127.0.0.1:3121")
    parser.add_argument("--hw-target", help="Vivado hardware target name or unique glob")
    args = parser.parse_args()
    folder = Path.cwd()
    bit = choose_file(folder, ".bit", args.bit)
    ltx = choose_file(folder, ".ltx", args.ltx)
    with bit.open("rb") as source:
        header = source.read(512)
    if b"7a35tcpg236" not in header:
        raise ValueError(f"{bit} is not a Basys3 xc7a35tcpg236 bitstream")
    ilas, vios = debug_core_counts(ltx)
    if args.target == "virtual":
        parser.error("This virtual XVC server cannot emulate an arbitrary ILA from only a .bit and .ltx. "
                     "Use a physical Basys3, or supply an implemented design netlist/checkpoint "
                     "and a matching XSI model.")
    key = hashlib.sha256(f"{bit}\n{ltx}".encode()).hexdigest()[:16]
    output = ROOT / "build" / "debug_sessions" / key / "connect.tcl"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated for a physical Basys3 by prepare_debug_session.py.",
        "set ::env(DEBUG_TARGET) physical",
        "unset -nocomplain ::env(HW_TARGET)",
        f"set ::env(BIT_FILE) {tcl_text(str(bit))}",
        f"set ::env(LTX_FILE) {tcl_text(str(ltx))}",
        f"set ::env(HW_SERVER_URL) {tcl_text(args.hw_server_url)}",
        f"set ::env(EXPECTED_ILAS) {ilas}",
        f"set ::env(EXPECTED_VIOS) {vios}",
    ]
    if args.hw_target:
        lines.append(f"set ::env(HW_TARGET) {tcl_text(args.hw_target)}")
    lines.append(f"source {tcl_text(str(ROOT / 'scripts/connect_debug_gui.tcl'))}")
    output.write_text("\n".join(lines) + "\n")
    print(f"Physical Basys3: {ilas} ILA, {vios} VIO declared in {ltx.name}")
    print(f"BIT: {bit}")
    print(f"LTX: {ltx}")
    print("Open Vivado Hardware Manager, then run in its Tcl console:")
    print(f"  source {{{output}}}")
    print("The board must be connected to the selected hw_server before sourcing the command.")


if __name__ == "__main__":
    main()
