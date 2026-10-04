"""Tests for the CXL001 frame parser. No Home Assistant dependency."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_PARSER = Path(__file__).resolve().parents[1] / "custom_components" / "cxl001" / "parser.py"
_SPEC = importlib.util.spec_from_file_location("cxl001_parser", _PARSER)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

IgnoredSample = _MODULE.IgnoredSample
ProbeOffline = _MODULE.ProbeOffline
TemperatureSample = _MODULE.TemperatureSample
parse_firmware = _MODULE.parse_firmware
parse_temperature_notify = _MODULE.parse_temperature_notify


def _frame(text: str) -> bytes:
    return text.encode("ascii")


class ParserTests(unittest.TestCase):
    def test_tip_frame_from_capture(self) -> None:
        raw = bytes.fromhex("30303a6162626364643032383630643a5832352e3926")
        parsed = parse_temperature_notify(raw)
        self.assertEqual(
            parsed,
            TemperatureSample("00", "abbcdd02860d", "X", 25.9),
        )

    def test_second_internal_frame(self) -> None:
        parsed = parse_temperature_notify(_frame("00:abbcdd02860d:W25.2&"))
        self.assertEqual(parsed, TemperatureSample("00", "abbcdd02860d", "W", 25.2))

    def test_number_is_celsius_not_scaled_and_letter_is_not_ambient(self) -> None:
        parsed = parse_temperature_notify(_frame("00:abbcdd02860d:X30.6&"))
        assert isinstance(parsed, TemperatureSample)
        self.assertEqual(parsed.celsius, 30.6)
        self.assertNotEqual(parsed.celsius, 88)

    def test_y_and_z_are_temperatures_with_no_assigned_role(self) -> None:
        y_frame = parse_temperature_notify(_frame("00:abbcdd02860d:Y28.4&"))
        z_frame = parse_temperature_notify(_frame("00:abbcdd02860d:Z28.1&"))
        self.assertEqual(y_frame, TemperatureSample("00", "abbcdd02860d", "Y", 28.4))
        self.assertEqual(z_frame, TemperatureSample("00", "abbcdd02860d", "Z", 28.1))

    def test_offline_frame(self) -> None:
        raw = bytes.fromhex("30303a6162626364643032383630643a3030303026")
        parsed = parse_temperature_notify(raw)
        self.assertEqual(parsed, ProbeOffline("00", "abbcdd02860d"))

    def test_empty_third_field_is_offline(self) -> None:
        parsed = parse_temperature_notify(_frame("00:abbcdd02860d:&"))
        self.assertIsInstance(parsed, ProbeOffline)

    def test_999_is_not_zero_celsius(self) -> None:
        parsed = parse_temperature_notify(_frame("00:abbcdd02860d:X999&"))
        self.assertEqual(parsed, IgnoredSample("00", "abbcdd02860d", "X"))

    def test_negative_and_longer_number(self) -> None:
        parsed = parse_temperature_notify(_frame("00:abbcdd02860d:X-1.2&"))
        self.assertEqual(parsed, TemperatureSample("00", "abbcdd02860d", "X", -1.2))
        parsed = parse_temperature_notify(_frame("00:abbcdd02860d:W100.0&"))
        self.assertEqual(parsed, TemperatureSample("00", "abbcdd02860d", "W", 100.0))

    def test_uppercase_probe_id(self) -> None:
        parsed = parse_temperature_notify(_frame("00:ABBCDD02860D:x31.8&"))
        self.assertEqual(parsed, TemperatureSample("00", "abbcdd02860d", "X", 31.8))

    def test_rejects_garbage(self) -> None:
        self.assertIsNone(parse_temperature_notify(b"\x00\x80"))
        self.assertIsNone(parse_temperature_notify(_frame("nope")))
        self.assertIsNone(parse_temperature_notify(_frame("00:short:X1.0&")))
        self.assertIsNone(parse_temperature_notify(_frame("00:abbcdd02860d:Xabc&")))

    def test_firmware(self) -> None:
        raw = bytes.fromhex("0380") + b"app-1.0.7-20240326.1100"
        self.assertEqual(parse_firmware(raw), "app-1.0.7-20240326.1100")
        self.assertIsNone(parse_firmware(bytes.fromhex("0080")))
        self.assertIsNone(parse_firmware(b"\x03\x80not-app"))


if __name__ == "__main__":
    unittest.main()
