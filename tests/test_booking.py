from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from threading import Barrier
import subprocess
import sys
import pytest
from booking import book_appointment, get_available_slots, new_reference
from database import connection
from models import Patient, ValidationError, SlotUnavailable, validate_purpose
from seed_data import seed_database


def reserve(db, clock, patient, doctor=1, day="2030-01-07", time="09:00", **kwargs):
    return book_appointment(patient, "General Consultation", doctor, day, time, db_path=db, now=clock, **kwargs)


def test_successful_booking_and_confirmation_excludes_dob(db, clock, patient):
    result = reserve(db, clock, patient)
    assert result.booking_status == "Confirmed"
    assert result.patient_name == "Avery Taylor"
    assert result.doctor_name == "Dr. Maya Rowan"
    assert result.clinic_name == "Willow Creek Clinic"
    assert result.appointment_time == "09:00"
    assert result.booking_reference.startswith("WC-")
    assert "dob" not in str(asdict(result))
    assert "1992-06-15" not in str(asdict(result))
    with connection(db) as conn:
        assert conn.execute("SELECT patient_dob FROM appointments").fetchone()[0] == "1992-06-15"
    assert "09:00" not in [s.start_time for s in get_available_slots(clock.date(), doctor_id=1, db_path=db, now=clock)]


@pytest.mark.parametrize("first,last,dob", [("", "Taylor", "1992-06-15"), ("Avery", " ", "1992-06-15"), ("Avery", "Taylor", None)])
def test_required_fields(first, last, dob):
    with pytest.raises(ValidationError):
        Patient.validate(first, "", last, dob, today=date(2030, 1, 7))


@pytest.mark.parametrize("dob", ["2031-01-01", "1899-12-31", "2000-02-30", "not-a-date", "1992-6-15"])
def test_invalid_dob(dob):
    with pytest.raises(ValidationError):
        Patient.validate("Avery", "", "Taylor", dob, today=date(2030, 1, 7))


def test_optional_middle_and_unicode_names():
    p = Patient.validate(" Zoë ", "", "O’Neill", "1992-06-15", today=date(2030, 1, 7))
    assert p.full_name == "Zoë O’Neill"


@pytest.mark.parametrize("day,time", [("2030-01-06", "09:00"), ("2030-01-07", "08:00"), ("2030-01-07", "07:30")])
def test_past_date_and_time_rejected(db, clock, patient, day, time):
    with pytest.raises(ValidationError, match="future"):
        reserve(db, clock, patient, day=day, time=time)


@pytest.mark.parametrize("time", ["09:15", "12:00", "17:00"])
def test_off_schedule_and_lunch_rejected(db, clock, patient, time):
    with pytest.raises(SlotUnavailable):
        reserve(db, clock, patient, time=time)


def test_simultaneous_same_slot_has_exactly_one_winner(db, clock, patient):
    barrier = Barrier(2)
    def attempt(name):
        barrier.wait(timeout=10)
        try:
            return reserve(db, clock, replace(patient, first_name=name)).booking_status
        except SlotUnavailable:
            return "Unavailable"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["Avery", "Morgan"]))
    assert sorted(results) == ["Confirmed", "Unavailable"]
    with connection(db) as conn:
        assert conn.execute("SELECT count(*) FROM appointments").fetchone()[0] == 1


def test_same_time_different_doctors(db, clock, patient):
    a = reserve(db, clock, patient, doctor=1)
    b = reserve(db, clock, patient, doctor=2)
    assert a.booking_reference != b.booking_reference
    assert a.doctor_name != b.doctor_name


def test_doctor_switch_changes_availability(db, clock):
    day = date(2030, 1, 8)
    assert get_available_slots(day, doctor_id=1, db_path=db, now=clock)
    assert get_available_slots(day, doctor_id=2, db_path=db, now=clock) == []


def test_any_doctor_identified_and_not_silently_reassigned(db, clock, patient):
    slots = get_available_slots(clock.date(), doctor_id=None, db_path=db, now=clock)
    assert {s.doctor_id for s in slots} == {1, 2, 4}
    selected = slots[0]
    result = reserve(db, clock, patient, doctor=selected.doctor_id, time=selected.start_time)
    assert result.doctor_name == selected.doctor_name
    with pytest.raises(SlotUnavailable):
        reserve(db, clock, patient, doctor=selected.doctor_id, time=selected.start_time)
    with pytest.raises(SlotUnavailable):
        reserve(db, clock, patient, doctor=None, time="10:00")


def test_restart_persists_appointments(db, clock, patient):
    result = reserve(db, clock, patient)
    script = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('SELECT booking_reference FROM appointments').fetchone()[0])"
    persisted = subprocess.check_output([sys.executable, "-c", script, str(db)], text=True).strip()
    assert persisted == result.booking_reference
    seed_database(db, start_date=clock.date(), days=14)
    assert "09:00" not in [s.start_time for s in get_available_slots(clock.date(), doctor_id=1, db_path=db, now=clock)]


def test_no_slots_on_closed_day(db, clock):
    assert get_available_slots("2030-01-13", db_path=db, now=clock) == []


def test_fully_booked_date_has_no_slots(db, clock, patient):
    for s in get_available_slots(clock.date(), doctor_id=4, db_path=db, now=clock):
        reserve(db, clock, patient, doctor=4, time=s.start_time)
    assert get_available_slots(clock.date(), doctor_id=4, db_path=db, now=clock) == []


def test_backend_revalidates_patient(db, clock, patient):
    with pytest.raises(ValidationError):
        reserve(db, clock, replace(patient, dob=date(2031, 1, 1)))


def test_idempotent_retry(db, clock, patient):
    reference = new_reference()
    assert reserve(db, clock, patient, reference=reference) == reserve(db, clock, patient, reference=reference)
    with connection(db) as conn:
        assert conn.execute("SELECT count(*) FROM appointments").fetchone()[0] == 1
    with pytest.raises(ValidationError, match="already in use"):
        reserve(db, clock, replace(patient, first_name="Morgan"), reference=reference)


def test_inactive_doctor_not_bookable(db, clock, patient):
    with connection(db) as conn:
        conn.execute("UPDATE doctors SET active_status = 0 WHERE doctor_id = 1")
    assert not get_available_slots(clock.date(), doctor_id=1, db_path=db, now=clock)
    with pytest.raises(SlotUnavailable):
        reserve(db, clock, patient)


def test_timezone_is_clinic_time(db, clock):
    utc_clock = datetime(2030, 1, 7, 17, tzinfo=timezone.utc)
    assert get_available_slots(clock.date(), doctor_id=1, db_path=db, now=utc_clock)[0].start_time == "09:30"


def test_other_purpose_and_validation(db, clock, patient):
    result = book_appointment(patient, "Other", 1, "2030-01-07", "09:00", other=" Demo visit ", db_path=db, now=clock)
    assert result.purpose_of_visit == "Other: Demo visit"
    assert validate_purpose("Other") == "Other"
    with pytest.raises(ValidationError):
        validate_purpose("Invalid")
    with pytest.raises(ValidationError):
        validate_purpose("Other", "x" * 301)


def test_failed_booking_rolls_back(db, clock, patient):
    with pytest.raises(SlotUnavailable):
        reserve(db, clock, patient, time="12:00")
    assert reserve(db, clock, patient).booking_status == "Confirmed"
