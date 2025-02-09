import unittest

from server.version_util import is_version_less_or_equal_than


class TestVersionComparison(unittest.TestCase):

    def test_valid_version_comparisons(self):
        # Test valid version comparisons
        self.assertTrue(is_version_less_or_equal_than("2024.6.0-alpha-1", "2024.6.0-alpha-0"))
        self.assertTrue(is_version_less_or_equal_than("2024.6.0-alpha-1", "2024.6.0-alpha-1"))
        self.assertFalse(is_version_less_or_equal_than("2024.6.0-alpha-0", "2024.6.0-alpha-1"))
        self.assertTrue(is_version_less_or_equal_than("2025.3.0", "2025.1.0"))
        self.assertFalse(is_version_less_or_equal_than("2025.1.0", "2025.3.0"))
        self.assertTrue(is_version_less_or_equal_than("2025.1.0", "2025.1.0-alpha-1"))
        self.assertTrue(is_version_less_or_equal_than("2025.1.0", "1.0.0"))

    def test_invalid_version_strings(self):
        # Test invalid version strings
        self.assertFalse(is_version_less_or_equal_than("2024-6-0-alpha-1", "2024.6.0-alpha-0"))
        self.assertFalse(is_version_less_or_equal_than("2024.6.0-alpha-1", "2024-6-0-alpha-0"))
        self.assertTrue(is_version_less_or_equal_than("v2024.6.0-alpha-1", "2024.6.0-alpha-0"))
        self.assertTrue(is_version_less_or_equal_than("2024.6.0-alpha-1", "v2024.6.0-alpha-0"))

    def test_edge_cases(self):
        # Test edge cases
        self.assertFalse(is_version_less_or_equal_than(None, "2024.6.0-alpha-0"))
        self.assertFalse(is_version_less_or_equal_than("2024.6.0-alpha-1", None))
        self.assertFalse(is_version_less_or_equal_than(None, None))
