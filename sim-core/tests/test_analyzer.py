import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyzer import LogicAnalyzer
from logic import Simulator
from runtime import BoardRuntime


class TestLogicAnalyzer(unittest.TestCase):
    def make_board(self):
        module = {
            "ports": {"clk": {"direction": "input", "bits": [1]},
                      "sw": {"direction": "input", "bits": [2]},
                      "led": {"direction": "output", "bits": [3]}},
            "netnames": {"physical_register_q": {"bits": [3]}},
            "cells": {"reg0": {"type": "FDRE", "parameters": {"INIT": "0"},
                               "connections": {"C": [1], "D": [2], "Q": [3],
                                               "CE": ["1"], "R": ["0"]},
                               "port_directions": {"C": "input", "D": "input",
                                                   "Q": "output", "CE": "input", "R": "input"}}},
        }
        simulator = Simulator(module)
        simulator.drive({"clk": 0, "sw": 0})

        class Board:
            ports = {"sw[0]": "sw", "led[0]": "led"}
        board = Board()
        board.simulator = simulator
        return board

    def test_rising_trigger_captures_real_register_transitions(self):
        board = self.make_board()
        analyzer = LogicAnalyzer(board)
        self.assertIn("reg:reg0", {probe["id"] for probe in analyzer.probe_list()})
        self.assertIn("net:physical_register_q", analyzer.catalog)
        analyzer.configure(["pin:led[0]", "pin:sw[0]"], 16,
                           {"mode": "rising", "probe": "pin:led[0]"})
        analyzer.arm()
        board.simulator.cycle("clk"); analyzer.sample()
        self.assertEqual(analyzer.state()["phase"], "waiting")
        board.simulator.drive({"sw": 1})
        board.simulator.cycle("clk"); analyzer.sample()
        state = analyzer.state()
        self.assertEqual(state["phase"], "capturing")
        self.assertEqual(state["samples"][state["trigger_index"]]["values"], [1, 1])
        frozen = analyzer.state()
        for _ in range(14):
            board.simulator.cycle("clk"); analyzer.sample()
        self.assertEqual(len(frozen["samples"]), 2)
        self.assertEqual(analyzer.state()["phase"], "complete")
        self.assertEqual(len(analyzer.state()["samples"]), 16)
        self.assertIn("cycle,LED[0],SW[0]", analyzer.csv_text())

    def test_invalid_configuration_and_vio_bus_word(self):
        analyzer = LogicAnalyzer(self.make_board())
        with self.assertRaisesRegex(ValueError, "Trigger probe"):
            analyzer.configure(["pin:led[0]"], 32,
                               {"mode": "high", "probe": "pin:sw[0]"})
        runtime = BoardRuntime()
        try:
            state = runtime.control({"switches": 0xA501})
            self.assertEqual(sum(bit << index for index, bit in enumerate(state["switches"])), 0xA501)
            with self.assertRaises(ValueError):
                runtime.control({"switches": 0x10000})
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
