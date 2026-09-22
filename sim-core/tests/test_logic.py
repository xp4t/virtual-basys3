import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic import Simulator, UnsupportedDesign
from pins import parse_xdc


def flop(q, d, clk=2):
    return {"type":"FDRE", "parameters":{"INIT":"0"},
            "connections":{"Q":[q],"D":[d],"C":[clk],"CE":[3],"R":[4]},
            "port_directions":{"Q":"output","D":"input","C":"input","CE":"input","R":"input"}}


class LogicTests(unittest.TestCase):
    def chain(self):
        return Simulator({"ports":{"clk":{"direction":"input","bits":[2]},
                                   "enable":{"direction":"input","bits":[3]},
                                   "reset":{"direction":"input","bits":[4]},
                                   "data":{"direction":"input","bits":[5]},
                                   "out":{"direction":"output","bits":[7]}},
                          "cells":{"a":flop(6,5),"b":flop(7,6)}})

    def test_all_flops_sample_before_any_q_updates(self):
        simulator = self.chain()
        simulator.drive({"clk":0,"enable":1,"reset":0,"data":1})
        simulator.cycle("clk")
        self.assertEqual(simulator.read("out"),0)
        simulator.cycle("clk")
        self.assertEqual(simulator.read("out"),1)

    def test_reset_takes_priority_over_disabled_enable(self):
        simulator = self.chain()
        simulator.drive({"clk":0,"enable":1,"reset":0,"data":1})
        simulator.cycle("clk"); simulator.cycle("clk")
        simulator.drive({"enable":0,"reset":1})
        simulator.cycle("clk")
        self.assertEqual(simulator.read("out"),0)

    def test_lut_unknown_input_resolution(self):
        self.assertEqual(Simulator.lut(0,[None,None]),0)
        self.assertEqual(Simulator.lut(0xF,[None,None]),1)
        self.assertIsNone(Simulator.lut(0x8,[1,None]))
        self.assertEqual(Simulator.lut(0x8,[0,None]),0)

    def test_unsupported_resources_fail_explicitly(self):
        with self.assertRaises(UnsupportedDesign):
            Simulator({"cells":{"dsp":{"type":"DSP48E1"}}})

    def test_digilent_master_pin_names(self):
        path = Path(__file__).resolve().parents[2] / "references/Basys-3-Master.xdc"
        pins = parse_xdc(path,include_commented=True)
        self.assertEqual([pins[name] for name in ("clk","sw[0]","led[0]","btnC")],
                         ["W5","V17","U16","U18"])
        self.assertTrue(all(f"sw[{i}]" in pins and f"led[{i}]" in pins for i in range(16)))
        self.assertEqual(parse_xdc(path),{})


if __name__ == "__main__":
    unittest.main()
