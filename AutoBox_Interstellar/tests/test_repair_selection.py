"""Confere os tres destinos de reparo do print de morte enviado pelo usuario."""

import ast
import unittest
from pathlib import Path


source = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
module = ast.parse(source.read_text(encoding="utf-8"))
function = next(node for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == "repair_click_points")
namespace = {"REPAIR_COSTS": {"base": 0, "portal": 250, "same_place": 500}}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
repair_click_points = namespace["repair_click_points"]


class RepairSelectionTests(unittest.TestCase):
    def setUp(self):
        # Contorno aproximado da caixa central do Screenshot_37.png.
        self.panel = (703, 300, 469, 357)

    def test_three_options_left_to_right(self):
        base, ok1 = repair_click_points(self.panel, "base")
        portal, ok2 = repair_click_points(self.panel, "portal")
        same, ok3 = repair_click_points(self.panel, "same_place")
        self.assertTrue(base[0] < portal[0] < same[0])
        self.assertTrue(450 <= base[1] <= 490)
        self.assertEqual(base[1], portal[1])
        self.assertEqual(portal[1], same[1])
        self.assertEqual(ok1, ok2)
        self.assertEqual(ok2, ok3)
        self.assertTrue(605 <= ok1[1] <= 640)

    def test_invalid_option(self):
        with self.assertRaises(ValueError):
            repair_click_points(self.panel, "unknown")


if __name__ == "__main__":
    unittest.main()
