import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

SQL_SERVER = os.getenv("ZP_SQL_SERVER")
SQL_DB = os.getenv("ZP_SQL_DB")
SQL_USER = os.getenv("ZP_SQL_USER")
SQL_PASS = os.getenv("ZP_SQL_PASS")
SQL_DRIVER = os.getenv("ZP_SQL_DRIVER")

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = Path(os.getenv("ZPROVEART_EXPORT_DIR", "exports"))