import io
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "00_Server", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main


class ReleaseRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_home_and_glossary_are_available(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        glossary = self.client.get("/api/glossary")
        self.assertEqual(glossary.status_code, 200)
        self.assertGreaterEqual(glossary.get_json()["count"], 129)

    def test_removed_feature_routes_are_not_available(self):
        for path in [
            "/api/transcribe",
            "/api/rewrite",
            "/history",
            "/feedback",
            "/corpus",
            "/api/ai-split-suggest",
            "/api/save-segments",
        ]:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_upload_rejects_non_srt_files(self):
        response = self.client.post(
            "/api/upload",
            data={"file": (io.BytesIO(b"not an srt"), "subtitle.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
