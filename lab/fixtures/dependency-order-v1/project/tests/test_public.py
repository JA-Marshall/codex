import unittest

from dependency_order import order_tasks


class OrderTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(order_tasks({}), [])

    def test_dependency_precedes_task(self):
        self.assertEqual(order_tasks({"build": ["setup"], "setup": []}), ["setup", "build"])

    def test_available_order(self):
        self.assertEqual(order_tasks({"b": ["a"], "a": [], "z": []}), ["a", "b", "z"])
