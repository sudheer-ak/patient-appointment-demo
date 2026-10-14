"""Small, explicit configuration surface for the local demonstration."""
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CLINIC_DB_PATH", str(ROOT / "data" / "clinic.sqlite3")))
CLINIC_NAME = "Willow Creek Clinic"
CLINIC_TIMEZONE = ZoneInfo("America/Los_Angeles")
SLOT_MINUTES = 30
BOOKING_DAYS = 60
CLINIC_OPENS = time(9)
CLINIC_CLOSES = time(17)
LUNCH_START = time(12)
LUNCH_END = time(13)
MIN_BIRTH_YEAR = 1900


def clinic_now() -> datetime:
    return datetime.now(CLINIC_TIMEZONE)
