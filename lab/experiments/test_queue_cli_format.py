import json
import unittest

from queue_cli_format import parse_cli_output


class QueueCliFormatTests(unittest.TestCase):
    def test_equivalent_json_styles_preserve_values_and_types(self):
        value = {"a": [1, True, None, {"accent": "é", "nested": 1.5}], "z": {}}
        for options in (
            {},
            {"ensure_ascii": False},
            {"separators": (",", ":")},
            {"indent": 2, "ensure_ascii": False},
        ):
            with self.subTest(options=options):
                encoded = (json.dumps(value, sort_keys=True, **options) + "\n").encode()
                observed = parse_cli_output(encoded)
                self.assertEqual(json.dumps(observed), json.dumps(value))
                self.assertIs(type(observed["a"][0]), int)
                self.assertIs(type(observed["a"][1]), bool)
        self.assertEqual(parse_cli_output(b'{"a":"\\u00E9"}\n'), {"a": "é"})

    def test_malformed_unsorted_duplicate_and_nonfinite_output_fails(self):
        for data in (
            b'{"z":1,"a":2}\n',
            b'{"a":{"z":1,"b":2}}\n',
            b'{"a":1,"a":1}\n',
            b'[{"b":1,"a":2}]\n',
            b'{}',
            b'{}\n\n',
            b'{}\n{}\n',
            b'{}\nextra',
            b'\xff\n',
            b'NaN\n',
            b'{"a":Infinity}\n',
            b'1e999\n',
            b'\n',
        ):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_cli_output(data)


if __name__ == "__main__":
    unittest.main()
