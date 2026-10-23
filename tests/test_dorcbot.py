import unittest
import sys
from unittest.mock import Mock, patch

sys.path.append("./dorcbot")
import dorcbot.dorcbot as dorcbot


class testSpots(unittest.TestCase):
    def setUp(self):
        dorcbot._data_cache.clear()

    @patch("dorcbot.dorcbot.requests.get")
    def test_spots(self, mock_get):
        payload = dorcbot.Payload()
        resp = {"spots": [
            {"dxcall": "AF7SO", "freq": "14.074", "mode": "FT8",
             "spotter": "AG7SU", "time": "Wed, 09 Jun 2021 01:25:21 GMT"}
        ]}
        mock_get.return_value.json.return_value = resp
        with patch.object(dorcbot, "DORC_CALLSIGNS", ["AG7SU"]):
            spots = dorcbot.get_spots(payload).content

        self.assertRegex(spots, "^Recent spots.+\n\nCall.+\n.+\nAF7SO.+GMT$")


class testSolar(unittest.TestCase):
    def setUp(self):
        dorcbot._data_cache.clear()

    @patch("dorcbot.dorcbot.requests.get")
    def test_solar(self, mock_get):
        payload = dorcbot.Payload()
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[{"time_tag": "2026-10-22", "flux": 75}])),
            Mock(json=Mock(return_value=[["time_tag", "Kp"], ["2026-10-22", "0.9"]])),
        ]
        solar = dorcbot.get_solar(payload).content

        self.assertIn("Current solar data", solar)
        self.assertIn("Solar radio flux (10.7 cm)", solar)
        self.assertIn("75", solar)
        self.assertIn("Planetary K index", solar)
        self.assertIn("0.9", solar)


class testDXCC(unittest.TestCase):
    def setUp(self):
        dorcbot._data_cache.clear()

    @patch("dorcbot.dorcbot.requests.get")
    def test_dxcc_func(self, mock_get):

        mock_get.return_value.json.return_value = {
            "entity": {"adif": 291, "name": "United States", "continent": "NA"}
        }
        dxcc = dorcbot.dxcc("ag7su")

        self.assertEqual(dxcc["dxcc"], 291)

    @patch("dorcbot.dorcbot.requests.get")
    def test_dxcc(self, mock_get):
        payload = dorcbot.Payload()
        mock_get.return_value.json.return_value = {
            "entity": {"adif": 291, "name": "United States", "continent": "NA"}
        }
        dxcc = dorcbot.get_dxcc(payload, "ag7su").content

        self.assertRegex(dxcc, "^DXCC.+")


class testCalldata(unittest.TestCase):
    @patch("dorcbot.dorcbot.requests.get")
    def test_calldata_func(self, mock_get):
        response = mock_get.return_value
        response.status_code = 200
        response.json.return_value = {
            "callsign": "AG7SU", "aliases": "", "name": "Test Operator",
            "nick": "Test", "country": "United States",
            "region": {"usState": "Oregon"}, "location": {"grid": "CN85"},
        }
        with patch.object(dorcbot, "HAMQTH_CALLSIGN", "AG7SU"), \
             patch.object(dorcbot, "HAMQTH_PASSWORD", "secret"), \
             patch.object(dorcbot, "hamqth_token", return_value="token"):
            calldata = dorcbot.calldata("ag7su")

        self.assertEqual(calldata["call"], "AG7SU")

    @patch("dorcbot.dorcbot.requests.get")
    def test_calldata(self, mock_get):
        payload = dorcbot.Payload()
        response = mock_get.return_value
        response.status_code = 200
        response.json.return_value = {
            "callsign": "AG7SU", "name": "Test Operator",
            "country": "United States", "location": {"grid": "CN85"},
        }
        with patch.object(dorcbot, "HAMQTH_CALLSIGN", "AG7SU"), \
             patch.object(dorcbot, "HAMQTH_PASSWORD", "secret"), \
             patch.object(dorcbot, "hamqth_token", return_value="token"):
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
