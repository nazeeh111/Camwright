from fractions import Fraction
import unittest
from unittest.mock import patch

from camwright import geometry as cam


class NumericInputTests(unittest.TestCase):
    def test_unsupported_and_out_of_range_strings_never_reach_fraction(self):
        calls = []

        def conversion_guard(*args, **kwargs):
            calls.append(args)
            raise ValueError("conversion should not be attempted")

        invalid = ["1e100000", "1e-100000", "1E999999999999999999999", "1e-999999999999999999999",
                   "1/2", "1_000", " 1", "1 ", "١", ".", "+", "--1", "inf", "NaN",
                   "100001", "100000.000000000001", "0.0000000000001",
                   "12345678901234567890123456789012", "0"*33]
        with patch.object(cam, "F", conversion_guard):
            for value in invalid:
                with self.assertRaises(ValueError):
                    cam.rational(value, "input")
        self.assertEqual([], calls, "invalid input must be rejected before Fraction construction")

    def test_fixed_decimal_values_remain_exact(self):
        for value, expected in [(25, Fraction(25)), (-100000, Fraction(-100000)),
                                ("25", Fraction(25)), ("+.500", Fraction(1,2)),
                                ("1.", Fraction(1)), ("00025.100", Fraction(251,10)),
                                ("-0.000000000001", Fraction(-1,10**12)),
                                ("0.1234567890120", Fraction(123456789012,10**12)),
                                ("1.000000000000000000000000000000", Fraction(1)),
                                ("100000.0000000000", Fraction(100000)),
                                ("-0", Fraction(0))]:
            self.assertEqual(expected, cam.rational(value, "input"))

    def test_nonstring_noninteger_and_oversized_integers_reject_before_conversion(self):
        calls = []

        def conversion_guard(*args, **kwargs):
            calls.append(args)
            raise ValueError("conversion should not be attempted")

        with patch.object(cam, "F", conversion_guard):
            for value in [True, False, 0.5, None, [], {}, 100001, -(10**100)]:
                with self.assertRaises(ValueError):
                    cam.rational(value, "input")
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
