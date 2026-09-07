import unittest

from config_merge import merge_config


class ConfigTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_config({}, {}), {})

    def test_nested_preservation(self):
        self.assertEqual(merge_config({"a": {"x": 1}}, {"a": {"y": 2}}), {"a": {"x": 1, "y": 2}})

    def test_no_mutation(self):
        base = {"a": 1}
        self.assertEqual(merge_config(base, {"b": 2}), {"a": 1, "b": 2})
        self.assertEqual(base, {"a": 1})
