"""Local clocked logic capture for the bitstream-backed board simulator.

This samples reconstructed physical nets; it does not impersonate a Vivado ILA
core or infer RTL names from an LTX file.
"""

import csv
import io
from collections import deque


MAX_PROBES = 16
MAX_DEPTH = 4096


class LogicAnalyzer:
    def __init__(self, board):
        self.simulator = board.simulator
        self.catalog = {}
        for name, physical in sorted(board.ports.items()):
            port = self.simulator.ports[physical]
            if len(port["bits"]) == 1:
                self._add(f"pin:{name}", name.upper(), "Board input" if
                          port["direction"] == "input" else "Board output",
                          port["bits"][0])
        for name, cell in sorted(self.simulator.cells.items()):
            if cell["type"].startswith("FD"):
                self._add(f"reg:{name}", name, "Register Q", cell["connections"]["Q"][0])
        for name, net in sorted(self.simulator.module.get("netnames", {}).items()):
            if len(net["bits"]) == 1:
                self._add(f"net:{name}", name, "Physical net", net["bits"][0])
        defaults = [f"pin:led[{i}]" for i in range(8) if f"pin:led[{i}]" in self.catalog]
        if not defaults:
            defaults = list(self.catalog)[:min(8, len(self.catalog))]
        if not defaults:
            raise ValueError("No observable one-bit signals in reconstructed design")
        self.configure(defaults, 256, {"mode": "immediate"})

    def _add(self, identifier, label, group, bit):
        if isinstance(bit, int):
            self.catalog[identifier] = {"id": identifier, "label": label,
                                        "group": group, "bit": bit}

    def configure(self, probes, depth, trigger):
        if (not isinstance(probes, list) or not 1 <= len(probes) <= MAX_PROBES or
                any(not isinstance(item, str) or item not in self.catalog for item in probes) or
                len(set(probes)) != len(probes)):
            raise ValueError(f"Choose 1–{MAX_PROBES} distinct available probes")
        if type(depth) is not int or not 16 <= depth <= MAX_DEPTH:
            raise ValueError(f"Capture depth must be 16–{MAX_DEPTH} samples")
        if not isinstance(trigger, dict) or set(trigger) - {"mode", "probe"}:
            raise ValueError("Invalid trigger")
        mode = trigger.get("mode")
        if mode not in ("immediate", "rising", "falling", "high", "low"):
            raise ValueError("Invalid trigger mode")
        probe = trigger.get("probe")
        if mode != "immediate" and probe not in probes:
            raise ValueError("Trigger probe must be one of the captured probes")
        self.probes = list(probes)
        self.depth = depth
        self.trigger = {"mode": mode, "probe": probe if mode != "immediate" else None}
        self.phase = "idle"
        self.samples = []
        self.trigger_index = None
        self.previous = None
        self.pretrigger = deque(maxlen=max(1, depth // 4))

    def arm(self):
        self.phase = "waiting"
        self.samples = []
        self.trigger_index = None
        self.previous = None
        self.pretrigger.clear()

    def stop(self):
        if self.phase in ("waiting", "capturing"):
            self.phase = "stopped"

    def _triggered(self, values):
        mode = self.trigger["mode"]
        if mode == "immediate":
            return True
        index = self.probes.index(self.trigger["probe"])
        value = values[index]
        if mode == "high":
            return value == 1
        if mode == "low":
            return value == 0
        prior = self.previous[index] if self.previous is not None else None
        return prior == (0 if mode == "rising" else 1) and value == (1 if mode == "rising" else 0)

    def sample(self):
        if self.phase not in ("waiting", "capturing"):
            return
        values = [self.simulator.values.get(self.catalog[probe]["bit"])
                  for probe in self.probes]
        cycle = self.simulator.steps
        if self.phase == "waiting":
            if self._triggered(values):
                self.samples = list(self.pretrigger)
                self.trigger_index = len(self.samples)
                self.phase = "capturing"
            else:
                self.pretrigger.append({"cycle": cycle, "values": values})
        if self.phase == "capturing":
            self.samples.append({"cycle": cycle, "values": values})
            if len(self.samples) >= self.depth:
                self.phase = "complete"
        self.previous = values

    def probe_list(self):
        return [{key: item[key] for key in ("id", "label", "group")}
                for item in self.catalog.values()]

    def state(self):
        # HTTP serializes this after the runtime lock is released. Return a
        # stable copy while the simulation thread continues appending samples.
        samples = [{"cycle": item["cycle"], "values": list(item["values"])}
                   for item in self.samples]
        return {"phase": self.phase, "probes": list(self.probes), "depth": self.depth,
                "trigger": dict(self.trigger), "trigger_index": self.trigger_index,
                "samples": samples, "max_probes": MAX_PROBES}

    def csv_text(self):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["cycle"] + [self.catalog[probe]["label"] for probe in self.probes])
        for sample in self.samples:
            writer.writerow([sample["cycle"]] +
                            ["X" if value is None else value for value in sample["values"]])
        return output.getvalue()
