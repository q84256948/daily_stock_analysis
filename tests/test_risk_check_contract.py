# -*- coding: utf-8 -*-
"""
Tests for the three-layer defense example in src/schemas/risk_check.py.
"""

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from icontract import ViolationError
from pydantic import ValidationError

from src.schemas.risk_check import RiskCheckRequest, RiskCheckResult, check_risk


class TestRiskCheckPydanticLayer(unittest.TestCase):
    def test_valid_request_passes(self):
        req = RiskCheckRequest(
            user_id="a" * 32,
            symbol="BTC-USDT",
            side="BUY",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            leverage=Decimal("10"),
            account_balance=Decimal("100000"),
        )
        self.assertEqual(req.symbol, "BTC-USDT")
        self.assertEqual(req.notional, Decimal("5000"))

    def test_invalid_symbol_format_rejected(self):
        with self.assertRaises(ValidationError):
            RiskCheckRequest(
                user_id="a" * 32,
                symbol="BTCUSDT",
                side="BUY",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                account_balance=Decimal("100000"),
            )

    def test_negative_price_rejected(self):
        with self.assertRaises(ValidationError):
            RiskCheckRequest(
                user_id="a" * 32,
                symbol="BTC-USDT",
                side="BUY",
                price=Decimal("-1"),
                quantity=Decimal("0.1"),
                account_balance=Decimal("100000"),
            )

    def test_invalid_user_id_pattern_rejected(self):
        with self.assertRaises(ValidationError):
            RiskCheckRequest(
                user_id="not-hex",
                symbol="BTC-USDT",
                side="BUY",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                account_balance=Decimal("100000"),
            )


class TestRiskCheckIcontractLayer(unittest.TestCase):
    def test_check_risk_passes_with_sufficient_margin(self):
        req = RiskCheckRequest(
            user_id="a" * 32,
            symbol="BTC-USDT",
            side="BUY",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            leverage=Decimal("10"),
            account_balance=Decimal("100000"),
        )
        result = check_risk(req)
        self.assertTrue(result.passed)
        self.assertEqual(result.margin_required, Decimal("500"))
        self.assertEqual(result.margin_ratio, Decimal("0.005"))

    def test_check_risk_fails_when_margin_ratio_too_low(self):
        req = RiskCheckRequest(
            user_id="a" * 32,
            symbol="BTC-USDT",
            side="BUY",
            price=Decimal("50000"),
            quantity=Decimal("10"),
            leverage=Decimal("100"),
            account_balance=Decimal("100"),
        )
        result = check_risk(req)
        self.assertFalse(result.passed)
        self.assertIn("10%", result.reject_reason or "")
        self.assertEqual(result.margin_ratio, Decimal("50"))

    def test_result_model_validates_output(self):
        with self.assertRaises(ValidationError):
            RiskCheckResult(
                passed=True,
                margin_required=Decimal("0"),
                margin_ratio=Decimal("-1"),
            )


if __name__ == "__main__":
    unittest.main()
