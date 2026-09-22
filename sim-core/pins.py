"""Bind reconstructed physical pad ports to package pins and board XDC names."""

import csv
import re
from pathlib import Path


def parse_xdc(path, include_commented=False):
    """Parse static PACKAGE_PIN constraints without executing Tcl.

    Supports Digilent's set_property -dict form and ordinary PACKAGE_PIN lines.
    Arbitrary Tcl expressions/variables are intentionally outside this parser.
    """
    pins = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("#"):
            if not include_commented:
                continue
            line = line[1:].strip()
        if not line.startswith("set_property"):
            continue
        pin = re.search(r"\bPACKAGE_PIN\s+([A-Z]+[0-9]+)\b", line)
        port = re.search(r"\[get_ports\s+(?:\{([^}]+)\}|([^\s\]]+))\s*\]", line)
        if pin and port:
            name = port.group(1) or port.group(2)
            if name in pins and pins[name] != pin.group(1):
                raise ValueError(f"Conflicting PACKAGE_PIN for {name}")
            pins[name] = pin.group(1)
    return pins


class BoardPins:
    def __init__(self, simulator, package_csv, master_xdc):
        self.simulator = simulator
        with open(package_csv, newline="") as stream:
            sites = {row["site"]: row["pin"] for row in csv.DictReader(stream)}
        physical = {}
        for name, port in simulator.ports.items():
            match = re.search(r"(IOB_X[0-9]+Y[0-9]+)_[IO]PAD$", name)
            if not match or match.group(1) not in sites:
                raise ValueError(f"Cannot map reconstructed pad {name}")
            if len(port["bits"]) != 1:
                raise ValueError("Expected one bit per physical pad")
            physical[sites[match.group(1)]] = name
        self.package_pins = parse_xdc(master_xdc, include_commented=True)
        self.ports = {name: physical[pin] for name, pin in self.package_pins.items() if pin in physical}

    def drive(self, controls):
        self.simulator.drive({self.ports[name]: value for name, value in controls.items()
                              if name in self.ports and self.simulator.ports[self.ports[name]]["direction"] == "input"})

    def read(self, name):
        return self.simulator.read(self.ports[name]) if name in self.ports else None

    def led_word(self):
        values = [self.read(f"led[{i}]") for i in range(16)]
        return None if None in values else sum(value << i for i, value in enumerate(values))

    def cycle(self):
        self.simulator.cycle(self.ports["clk"])
