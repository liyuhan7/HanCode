from __future__ import annotations

import sys
import unittest

if "pytest" in sys.modules:
    import pytest

    pytest.skip("demo fixture is executed only by its local unittest runner", allow_module_level=True)

from src.calculator import add


class CalculatorTests(unittest.TestCase):
    def test_add_returns_the_sum_of_two_integers(self) -> None:
        self.assertEqual(add(1, 2), 3)
