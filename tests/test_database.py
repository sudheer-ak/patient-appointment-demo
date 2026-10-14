import sqlite3
import pytest
from database import connection
from seed_data import seed_database
from test_booking import reserve


def test_schema_integrity(db):
    with connection(db) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_unique_index_blocks_direct_sql_double_booking(db, clock, patient):
    reserve(db, clock, patient)
    with connection(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("""INSERT INTO appointments
            (booking_reference, patient_first_name, patient_last_name, patient_dob, purpose_of_visit,
             doctor_id, appointment_date, appointment_time)
            VALUES ('OTHER-REF', 'Morgan', 'Taylor', '1990-01-01', 'Follow-up', 1, '2030-01-07', '09:00')""")


def test_cancelled_record_does_not_occupy_slot(db, clock, patient):
    reserve(db, clock, patient)
    with connection(db) as conn:
        conn.execute("UPDATE appointments SET booking_status = 'Cancelled'")
    reserve(db, clock, patient)
    with connection(db) as conn:
        assert conn.execute("SELECT count(*) FROM appointments").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE appointments SET booking_status = 'Confirmed' WHERE booking_status = 'Cancelled'")


def test_foreign_key_rejects_nonexistent_slot(db):
    with connection(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("""INSERT INTO appointments
            (booking_reference, patient_first_name, patient_last_name, patient_dob, purpose_of_visit,
             doctor_id, appointment_date, appointment_time)
            VALUES ('BAD-REF', 'Morgan', 'Taylor', '1990-01-01', 'Follow-up', 999, '2030-01-07', '09:15')""")


def test_seed_is_idempotent(db, clock):
    with connection(db) as conn:
        before = conn.execute("SELECT count(*) FROM doctor_availability").fetchone()[0]
    seed_database(db, start_date=clock.date(), days=14)
    with connection(db) as conn:
        assert conn.execute("SELECT count(*) FROM doctors").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM doctor_availability").fetchone()[0] == before


def test_overlapping_availability_rejected(db):
    with connection(db) as conn, pytest.raises(sqlite3.IntegrityError, match="Overlapping"):
        conn.execute("""INSERT INTO doctor_availability (doctor_id, appointment_date, start_time, end_time)
                        VALUES (1, '2030-01-07', '09:15', '09:45')""")


@pytest.mark.parametrize("day,start,end", [("2030-02-30", "09:00", "09:30"), ("2030-01-27", "9:00", "09:30"),
                                           ("2030-01-27", "24:00", "24:30"), ("2030-01-27", "10:00", "09:30")])
def test_malformed_schedule_rejected(db, day, start, end):
    with connection(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO doctor_availability (doctor_id, appointment_date, start_time, end_time) VALUES (1, ?, ?, ?)", (day, start, end))
