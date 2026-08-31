import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "00_Server", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main
from core.srt_parser import SRTEntry


class DeliveryWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_folder = os.path.join(self.temp_dir.name, "uploads")
        self.output_folder = os.path.join(self.temp_dir.name, "output")
        self.previous_upload_folder = main.cfg.UPLOAD_FOLDER
        self.previous_output_folder = main.cfg.OUTPUT_FOLDER
        self.previous_api_key = main.cfg.DEEPSEEK_API_KEY
        main.cfg.UPLOAD_FOLDER = self.upload_folder
        main.cfg.OUTPUT_FOLDER = self.output_folder
        main.cfg.DEEPSEEK_API_KEY = "test-key"
        main.sessions.clear()

    def tearDown(self):
        main.cfg.UPLOAD_FOLDER = self.previous_upload_folder
        main.cfg.OUTPUT_FOLDER = self.previous_output_folder
        main.cfg.DEEPSEEK_API_KEY = self.previous_api_key
        main.sessions.clear()
        self.temp_dir.cleanup()

    def test_workflow_delivers_exactly_three_subtitle_files(self):
        session_id = "deliverytest"
        entries = [
            SRTEntry(1, "00:00:00,000", "00:00:02,000", "这个 MES 看板。"),
            SRTEntry(2, "00:00:02,000", "00:00:04,000", "然后我们可以查看生产进度。"),
        ]
        main.sessions[session_id] = {
            "id": session_id,
            "filename": "demo.srt",
            "entries": entries,
            "status": "uploaded",
            "progress": {"step": "", "percent": 0, "message": "", "logs": []},
            "output_files": [],
            "api_calls": [],
        }

        polished_entries = [
            SRTEntry(1, "00:00:00,000", "00:00:02,000", "MES 看板。"),
            SRTEntry(2, "00:00:02,000", "00:00:04,000", "我们可以查看生产进度。"),
        ]
        translated_entries = [
            SRTEntry(1, "00:00:00,000", "00:00:02,000", "The MES dashboard."),
            SRTEntry(2, "00:00:02,000", "00:00:04,000", "We can view production progress."),
        ]
        readable_entries = [
            SRTEntry(1, "00:00:00,000", "00:00:04,000", "The MES dashboard lets us view production progress."),
        ]

        with patch.object(main, "polish_srt_entries", return_value=polished_entries), patch.object(
            main, "translate_srt_entries", return_value=translated_entries
        ), patch.object(
            main,
            "reflow_english_subtitles",
            return_value=(readable_entries, [[0, 1]], {"merged_entries": 1}),
        ):
            main._polish_worker(session_id)
            self.assertEqual(main.sessions[session_id]["status"], "optimized")
            main._process_worker(session_id)

        session = main.sessions[session_id]
        self.assertEqual(session["status"], "completed")
        self.assertEqual(len(session["output_files"]), 3)
        self.assertEqual(
            [item["name"] for item in session["output_files"]],
            ["中文_demo.srt", "英文_demo.srt", "英文_可读优化版_demo.srt"],
        )
        self.assertTrue(all(os.path.exists(item["path"]) for item in session["output_files"]))


if __name__ == "__main__":
    unittest.main()
