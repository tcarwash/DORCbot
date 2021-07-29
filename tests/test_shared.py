import unittest
import sys

sys.path.append("./dorcbot")
import dorcbot.shared as shared


class testIsvalidgrid(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(shared.isvalidgrid("CN85"))
        self.assertTrue(shared.isvalidgrid("CN85tp"))
        self.assertTrue(shared.isvalidgrid("cn85"))

    def test_invalid(self):
        self.assertFalse(shared.isvalidgrid("Garbage_notagrid"))


if __name__ == "__main__":
    unittest.main()
