"""Testes do detector sem precisar abrir o jogo ou instalar automouse."""

import ast
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


source = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
module = ast.parse(source.read_text(encoding="utf-8"))
function = next(node for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == "new_reward_message")
namespace = {"np": np}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
new_reward_message = namespace["new_reward_message"]


def notification(texts):
    image = Image.new("RGB", (300, 120), "black")
    draw = ImageDraw.Draw(image)
    for i, text in enumerate(texts):
        draw.text((4, 5 + 14 * i), text, fill=(190, 190, 190))
    return np.asarray(image)[:, :, ::-1].copy()


class RewardNotificationTests(unittest.TestCase):
    def test_new_receipt_after_previous(self):
        old = notification(["You received 60 Uridium"])
        new = notification(["You received 60 Uridium", "You received 20 SAB-50"])
        self.assertTrue(new_reward_message(old, new))

    def test_persistent_old_receipt_does_not_repeat(self):
        old = notification(["You received 60 Uridium"])
        self.assertFalse(new_reward_message(old, old.copy()))

    def test_disappearing_message_is_not_new_reward(self):
        old = notification(["You received 60 Uridium"])
        self.assertFalse(new_reward_message(old, notification([])))

    def test_small_bright_particles_are_ignored(self):
        old = notification(["You received 60 Uridium"])
        after = old.copy()
        after[70:73, 65:68] = 255
        self.assertFalse(new_reward_message(old, after))

    def test_different_image_size_is_rejected(self):
        old = notification([])
        self.assertFalse(new_reward_message(old, old[:, :100]))


if __name__ == "__main__":
    unittest.main()
