import unittest
import sys
import json
from unittest.mock import Mock, patch

sys.path.append("./dorcbot")
import dorcbot.kc2g as kc2g


class testKC2G(unittest.TestCase):
    def setUp(self):
        with open("tests/kc2g.json", "r") as f:
            self.resp = json.load(f)

    @patch("dorcbot.dorcbot.kc2g.requests.get")
    def test_kc2g(self, mock_get):
        mock_get.return_value.json.return_value = self.resp
        mufdata = kc2g.muf("CN85", "FN85")

        self.assertEqual(mufdata["luf_lp"], 15.13131562438781)


if __name__ == "__main__":
    unittest.main()
