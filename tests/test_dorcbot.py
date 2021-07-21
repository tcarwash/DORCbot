import unittest
import sys
from unittest.mock import Mock, patch

sys.path.append("./dorcbot")
import dorcbot.dorcbot as dorcbot


class testspots(unittest.TestCase):
    @patch("dorcbot.dorcbot.requests.get")
    def test_spots(self, mock_get):
        payload = dorcbot.Payload()
        resp = [
            {
                "callsign": "AF7SO",
                "frequency": "14.074",
                "mode": "FT8",
                "time": "Wed, 09 Jun 2021 01:25:21 GMT",
            }
        ]
        mock_get.return_value.json.return_value = resp
        spots = dorcbot.get_spots(payload).content

        self.assertRegex(spots, "^Most.+\n\nCall.+\n.+\nAF7SO.+GMT$")

    @patch("dorcbot.dorcbot.requests.get")
    def test_solar(self, mock_get):
        payload = dorcbot.Payload()
        with open("tests/solar.xml", "r") as f:
            resp = f.read()
        mock_get.return_value.content = resp
        solar = dorcbot.get_solar(payload).content

        self.assertRegex(solar, "^Solar.+\n\n.+\n.+\n09.+75$")

    def test_help(self):
        payload = dorcbot.Payload()
        mock_cmdmap = patch.object(
            dorcbot,
            "commandmap",
            {
                "!spots": [
                    dorcbot.get_spots,
                    "Get the 3 most recent spots of DORC members",
                ]
            },
        )
        with mock_cmdmap:
            out = dorcbot.get_help(payload, "").content

        self.assertRegex(out, r".*!spots.*")

    @patch("dorcbot.dorcbot.requests.get")
    def test_calldata(self, mock_get):
        with open("tests/calldata.xml", "r") as f:
            resp = f.read()

        mock_get.return_value.content = resp
        calldata = dorcbot.calldata("ag7su")

        self.assertEqual(calldata["call"], "AG7SU")

    @patch("dorcbot.dorcbot.requests.get")
    def test_dxcc(self, mock_get):
        with open("tests/dxcc.xml", "r") as f:
            resp = f.read()

        mock_get.return_value.content = resp
        dxcc = dorcbot.dxcc("ag7su")

        self.assertEqual(dxcc["dxcc"], "291")


if __name__ == "__main__":
    unittest.main()
