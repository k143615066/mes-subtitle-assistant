import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "00_Server", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from core.english_reflow import _parse_ai_groups, compare_subtitle_files, reflow_english_subtitles
from core.srt_parser import SRTEntry


def _entry(index, start, end, text):
    return SRTEntry(index, f"00:00:{start:02d},000", f"00:00:{end:02d},000", text)


class EnglishReflowTest(unittest.TestCase):
    class MockAI:
        api_key = "test-key"

        def __init__(self):
            self.calls = 0

        def call_chat(self, system_prompt, user_prompt, temperature=None, timeout=None, max_retries=None):
            self.calls += 1
            if self.calls == 1:
                return '{"groups":[{"source_positions":[1,2],"text":"This is a deliberately long sentence that should be revised because it is too fast to read and too long for one subtitle block."}]}'
            return '{"groups":[{"source_positions":[1],"text":"This is a concise sentence."},{"source_positions":[2],"text":"The second part is easy to read."}]}'

    def test_ai_group_partition_must_cover_every_source_entry(self):
        valid = '{"groups":[{"source_positions":[1,2],"text":"A complete sentence."}]}'
        invalid = '{"groups":[{"source_positions":[1],"text":"Only part."}]}'
        self.assertIsNotNone(_parse_ai_groups(valid, 2))
        self.assertIsNone(_parse_ai_groups(invalid, 2))

    def test_fallback_merges_fragments_and_reports_reading_speed(self):
        cn = [
            _entry(1, 0, 2, "所以，在 APP 看板上，"),
            _entry(2, 2, 6, "我们怎么知道这条 SMT 的生产进度？"),
            _entry(3, 6, 9, "通过三色灯收集设备状态。"),
        ]
        en = [
            _entry(1, 0, 2, "So how, on the APP Kanban,"),
            _entry(2, 2, 6, "do we know this SMT's production progress?"),
            _entry(3, 6, 9, "We collect equipment status through the tri-color light."),
        ]
        optimized, mappings, report = reflow_english_subtitles(cn, en, ai_client=None)
        self.assertLess(len(optimized), len(en))
        self.assertEqual(mappings[0], [0, 1])
        self.assertEqual(report["merged_entries"], 1)
        self.assertTrue(all("words_per_second" in item for item in report["entries"]))

    def test_comparison_reports_manual_reduction(self):
        system = [_entry(1, 0, 2, "So how, on the APP Kanban,"), _entry(2, 2, 6, "do we know?")]
        manual = [_entry(1, 0, 6, "So how do we know on the APP Kanban?")]
        report = compare_subtitle_files(system, manual)
        self.assertEqual(report["merged_entry_reduction"], 1)
        self.assertEqual(report["records"][0]["system_indices"], [1, 2])

    def test_ai_revision_is_requested_for_invalid_readability(self):
        cn = [_entry(1, 0, 2, "第一段"), _entry(2, 2, 4, "第二段")]
        en = [_entry(1, 0, 2, "First fragment."), _entry(2, 2, 4, "Second fragment.")]
        mock = self.MockAI()
        optimized, mappings, report = reflow_english_subtitles(
            cn,
            en,
            ai_client=mock,
            max_chars_per_line=20,
            hard_wps=4.0,
            revise_batches=True,
        )
        self.assertEqual(mock.calls, 2)
        self.assertEqual(report["ai_revision_batches"], 1)
        self.assertEqual(mappings, [[0], [1]])
        self.assertEqual(len(optimized), 2)


if __name__ == "__main__":
    unittest.main()
