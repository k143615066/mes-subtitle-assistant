import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEEPSEEK_API_KEY = os.environ.get("DeepSeek_Key", "")
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_GLOSSARY_FILENAME = "TreeMES_MES_Glossary.md"

TARGET_LANGUAGES = {
    "en": {
        "label": "英文",
        "prompt_name": "English",
        "file_prefix": "英文",
        "rtl": False,
        "max_chars_per_line": 42,
        "warning_reading_speed": 3.5,
        "hard_reading_speed": 4.0,
        "instruction": "Use concise, natural international English suitable for B2B manufacturing videos.",
    },
    "zh-TW": {
        "label": "台湾繁体中文",
        "prompt_name": "Traditional Chinese used in Taiwan",
        "file_prefix": "台湾繁体中文",
        "rtl": False,
        "max_chars_per_line": 22,
        "warning_reading_speed": 6.0,
        "hard_reading_speed": 8.0,
        "instruction": (
            "Use Traditional Chinese characters, Taiwan terminology and Taiwan punctuation. "
            "Localize wording naturally instead of performing character conversion only."
        ),
    },
    "vi": {
        "label": "越南语",
        "prompt_name": "Vietnamese",
        "file_prefix": "越南语",
        "rtl": False,
        "max_chars_per_line": 42,
        "warning_reading_speed": 3.5,
        "hard_reading_speed": 4.0,
        "instruction": "Use concise, professional Vietnamese suitable for manufacturing software demonstrations.",
    },
    "ar": {
        "label": "阿拉伯语（现代标准阿拉伯语）",
        "prompt_name": "Modern Standard Arabic (MSA)",
        "file_prefix": "阿拉伯语",
        "rtl": True,
        "max_chars_per_line": 38,
        "warning_reading_speed": 3.2,
        "hard_reading_speed": 3.8,
        "instruction": (
            "Use Modern Standard Arabic, right-to-left writing conventions and concise formal wording. "
            "Keep product names, MES, SMT and other established Latin abbreviations unchanged."
        ),
    },
    "es-MX": {
        "label": "西班牙语（墨西哥）",
        "prompt_name": "Mexican Spanish",
        "file_prefix": "西班牙语（墨西哥）",
        "rtl": False,
        "max_chars_per_line": 42,
        "warning_reading_speed": 3.5,
        "hard_reading_speed": 4.0,
        "instruction": (
            "Use neutral professional Mexican Spanish suitable for B2B manufacturing videos, "
            "avoiding Spain-specific wording."
        ),
    },
}
DEFAULT_TARGET_LANGUAGE = "en"

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
