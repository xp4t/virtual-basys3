"""Event-driven, zero-delay simulation of reconstructed Xilinx primitive netlists.

Input is Yosys JSON used only as a structural Verilog reader. There is no synthesis
or route inference here. Unknown bits are represented by None and remain visible.
"""

import json
from collections import defaultdict, deque
from pathlib import Path


class UnsupportedDesign(ValueError):
    pass


def parameter(cell, name, default=0):
    value = cell.get("parameters", {}).get(name)
    if value is None:
        return default
    return value if isinstance(value, int) else int(value, 2)


def invert(value, flag):
    return None if value is None else value ^ flag


class Simulator:
    def __init__(self, module):
        self.module = module
        self.cells = module.get("cells", {})
        self.ports = module.get("ports", {})
        self.values = {"0": 0, "1": 1, "x": None, "z": None}
        self.consumers = defaultdict(set)
        self.queue = deque()
        self.queued = set()
        self.flops = []
        self.clocks = {}
        self.transitions = 0
        self.steps = 0
        self.input_pins = {bit for port in self.ports.values() if port["direction"] == "input"
                           for bit in port["bits"]}
        drivers = {}
        supported = {"LUT" + str(i) for i in range(1, 7)} | {
            "LUT6_2", "FDRE", "FDSE", "FDCE", "FDPE", "IBUF", "OBUF",
            "BUFG", "BUFGCTRL", "MUXF7", "MUXF8", "CARRY4", "INV", "VCC", "GND"}
        for name, cell in self.cells.items():
            kind = cell["type"]
            if kind not in supported:
                raise UnsupportedDesign(f"Unsupported primitive {kind}: {name}")
            for port, bits in cell["connections"].items():
                direction = cell["port_directions"][port]
                for bit in bits:
                    self.values.setdefault(bit, None)
                    if direction == "input":
                        self.consumers[bit].add(name)
                    elif direction == "output":
                        if bit in drivers or bit in self.input_pins:
                            raise UnsupportedDesign(f"Multiple drivers on net {bit}")
                        drivers[bit] = name
            if kind.startswith("FD"):
                self.flops.append(name)
                self.clocks[name] = None
                self.set_value(cell["connections"]["Q"][0], parameter(cell, "INIT"))
            if kind == "BUFGCTRL":
                for port in ("CE0", "CE1", "S0", "S1", "IGNORE0", "IGNORE1"):
                    if any(isinstance(bit, int) for bit in cell["connections"][port]):
                        raise UnsupportedDesign("Only statically selected BUFGCTRL clocks are supported")
            self.enqueue(name)
        self.settle()

    @classmethod
    def load(cls, path, top="top"):
        return cls(json.loads(Path(path).read_text())["modules"][top])

    def enqueue(self, name):
        if name not in self.queued:
            self.queue.append(name)
            self.queued.add(name)

    def set_value(self, bit, value):
        if isinstance(bit, str):
            if self.values[bit] != value:
                raise UnsupportedDesign("Cell drives a conflicting constant")
            return
        if self.values.get(bit) != value:
            self.values[bit] = value
            self.transitions += 1
            for name in self.consumers[bit]:
                self.enqueue(name)

    def pins(self, cell, port):
        return [self.values.get(bit) for bit in cell["connections"][port]]

    def pin(self, cell, port):
        return self.pins(cell, port)[0]

    def output(self, cell, port, values):
        if not isinstance(values, list):
            values = [values]
        bits = cell["connections"][port]
        if len(bits) != len(values):
            raise ValueError(f"Width mismatch on {port}")
        for bit, value in zip(bits, values):
            self.set_value(bit, value)

    @staticmethod
    def lut(init, inputs):
        # If all possible values for X inputs agree, output is still known.
        indices = [0]
        for index, bit in enumerate(inputs):
            indices = [value | (choice << index) for value in indices
                       for choice in ((0, 1) if bit is None else (bit,))]
        values = {(init >> index) & 1 for index in indices}
        return next(iter(values)) if len(values) == 1 else None

    def evaluate(self, cell):
        kind = cell["type"]
        if kind.startswith("FD"):
            return
        if kind.startswith("LUT"):
            width = 6 if kind == "LUT6_2" else int(kind[-1])
            inputs = [self.pin(cell, f"I{i}") for i in range(width)]
            init = parameter(cell, "INIT")
            self.output(cell, "O6" if kind == "LUT6_2" else "O", self.lut(init, inputs))
            if kind == "LUT6_2":
                self.output(cell, "O5", self.lut(init, inputs[:5]))
        elif kind in ("IBUF", "OBUF", "BUFG", "INV"):
            self.output(cell, "O", invert(self.pin(cell, "I"), int(kind == "INV")))
        elif kind in ("VCC", "GND"):
            self.output(cell, "P" if kind == "VCC" else "G", int(kind == "VCC"))
        elif kind in ("MUXF7", "MUXF8"):
            a, b, select = (self.pin(cell, p) for p in ("I0", "I1", "S"))
            self.output(cell, "O", (b if select else a) if select is not None else (a if a == b else None))
        elif kind == "CARRY4":
            ci, cyinit = self.pin(cell, "CI"), self.pin(cell, "CYINIT")
            carry = 1 if 1 in (ci, cyinit) else (None if None in (ci, cyinit) else 0)
            outputs, carries = [], []
            for select, data in zip(self.pins(cell, "S"), self.pins(cell, "DI")):
                outputs.append(None if None in (select, carry) else select ^ carry)
                carry = (carry if select else data) if select is not None else (carry if carry == data else None)
                carries.append(carry)
            self.output(cell, "O", outputs)
            self.output(cell, "CO", carries)
        elif kind == "BUFGCTRL":
            selected = []
            for i in range(2):
                ce = invert(self.pin(cell, f"CE{i}"), parameter(cell, f"IS_CE{i}_INVERTED"))
                select = invert(self.pin(cell, f"S{i}"), parameter(cell, f"IS_S{i}_INVERTED"))
                if ce and select:
                    selected.append(self.pin(cell, f"I{i}"))
            self.output(cell, "O", selected[0] if len(selected) == 1 else
                        (parameter(cell, "INIT_OUT") if not selected else None))

    def settle_combinational(self):
        count = 0
        while self.queue:
            name = self.queue.popleft()
            self.queued.remove(name)
            self.evaluate(self.cells[name])
            count += 1
            if count > max(10000, len(self.cells) * 100):
                raise UnsupportedDesign("Combinational logic did not settle")

    def settle(self):
        # Propagate clocks, sample D simultaneously, then commit all Q updates.
        for _ in range(100):
            self.settle_combinational()
            changes = []
            for name in self.flops:
                cell = self.cells[name]
                clock = invert(self.pin(cell, "C"), parameter(cell, "IS_C_INVERTED"))
                edge = self.clocks[name] == 0 and clock == 1
                self.clocks[name] = clock
                kind = cell["type"]
                control_port = {"FDRE": "R", "FDSE": "S", "FDCE": "CLR", "FDPE": "PRE"}[kind]
                control = invert(self.pin(cell, control_port), parameter(cell, f"IS_{control_port}_INVERTED"))
                asynchronous = kind in ("FDCE", "FDPE")
                bit = cell["connections"]["Q"][0]
                value = self.values[bit]
                if (edge or asynchronous) and control == 1:
                    value = int(kind in ("FDSE", "FDPE"))
                elif edge:
                    ce = self.pin(cell, "CE")
                    if control is None or ce is None:
                        value = None
                    elif ce:
                        value = invert(self.pin(cell, "D"), parameter(cell, "IS_D_INVERTED"))
                if value != self.values[bit]:
                    changes.append((bit, value))
            if not changes:
                return
            for bit, value in changes:
                self.set_value(bit, value)
        raise UnsupportedDesign("Sequential delta-cycle limit exceeded")

    def drive(self, ports):
        for name, value in ports.items():
            port = self.ports[name]
            if port["direction"] != "input":
                raise ValueError(f"{name} is not an input")
            if value is not None and not 0 <= value < (1 << len(port["bits"])):
                raise ValueError(f"Input {name} value exceeds port width")
            for index, bit in enumerate(port["bits"]):
                self.set_value(bit, None if value is None else (value >> index) & 1)
        self.settle()

    def read(self, name):
        bits = [self.values.get(bit) for bit in self.ports[name]["bits"]]
        return None if None in bits else sum(bit << index for index, bit in enumerate(bits))

    def cycle(self, clock):
        self.drive({clock: 0})
        self.drive({clock: 1})
        self.steps += 1

    def snapshot(self):
        return {"cycles": self.steps, "transitions": self.transitions,
                "ports": {name: self.read(name) for name in self.ports}}
