"""Streamlit execution tests. Third-party iframe rendering needs a real browser."""
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from config import clinic_now
from database import connection

APP = Path(__file__).resolve().parents[1] / "app.py"

@pytest.fixture
def app(tmp_path):
    path = tmp_path / "ui.sqlite3"
    with patch("config.DB_PATH", path):
        import booking
        original_book, original_slots, original_doctors = booking.book_appointment, booking.get_available_slots, booking.get_doctors
        with patch("booking.book_appointment", side_effect=lambda *a, **k: original_book(*a, **(k | {"db_path": path}))), \
             patch("booking.get_available_slots", side_effect=lambda *a, **k: original_slots(*a, **(k | {"db_path": path}))), \
             patch("booking.get_doctors", side_effect=lambda: original_doctors(path)):
            at = AppTest.from_file(str(APP), default_timeout=20).run()
            yield at, path


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def complete_details(at):
    at.text_input[0].input("Avery")
    at.text_input[2].input("Taylor")
    at.date_input[0].set_value(date(1992, 6, 15))
    click(at, "Continue to visit")
    click(at, "Continue to doctors")


def test_ui_required_fields(app):
    at, _ = app
    assert not at.exception
    click(at, "Continue to visit")
    assert at.error
    assert at.session_state.step == 1


def test_ui_full_booking_workflow(app):
    at, path = app
    complete_details(at)
    assert at.selectbox[0].value is None
    click(at, "Continue to calendar")
    time_picker = next(s for s in at.selectbox if s.label == "Choose a time and doctor")
    from booking import get_available_slots
    first_slot = get_available_slots(at.session_state.chosen_date)[0]
    time_picker.select(first_slot.key).run()
    assert not at.exception
    click(at, "Review appointment")
    assert "Dr." in " ".join(m.value for m in at.markdown)
    click(at, "Confirm appointment")
    assert at.session_state.step == 6
    visible = " ".join(m.value for m in at.markdown)
    assert "Confirmed" in visible
    assert "1992-06-15" not in visible
    with connection(path) as conn:
        assert conn.execute("SELECT count(*) FROM appointments").fetchone()[0] == 1
    click(at, "Book another appointment")
    assert at.session_state.step == 1
    assert not at.text_input[0].value


def test_ui_doctor_switch_and_closed_day(app):
    at, _ = app
    complete_details(at)
    at.selectbox[0].select(2).run()
    click(at, "Continue to calendar")
    today = clinic_now().date()
    tuesday = today + timedelta(days=(1 - today.weekday()) % 7 or 7)
    at.date_input[0].set_value(tuesday).run()
    assert not at.exception
    assert any("No available appointments" in m.value for m in at.info)
    assert next(b for b in at.button if b.label == "Review appointment").disabled
    click(at, "Back")
    at.selectbox[0].select(1).run()
    click(at, "Continue to calendar")
    at.date_input[0].set_value(tuesday).run()
    assert any(s.label == "Choose a time and doctor" for s in at.selectbox)
    assert "slot" not in at.session_state


def select_first_time(at):
    from booking import get_available_slots
    slot = get_available_slots(at.session_state.chosen_date,
                               doctor_id=at.session_state.selected_doctor)[0]
    next(s for s in at.selectbox if s.label == "Choose a time and doctor").select(slot.key).run()
    assert not at.exception
    return slot


def test_ui_stale_slot_returns_to_calendar(app):
    at, path = app
    complete_details(at)
    click(at, "Continue to calendar")
    slot = select_first_time(at)
    click(at, "Review appointment")
    from booking import book_appointment
    from models import Patient
    book_appointment(Patient("Morgan", "", "Sample", date(1990, 2, 3)), "Follow-up",
                     slot.doctor_id, slot.appointment_date, slot.start_time)
    click(at, "Confirm appointment")
    assert at.session_state.step == 4
    assert any("no longer available" in error.value for error in at.error)
    assert next(b for b in at.button if b.label == "Review appointment").disabled
    with connection(path) as conn:
        assert conn.execute("SELECT count(*) FROM appointments").fetchone()[0] == 1


def test_ui_calendar_callback_and_date_picker_do_not_replay_old_click(app):
    at, _ = app
    complete_details(at)
    click(at, "Continue to calendar")
    today = clinic_now().date()
    target = today + timedelta(days=3)
    payload = {"callback": "eventClick", "eventClick": {"event": {"start": target.isoformat()}}}
    with patch("streamlit_calendar.calendar", return_value=payload):
        at.run()
        assert not at.exception
        assert at.date_input[0].value == target
    different = today + timedelta(days=5)
    with patch("streamlit_calendar.calendar", return_value={}):
        at.date_input[0].set_value(different).run()
        assert at.date_input[0].value == different
    # The same calendar date remains clickable after using the alternate picker.
    with patch("streamlit_calendar.calendar", return_value=payload):
        at.run()
        assert not at.exception
        assert at.date_input[0].value == target


def test_ui_edit_patient_keeps_saved_details(app):
    at, _ = app
    complete_details(at)
    click(at, "Back")
    click(at, "Back")
    assert at.text_input[0].value == "Avery"
    assert at.text_input[2].value == "Taylor"
    assert at.date_input[0].value == date(1992, 6, 15)
