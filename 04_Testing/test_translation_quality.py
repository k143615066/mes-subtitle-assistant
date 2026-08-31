import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "00_Server", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from core.srt_parser import SRTEntry
from core.translation_quality import generate_quality_report, load_quality_rules


def _entry(index, text):
    return SRTEntry(index=index, start_time="00:00:01,000", end_time="00:00:03,000", text=text)


class TranslationQualityTest(unittest.TestCase):
    def test_first_quality_check_rule_flags_forbidden_first_article_check(self):
        report = generate_quality_report(
            cn_entries=[_entry(1, "首检应该是质量检验")],
            en_entries=[_entry(1, "The first inspection should be First Article Check.")],
        )

        issues = report["entries"][0]["issues"]
        self.assertTrue(any(issue["type"] == "forbidden_term" for issue in issues))
        self.assertEqual(report["entries"][0]["confidence"], "low")

    def test_first_quality_check_rule_accepts_fqc(self):
        report = generate_quality_report(
            cn_entries=[_entry(1, "首检应该是质量检验")],
            en_entries=[_entry(1, "FQC should be performed before mass production.")],
        )

        self.assertEqual(report["entries"][0]["issues"], [])
        self.assertEqual(report["entries"][0]["confidence"], "high")

    def test_glossary_rules_include_first_quality_check(self):
        glossary = os.path.join(
            ROOT, "00_Server", "data", "glossary", "TreeMES_MES_Glossary.md"
        )
        rules = load_quality_rules(glossary)

        first_check_rules = [rule for rule in rules if rule["term"] == "首检"]
        self.assertTrue(first_check_rules)
        self.assertIn("FQC", first_check_rules[0]["aliases"])
        self.assertIn("First Article Check", first_check_rules[0]["forbidden"])


if __name__ == "__main__":
    unittest.main()
