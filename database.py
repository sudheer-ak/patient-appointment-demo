"""SQLite persistence. Each operation owns and closes its connection."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL CHECK(length(trim(doctor_name)) > 0),
    specialty TEXT NOT NULL,
    clinic_name TEXT NOT NULL,
    active_status INTEGER NOT NULL DEFAULT 1 CHECK(active_status IN (0, 1))
);
CREATE TABLE IF NOT EXISTS doctor_availability (
    availability_id INTEGER PRIMARY KEY,
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id),
    appointment_date TEXT NOT NULL CHECK(
        length(appointment_date) = 10 AND date(appointment_date, '+0 days') IS NOT NULL
        AND date(appointment_date, '+0 days') = appointment_date),
    start_time TEXT NOT NULL CHECK(length(start_time) = 5 AND time(start_time) IS NOT NULL
        AND strftime('%H:%M', start_time) = start_time AND start_time < '24:00'),
    end_time TEXT NOT NULL CHECK(length(end_time) = 5 AND time(end_time) IS NOT NULL
        AND strftime('%H:%M', end_time) = end_time AND end_time < '24:00'),
    CHECK(start_time < end_time),
    UNIQUE(doctor_id, appointment_date, start_time)
);
CREATE INDEX IF NOT EXISTS idx_availability_date ON doctor_availability(appointment_date, doctor_id);
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY,
    booking_reference TEXT NOT NULL UNIQUE,
    patient_first_name TEXT NOT NULL CHECK(length(trim(patient_first_name)) BETWEEN 1 AND 80),
    patient_middle_name TEXT NOT NULL DEFAULT '' CHECK(length(patient_middle_name) <= 80),
    patient_last_name TEXT NOT NULL CHECK(length(trim(patient_last_name)) BETWEEN 1 AND 80),
    patient_dob TEXT NOT NULL CHECK(length(patient_dob) = 10 AND date(patient_dob, '+0 days') IS NOT NULL
        AND date(patient_dob, '+0 days') = patient_dob AND patient_dob >= '1900-01-01'),
    purpose_of_visit TEXT NOT NULL CHECK(purpose_of_visit IN
        ('General Consultation', 'Follow-up', 'Annual Checkup', 'Other')
        OR (substr(purpose_of_visit, 1, 7) = 'Other: ' AND length(purpose_of_visit) <= 307)),
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id),
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    booking_status TEXT NOT NULL DEFAULT 'Confirmed' CHECK(booking_status IN ('Confirmed', 'Cancelled')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY(doctor_id, appointment_date, appointment_time)
        REFERENCES doctor_availability(doctor_id, appointment_date, start_time)
);
-- Cancelled records can remain for history without occupying a slot.
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_appointment
    ON appointments(doctor_id, appointment_date, appointment_time)
    WHERE booking_status = 'Confirmed';
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date, booking_status);
-- A window is one appointment slot. Overlapping windows would bypass exact-time uniqueness.
CREATE TRIGGER IF NOT EXISTS availability_no_overlap_insert
BEFORE INSERT ON doctor_availability
WHEN EXISTS(SELECT 1 FROM doctor_availability a
    WHERE a.doctor_id = NEW.doctor_id AND a.appointment_date = NEW.appointment_date
    AND a.start_time < NEW.end_time AND a.end_time > NEW.start_time
    AND NOT (a.start_time = NEW.start_time AND a.end_time = NEW.end_time))
BEGIN SELECT RAISE(ABORT, 'Overlapping availability'); END;
CREATE TRIGGER IF NOT EXISTS availability_no_overlap_update
BEFORE UPDATE ON doctor_availability
WHEN EXISTS(SELECT 1 FROM doctor_availability a
    WHERE a.availability_id != OLD.availability_id AND a.doctor_id = NEW.doctor_id
    AND a.appointment_date = NEW.appointment_date
    AND a.start_time < NEW.end_time AND a.end_time > NEW.start_time)
BEGIN SELECT RAISE(ABORT, 'Overlapping availability'); END;
"""


@contextmanager
def connection(db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


def initialize_database(db_path=DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connection(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
