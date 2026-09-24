"""Live board state and background configuration-to-netlist conversion."""

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from logic import Simulator
from pins import BoardPins
from analyzer import LogicAnalyzer

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("runtime")


class BoardRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="decode")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.generation = 0
        self.status = "unconfigured"
        self.error = None
        self.board = None
        self.analyzer = None
        self.running = False
        self.rate = 32
        self.switches = [0] * 16
        self.buttons = {name: 0 for name in ("btnC", "btnU", "btnD", "btnL", "btnR")}
        self.connected = lambda: False
        self.endpoint = "127.0.0.1:2542"
        self.source_hash = None
        self.thread.start()

    def reset(self):
        with self.lock:
            self.generation += 1
            self.board = None
            self.analyzer = None
            self.running = False
            self.status = "programming"
            self.error = None

    def programmed(self, data):
        with self.lock:
            self.generation += 1
            generation = self.generation
            self.status = "decoding"
        self.executor.submit(self.load_program, bytes(data), generation)

    def load_program(self, data, generation):
        try:
            from pipeline import convert
            digest = hashlib.sha256(data).hexdigest()
            output = ROOT / "build/programs" / digest
            output.mkdir(parents=True, exist_ok=True)
            capture = output / "configuration.bin"
            capture.write_bytes(data)
            netlist = output / "netlist.json"
            if not netlist.exists():
                netlist = convert(capture, output)
            report = json.loads((output / "design.decode.json").read_text())
            if report["unknown_bits"] or report["missing_tile_types"] or not report["complete"]:
                raise ValueError("Configuration has unknown bits or incomplete database coverage; see decode report")
            simulator = Simulator.load(netlist)
            board = BoardPins(simulator,
                              ROOT / "third_party/prjxray-db/artix7/xc7a35tcpg236-1/package_pins.csv",
                              ROOT / "references/Basys-3-Master.xdc")
            if "clk" not in board.ports:
                raise ValueError("This runtime requires the Basys3 W5 clock input")
            with self.lock:
                if generation != self.generation:
                    return
                self.board = board
                simulator.drive({name: 0 for name, port in simulator.ports.items() if port["direction"] == "input"})
                self.apply_inputs()
                self.analyzer = LogicAnalyzer(board)
                self.status = "ready"
                self.error = None
                self.source_hash = digest
                self.running = True
            LOG.info("Simulation ready: %d primitives, %d flip-flops", len(simulator.cells), len(simulator.flops))
        except Exception as error:
            LOG.exception("Unable to simulate configuration")
            with self.lock:
                if generation == self.generation:
                    self.status = "error"
                    self.error = str(error)
                    self.running = False
                    self.board = None
                    self.analyzer = None

    def apply_inputs(self):
        if self.board:
            self.board.drive({**{f"sw[{i}]": value for i, value in enumerate(self.switches)}, **self.buttons})

    def control(self, command):
        if not isinstance(command, dict):
            raise ValueError("Control must be an object")
        allowed = {"switch", "switches", "button", "value", "running", "rate", "step"}
        if set(command) - allowed:
            raise ValueError("Unknown control")
        with self.lock:
            if "switches" in command:
                word = command["switches"]
                if "switch" in command or type(word) is not int or not 0 <= word <= 0xFFFF:
                    raise ValueError("Switches must be a 16-bit word, without an individual switch update")
                self.switches = [(word >> index) & 1 for index in range(16)]
            if "switch" in command:
                index = command["switch"]
                if type(index) is not int or not 0 <= index < 16 or type(command.get("value")) is not bool:
                    raise ValueError("Switch requires index 0–15 and boolean value")
                self.switches[index] = int(command["value"])
            if "button" in command:
                name = command["button"]
                if name not in self.buttons or type(command.get("value")) is not bool:
                    raise ValueError("Unknown button or invalid value")
                self.buttons[name] = int(command["value"])
            if "rate" in command:
                value = command["rate"]
                if type(value) not in (int, float) or not 1 <= value <= 10000:
                    raise ValueError("Clock rate must be 1–10000 Hz")
                self.rate = value
            if "running" in command:
                if type(command["running"]) is not bool:
                    raise ValueError("Running must be boolean")
                self.running = command["running"] and self.status == "ready"
            self.apply_inputs()
            if "step" in command:
                if type(command["step"]) is not int or not 1 <= command["step"] <= 1000:
                    raise ValueError("Step count must be 1–1000")
                if not self.board or self.status != "ready":
                    raise ValueError("No simulated design loaded")
                self.running = False
                for _ in range(command["step"]):
                    self.board.cycle()
                    if self.analyzer:
                        self.analyzer.sample()
            return self.snapshot()

    def logic_catalog(self):
        with self.lock:
            return self.analyzer.probe_list() if self.analyzer else []

    def logic_snapshot(self):
        with self.lock:
            return self.analyzer.state() if self.analyzer else None

    def logic_control(self, command):
        if not isinstance(command, dict) or set(command) - {"action", "probes", "depth", "trigger"}:
            raise ValueError("Invalid analyzer command")
        with self.lock:
            if not self.analyzer:
                raise ValueError("Program a supported design before using the analyzer")
            action = command.get("action")
            if action == "configure":
                self.analyzer.configure(command.get("probes"), command.get("depth"),
                                        command.get("trigger"))
            elif action == "arm" and set(command) == {"action"}:
                self.analyzer.arm()
            elif action == "stop" and set(command) == {"action"}:
                self.analyzer.stop()
            else:
                raise ValueError("Invalid analyzer action")
            return self.analyzer.state()

    def logic_csv(self):
        with self.lock:
            if not self.analyzer:
                raise ValueError("No analyzer capture available")
            return self.analyzer.csv_text()

    def snapshot(self):
        with self.lock:
            return {"status": self.status, "error": self.error, "running": self.running,
                    "rate": self.rate, "switches": list(self.switches), "buttons": dict(self.buttons),
                    "leds": [self.board.read(f"led[{i}]") if self.board else None for i in range(16)],
                    "cycles": self.board.simulator.steps if self.board else 0,
                    "cells": len(self.board.simulator.cells) if self.board else 0,
                    "xvc_connected": self.connected(), "endpoint": self.endpoint,
                    "part": "xc7a35t", "sha256": self.source_hash}

    def run(self):
        previous = time.monotonic()
        pending = 0.0
        while not self.stop_event.wait(0.01):
            now = time.monotonic()
            elapsed, previous = now - previous, now
            with self.lock:
                if not self.running or not self.board:
                    pending = 0
                    continue
                pending += elapsed * self.rate
                count = min(int(pending), 1000)
                pending -= count
                try:
                    for _ in range(count):
                        self.board.cycle()
                        if self.analyzer:
                            self.analyzer.sample()
                except Exception as error:
                    self.status = "error"
                    self.error = str(error)
                    self.running = False

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        self.executor.shutdown(wait=False, cancel_futures=True)
