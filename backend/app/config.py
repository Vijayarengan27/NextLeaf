from pathlib import Path
from dotenv import load_dotenv
import os

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

load_dotenv(BACKEND_DIR / ".env")

DATABASE_PATH = DATA_DIR / "goodreads_catalog.sqlite"

META_API_KEY = os.getenv("META_API_KEY")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3")