from datetime import date, datetime
import pytest
from config import CLINIC_TIMEZONE
from models import Patient
from seed_data import seed_database

@pytest.fixture
def clock():
    return datetime(2030, 1, 7, 8, tzinfo=CLINIC_TIMEZONE)

@pytest.fixture
def db(tmp_path, clock):
    path = tmp_path / "clinic.sqlite3"
    seed_database(path, start_date=clock.date(), days=14)
    return path

@pytest.fixture
def patient():
    return Patient("Avery", "", "Taylor", date(1992, 6, 15))
