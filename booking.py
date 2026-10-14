"""Availability queries and atomic, idempotent appointment creation."""
from datetime import datetime, timezone
import secrets
import sqlite3

from config import DB_PATH, CLINIC_TIMEZONE, clinic_now
from database import connection
from models import (Patient, Slot, Confirmation, ValidationError, SlotUnavailable,
                    BookingBusy, parse_date, parse_time, normalize_now, validate_purpose)


def new_reference():
    return "WC-" + secrets.token_hex(12).upper()


def get_doctors(db_path=DB_PATH):
    with connection(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM doctors WHERE active_status = 1 ORDER BY doctor_id")]


def _slots(conn, start_date, end_date, doctor_id, now):
    rows = conn.execute("""
        SELECT a.doctor_id, d.doctor_name, d.specialty, d.clinic_name,
               a.appointment_date, a.start_time, a.end_time
        FROM doctor_availability a JOIN doctors d USING(doctor_id)
        WHERE d.active_status = 1 AND a.appointment_date BETWEEN ? AND ?
        AND (? IS NULL OR a.doctor_id = ?)
        AND NOT EXISTS(SELECT 1 FROM appointments p WHERE p.doctor_id = a.doctor_id
            AND p.appointment_date = a.appointment_date AND p.appointment_time = a.start_time
            AND p.booking_status = 'Confirmed')
        ORDER BY a.appointment_date, a.start_time, a.doctor_id
    """, (start_date.isoformat(), end_date.isoformat(), doctor_id, doctor_id)).fetchall()
    return [Slot(**dict(r)) for r in rows
            if datetime.combine(parse_date(r["appointment_date"]), parse_time(r["start_time"]), CLINIC_TIMEZONE) > now]


def get_available_slots(start_date, end_date=None, doctor_id=None, *, db_path=DB_PATH, now=None):
    start = parse_date(start_date, "Appointment date")
    end = parse_date(end_date or start, "Appointment date")
    if end < start:
        raise ValidationError("The end date must follow the start date.")
    with connection(db_path) as conn:
        return _slots(conn, start, end, doctor_id, normalize_now(now or clinic_now()))


def _confirmation(conn, reference):
    row = conn.execute("""
        SELECT p.*, d.doctor_name, d.clinic_name, a.end_time FROM appointments p
        JOIN doctors d USING(doctor_id)
        JOIN doctor_availability a ON a.doctor_id = p.doctor_id
            AND a.appointment_date = p.appointment_date AND a.start_time = p.appointment_time
        WHERE p.booking_reference = ?
    """, (reference,)).fetchone()
    if not row:
        return None
    return Confirmation(
        reference, " ".join(row[k] for k in ("patient_first_name", "patient_middle_name", "patient_last_name") if row[k]),
        row["doctor_name"], row["clinic_name"], row["purpose_of_visit"], row["appointment_date"],
        row["appointment_time"], row["end_time"], row["booking_status"])


def book_appointment(patient: Patient, purpose, doctor_id, appointment_date, appointment_time,
                     *, other="", reference=None, db_path=DB_PATH, now=None):
    """Recheck after acquiring the write lock. No implicit doctor reassignment.

    A review screen owns one random reference. Retrying an identical request is
    safe, including after a lost response. A changed request needs a new reference.
    """
    day = parse_date(appointment_date, "Appointment date")
    slot_time = parse_time(appointment_time)
    visit = validate_purpose(purpose, other)
    reference = reference or new_reference()
    if not isinstance(reference, str) or not reference.startswith("WC-") or len(reference) != 27:
        raise ValidationError("Invalid booking reference. Please review the appointment again.")
    try:
        with connection(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            clock = normalize_now(now or clinic_now())  # evaluated after lock acquisition
            patient = Patient.validate(patient.first_name, patient.middle_name, patient.last_name,
                                       patient.dob, today=clock.date())
            payload = (patient.first_name, patient.middle_name, patient.last_name, patient.dob.isoformat(),
                       visit, doctor_id, day.isoformat(), slot_time.strftime("%H:%M"))
            prior = conn.execute("SELECT * FROM appointments WHERE booking_reference = ?", (reference,)).fetchone()
            if prior:
                cols = ("patient_first_name", "patient_middle_name", "patient_last_name", "patient_dob",
                        "purpose_of_visit", "doctor_id", "appointment_date", "appointment_time")
                if tuple(prior[k] for k in cols) != payload or prior["booking_status"] != "Confirmed":
                    raise ValidationError("This booking reference is already in use. Please review again.")
                result = _confirmation(conn, reference)
                conn.commit()
                return result
            if datetime.combine(day, slot_time, CLINIC_TIMEZONE) <= clock:
                raise ValidationError("Please choose a future appointment date and time.")
            if not any(s.start_time == appointment_time for s in _slots(conn, day, day, doctor_id, clock)) or doctor_id is None:
                raise SlotUnavailable("That appointment is no longer available. Please choose another time.")
            conn.execute("""INSERT INTO appointments
                (booking_reference, patient_first_name, patient_middle_name, patient_last_name,
                 patient_dob, purpose_of_visit, doctor_id, appointment_date, appointment_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (reference, *payload, clock.astimezone(timezone.utc).isoformat()))
            result = _confirmation(conn, reference)
            conn.commit()
            return result
    except sqlite3.IntegrityError as exc:
        raise SlotUnavailable("That appointment could not be reserved. Please choose another time.") from exc
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise BookingBusy("The booking system is busy. Please try confirming again in a moment.") from exc
        raise
