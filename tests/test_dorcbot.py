import unittest
import dorcbot.dorcbot as dorcbot
from unittest.mock import Mock, patch

class testspots(unittest.TestCase):

    @patch('dorcbot.dorcbot.requests.get')
    def test_spots(self, mock_get):
        resp = [{"callsign":"AF7SO","frequency":"14.074","mode":"FT8","time":"Wed, 09 Jun 2021 01:25:21 GMT"}] 
        mock_get.return_value.json.return_value = resp 
        spots = dorcbot.get_spots()
        
        self.assertRegex(spots, r'.*AF7SO.*01:25:21 GMT')

    @patch('dorcbot.dorcbot.requests.get')
    def test_solar(self, mock_get):
        with open('tests/solar.xml', 'r') as f:
            resp = f.read()
        mock_get.return_value.content = resp 
        solar = dorcbot.get_solar()
        
        self.assertRegex(solar, r'.*0300.*75')

    def test_help(self):
        mock_cmdmap = patch.object(dorcbot, 'commandmap', {'!spots': [dorcbot.get_spots, "Get the 3 most recent spots of DORC members"]})
        with mock_cmdmap:
            out = dorcbot.get_help()

        self.assertRegex(out, r'.*!spots.*')

if __name__ == "__main__":
    unittest.main()
