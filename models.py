"""Validated inputs and immutable values; no Streamlit dependency."""
from dataclasses import dataclass
from datetime import date, datetime, time
import re

from config import CLINIC_TIMEZONE, MIN_BIRTH_YEAR

PURPOSES = ("General Consultation", "Follow-up", "Annual Checkup", "Other")


class ValidationError(ValueError):
    """An input that can be corrected by the patient."""


class SlotUnavailable(ValidationError):
    """Availability changed or the selected slot is not bookable."""


class BookingBusy(RuntimeError):
    """A competing database writer has not finished; retry safely."""


def parse_date(value, label="Date") -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValidationError(f"{label} must be a valid date.")


def parse_time(value) -> time:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValidationError("Appointment time must use HH:MM.")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("Appointment time is invalid.") from exc


def normalize_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("A timezone-aware clock is required.")
    return now.astimezone(CLINIC_TIMEZONE)


def clean_name(value, label, required=True):
    value = " ".join(str(value or "").split())
    if required and not value:
        raise ValidationError(f"Please enter your {label.lower()}.")
    if len(value) > 80 or any(not (c.isalpha() or c in " '-.’") for c in value):
        raise ValidationError(f"{label} must be at most 80 characters and contain letters, spaces, apostrophes, periods or hyphens.")
    if value and not any(c.isalpha() for c in value):
        raise ValidationError(f"Please enter a valid {label.lower()}.")
    return value


@dataclass(frozen=True)
class Patient:
    first_name: str
    middle_name: str
    last_name: str
    dob: date

    @classmethod
    def validate(cls, first_name, middle_name, last_name, dob, *, today):
        first = clean_name(first_name, "First name")
        middle = clean_name(middle_name, "Middle name", required=False)
        last = clean_name(last_name, "Last name")
        birth = parse_date(dob, "Date of birth")
        if birth > today or birth < date(MIN_BIRTH_YEAR, 1, 1):
            raise ValidationError(f"Date of birth must be between January 1, {MIN_BIRTH_YEAR} and today.")
        return cls(first, middle, last, birth)

    @property
    def full_name(self):
        return " ".join(v for v in (self.first_name, self.middle_name, self.last_name) if v)


def validate_purpose(purpose, other=""):
    if purpose not in PURPOSES:
        raise ValidationError("Please choose a purpose of visit.")
    other = " ".join(str(other or "").split())
    if len(other) > 300:
        raise ValidationError("Please keep your visit description under 300 characters.")
    return f"Other: {other}" if purpose == "Other" and other else purpose


@dataclass(frozen=True)
class Slot:
    doctor_id: int
    doctor_name: str
    specialty: str
    clinic_name: str
    appointment_date: str
    start_time: str
    end_time: str

    @property
    def key(self):
        return f"{self.doctor_id}|{self.appointment_date}|{self.start_time}"

    @property
    def label(self):
        start = parse_time(self.start_time).strftime("%I:%M %p").lstrip("0")
        return f"{start} · {self.doctor_name}"


@dataclass(frozen=True)
class Confirmation:
    """Safe presentation model: deliberately does not carry date of birth."""
    booking_reference: str
    patient_name: str
    doctor_name: str
    clinic_name: str
    purpose_of_visit: str
    appointment_date: str
    appointment_time: str
    end_time: str
    booking_status: str
