import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEEPSEEK_API_KEY = os.environ.get("DeepSeek_Key", "")
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_GLOSSARY_FILENAME = "TreeMES_MES_Glossary.md"

BATCH_SIZE = 25
TRANSLATION_TEMPERATURE = 0.3

ENABLE_ENGLISH_REFLOW = os.environ.get("MES_ENABLE_ENGLISH_REFLOW", "1") == "1"
ENGLISH_REFLOW_BATCH_SIZE = 15
ENGLISH_WARNING_WPS = 3.5
ENGLISH_HARD_WPS = 4.0
ENGLISH_MIN_DURATION_MS = 1200
ENGLISH_MAX_CHARS_PER_LINE = 42
ENGLISH_REFLOW_TIMEOUT = 60
ENGLISH_REFLOW_MAX_RETRIES = 1
ENGLISH_REFLOW_REVISE_BATCHES = False

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 15000
SECRET_KEY = "mes-subtitle-tool-secret-key-2025"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "data", "output")
GLOSSARY_FOLDER = os.path.join(BASE_DIR, "..", "data", "glossary")
LOG_FOLDER = os.path.join(BASE_DIR, "..", "logs")

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, GLOSSARY_FOLDER, LOG_FOLDER]:
    os.makedirs(folder, exist_ok=True)
