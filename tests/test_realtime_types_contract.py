# -*- coding: utf-8 -*-
"""
Tests for icontract decorators on data_provider.realtime_types helpers.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from icontract import ViolationError

from data_provider.realtime_types import ChipDistribution, safe_float, safe_int


class TestSafeFloatContract(unittest.TestCase):
    def test_returns_float_for_numeric_string(self):
        self.assertEqual(safe_float("123.45"), 123.45)

    def test_returns_default_for_invalid_input(self):
        self.assertIsNone(safe_float("not-a-number"))

    def test_returns_default_for_none(self):
        self.assertIsNone(safe_float(None))

    def test_violates_when_default_is_not_numeric(self):
        with self.assertRaises(ViolationError):
            safe_float("123", default="invalid")  # type: ignore


class TestSafeIntContract(unittest.TestCase):
    def test_returns_int_for_numeric_string(self):
        self.assertEqual(safe_int("123.0"), 123)

    def test_returns_default_for_invalid_input(self):
        self.assertIsNone(safe_int("not-a-number"))

    def test_violates_when_default_is_not_int(self):
        with self.assertRaises(ViolationError):
            safe_int("123", default=1.5)  # type: ignore


class TestChipDistributionContract(unittest.TestCase):
    def test_get_chip_status_with_valid_state(self):
        chip = ChipDistribution(
            code="600519",
            profit_ratio=0.5,
            avg_cost=100.0,
            concentration_90=0.1,
        )
        status = chip.get_chip_status(current_price=110.0)
        self.assertGreater(len(status), 0)

    def test_violates_when_profit_ratio_out_of_range(self):
        chip = ChipDistribution(
            code="600519",
            profit_ratio=1.5,
            avg_cost=100.0,
            concentration_90=0.1,
        )
        with self.assertRaises(ViolationError):
            chip.get_chip_status(current_price=110.0)

    def test_violates_when_current_price_negative(self):
        chip = ChipDistribution(
            code="600519",
            profit_ratio=0.5,
            avg_cost=100.0,
            concentration_90=0.1,
        )
        with self.assertRaises(ViolationError):
            chip.get_chip_status(current_price=-1.0)


if __name__ == "__main__":
    unittest.main()
