import unittest
import sys
from unittest.mock import Mock, patch

sys.path.append("./dorcbot")
import dorcbot.dorcbot as dorcbot


class testSpots(unittest.TestCase):
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


class testSolar(unittest.TestCase):
    def setUp(self):
        with open("tests/solar.xml", "r") as f:
            self.resp = f.read()

    @patch("dorcbot.dorcbot.requests.get")
    def test_solar(self, mock_get):
        payload = dorcbot.Payload()
        mock_get.return_value.content = self.resp
        solar = dorcbot.get_solar(payload).content

        self.assertRegex(solar, "^Solar.+\n\n.+\n.+\n09.+75$")


class testDXCC(unittest.TestCase):
    def setUp(self):
        with open("tests/dxcc.xml", "r") as f:
            self.resp = f.read()

    @patch("dorcbot.dorcbot.requests.get")
    def test_dxcc_func(self, mock_get):

        mock_get.return_value.content = self.resp
        dxcc = dorcbot.dxcc("ag7su")

        self.assertEqual(dxcc["dxcc"], "291")

    @patch("dorcbot.dorcbot.requests.get")
    def test_dxcc(self, mock_get):
        payload = dorcbot.Payload()
        mock_get.return_value.content = self.resp
        dxcc = dorcbot.get_dxcc(payload, "ag7su").content

        self.assertRegex(dxcc, "^DXCC.+")


class testCalldata(unittest.TestCase):
    def setUp(self):
        with open("tests/calldata.xml", "r") as f:
            self.resp = f.read()
        self.mock_cannedcallinfo = patch.object(
            dorcbot, "QRZCALLSIGNSAMPLE", "tests/calldata.xml"
        )

    @patch("dorcbot.dorcbot.requests.get")
    def test_calldata_func(self, mock_get):
        with self.mock_cannedcallinfo:
            mock_get.return_value.content = self.resp
            calldata = dorcbot.calldata("ag7su")

        self.assertEqual(calldata["call"], "AG7SU")

    @patch("dorcbot.dorcbot.requests.get")
    def test_calldata(self, mock_get):
        payload = dorcbot.Payload()
        with self.mock_cannedcallinfo:
            mock_get.return_value.content = self.resp
            calldata = dorcbot.get_calldata(payload, "ag7su").content

        self.assertRegex(calldata, "^Data.+")


class testOtherCommands(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
