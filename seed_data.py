"""Idempotently extend the rolling demo schedule; never reset appointments."""
import argparse
from datetime import datetime, timedelta, time
from pathlib import Path

from config import (DB_PATH, CLINIC_NAME, CLINIC_OPENS, CLINIC_CLOSES,
                    LUNCH_START, LUNCH_END, SLOT_MINUTES, BOOKING_DAYS, clinic_now)
from database import connection, initialize_database

# Entirely fictional. Weekdays use Monday=0; start/end are intersected with clinic hours.
DOCTORS = (
    (1, "Dr. Maya Rowan", "Family Medicine", (0, 1, 2, 3, 4), time(9), time(17)),
    (2, "Dr. Ethan Vale", "Internal Medicine", (0, 2, 4), time(9), time(15)),
    (3, "Dr. Lena Brooks", "Preventive Medicine", (1, 2, 3, 4), time(10), time(17)),
    (4, "Dr. Noah Ellis", "General Practice", (0, 1, 3, 4, 5), time(9), time(13)),
)


def seed_database(db_path=DB_PATH, *, start_date=None, days=BOOKING_DAYS):
    initialize_database(db_path)
    start_date = start_date or clinic_now().date()
    if SLOT_MINUTES <= 0 or days <= 0 or CLINIC_OPENS >= CLINIC_CLOSES:
        raise ValueError("Use positive slot length/days and same-day clinic hours.")
    rows = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        for doctor_id, _, _, weekdays, opens, closes in DOCTORS:
            if day.weekday() not in weekdays:
                continue
            cursor = datetime.combine(day, max(opens, CLINIC_OPENS))
            end = datetime.combine(day, min(closes, CLINIC_CLOSES))
            while cursor + timedelta(minutes=SLOT_MINUTES) <= end:
                next_slot = cursor + timedelta(minutes=SLOT_MINUTES)
                if not (cursor.time() < LUNCH_END and next_slot.time() > LUNCH_START):
                    rows.append((doctor_id, day.isoformat(), cursor.strftime("%H:%M"), next_slot.strftime("%H:%M")))
                cursor = next_slot
    with connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany("INSERT OR IGNORE INTO doctors VALUES (?, ?, ?, ?, 1)",
                         [(i, name, specialty, CLINIC_NAME) for i, name, specialty, *_ in DOCTORS])
        conn.executemany("""INSERT OR IGNORE INTO doctor_availability
                            (doctor_id, appointment_date, start_time, end_time) VALUES (?, ?, ?, ?)""", rows)
        conn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    seed_database(args.db)
    print(f"Demo doctors and {BOOKING_DAYS} days of schedules are ready: {args.db}")
