import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "00_Server", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from core.glossary_manager import GlossaryManager
from core.translator import load_glossary


class GlossaryManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.temp_dir, "glossary.md")
        source = os.path.join(
            ROOT, "00_Server", "data", "glossary", "TreeMES_MES_Glossary.md"
        )
        shutil.copyfile(source, self.path)
        self.manager = GlossaryManager(self.path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_update_and_delete_term(self):
        initial = self.manager.list_terms()
        self.assertGreaterEqual(initial["count"], 129)

        saved = self.manager.save_term({
            "category": "Product and Platform",
            "term": "测试术语",
            "translation": "Test Term",
            "alias": "TT",
            "module": "Testing",
            "notes": "Temporary test term",
        })
        self.assertEqual(saved["translation"], "Test Term")
        self.assertIn("测试术语 → Test Term", load_glossary(self.path))

        updated = self.manager.save_term({
            **saved,
            "translation": "Updated Test Term",
        })
        self.assertEqual(updated["translation"], "Updated Test Term")
        self.assertIn("测试术语 → Updated Test Term", load_glossary(self.path))

        self.manager.delete_term(updated["id"])
        self.assertNotIn("测试术语", load_glossary(self.path))

    def test_duplicate_term_is_rejected_within_category(self):
        with self.assertRaises(ValueError):
            self.manager.save_term({
                "category": "Product and Platform",
                "term": "树字工厂",
                "translation": "Another TreeMES",
            })


if __name__ == "__main__":
    unittest.main()
