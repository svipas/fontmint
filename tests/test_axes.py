import unittest

from fontmint.axes import is_static, parse_spec, plan
from fontmint.common import FontmintError

from . import fixtures as fx


class ParseSpecTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(parse_spec("400"), [400.0])
        self.assertEqual(parse_spec("400,700"), [400.0, 700.0])
        self.assertEqual(parse_spec(" 400 , 700 "), [400.0, 700.0])
        self.assertEqual(parse_spec("-10"), [-10.0])
        self.assertEqual(parse_spec("87.5"), [87.5])

    def test_ranges_are_normalized(self):
        self.assertEqual(parse_spec("300:700"), [(300.0, 700.0)])
        self.assertEqual(parse_spec("700:300"), [(300.0, 700.0)])
        self.assertEqual(parse_spec("-15:0"), [(-15.0, 0.0)])
        self.assertEqual(parse_spec("400:400"), [400.0])

    def test_all_and_mixed(self):
        self.assertEqual(parse_spec("all"), ["all"])
        self.assertEqual(parse_spec("400,300:700"), [400.0, (300.0, 700.0)])

    def test_python_values(self):
        self.assertEqual(parse_spec(400), [400.0])
        self.assertEqual(parse_spec([400, (700, 300), "all", "500"]), [400.0, (300.0, 700.0), "all", 500.0])
        self.assertEqual(parse_spec((300, 700)), [(300.0, 700.0)])

    def test_invalid(self):
        for bad in ("abc", "", ",", "1:2:3", "400,bold"):
            with self.subTest(bad=bad), self.assertRaises(FontmintError):
                parse_spec(bad)
        with self.assertRaises(FontmintError):
            parse_spec({"wght": 400})


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.font = fx.open_font(fx.variable_ttf())

    def test_combinations_multiply(self):
        p = plan(self.font, {"wght": "400,700", "wdth": "75,100"})
        self.assertEqual(
            p.combos,
            [{"wght": 400, "wdth": 75}, {"wght": 400, "wdth": 100},
             {"wght": 700, "wdth": 75}, {"wght": 700, "wdth": 100}],
        )
        self.assertEqual(p.labeled, {"wght", "wdth"})

    def test_all_uses_named_instance_values(self):
        self.assertEqual(plan(self.font, {"wght": "all"}).combos, [{"wght": 400}, {"wght": 700}])
        self.assertEqual(plan(self.font, {"wdth": "all"}).combos, [{"wdth": 75}, {"wdth": 100}])

    def test_duplicates_removed(self):
        self.assertEqual(plan(self.font, {"wght": "400,400,all"}).combos, [{"wght": 400}, {"wght": 700}])

    def test_single_value_axes_are_not_labeled(self):
        p = plan(self.font, {"wght": "400,700", "wdth": "75"})
        self.assertEqual(p.labeled, {"wght"})

    def test_ranges(self):
        p = plan(self.font, {"wght": "400,300:700"})
        self.assertEqual(p.combos, [{"wght": 400}, {"wght": (300, 700)}])
        self.assertEqual([is_static(c) for c in p.combos], [True, False])
        self.assertEqual(p.labeled, set())

    def test_out_of_range(self):
        with self.assertRaisesRegex(FontmintError, "outside the axis range 100–900"):
            plan(self.font, {"wght": "950"})
        with self.assertRaisesRegex(FontmintError, "outside"):
            plan(self.font, {"wdth": "50:100"})

    def test_errors_name_the_axis(self):
        with self.assertRaisesRegex(FontmintError, "axis wght: invalid axis value 'bold'"):
            plan(self.font, {"wght": "bold"})

    def test_unknown_axis(self):
        with self.assertRaisesRegex(FontmintError, "no 'slnt' axis"):
            plan(self.font, {"slnt": "-10"})


if __name__ == "__main__":
    unittest.main()
