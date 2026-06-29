import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "gym_nutrition.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")  # PostgreSQL URL for production (Railway)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
STORAGE_SECRET = os.environ.get("STORAGE_SECRET", "gym-nutrition-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours
SUPER_USER_USERNAME = os.environ.get("SUPER_USER_USERNAME", "admin")
SUPER_USER_PASSWORD = os.environ.get("SUPER_USER_PASSWORD", "admin123")
SUPER_USER_ROLE = "OWNER"