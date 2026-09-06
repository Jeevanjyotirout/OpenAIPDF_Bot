import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp_files"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Try loading .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Telegram Bot Credentials
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8993850012:AAEkel2F0v3OKuJ0TvE6u6D3mRDNzthVMUA").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "OpenAIPDF_bot")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://openaipdf.com")

# Limits
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Session timeout (in seconds)
SESSION_TIMEOUT = 3600  # 1 hour
