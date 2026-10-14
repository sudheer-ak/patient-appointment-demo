"""Patient-facing Streamlit demo. Run: python -m streamlit run app.py"""
from collections import Counter
from datetime import date, timedelta
from html import escape
from pathlib import Path
import logging
import sqlite3

import streamlit as st
from streamlit_calendar import calendar

from booking import book_appointment, get_available_slots, get_doctors, new_reference
from config import DB_PATH, CLINIC_NAME, CLINIC_TIMEZONE, BOOKING_DAYS, MIN_BIRTH_YEAR, clinic_now
from models import Patient, PURPOSES, ValidationError, SlotUnavailable, BookingBusy, parse_time, validate_purpose
from seed_data import seed_database

st.set_page_config(page_title="Book a visit | Willow Creek", page_icon="✚", layout="wide", initial_sidebar_state="collapsed")

CSS = """
<style>
.block-container {max-width:1160px;padding-top:2rem;padding-bottom:3rem;}
header[data-testid="stHeader"] {background:transparent;}
h1,h2,h3 {letter-spacing:-.035em;color:#183C46;}
h1 {font-size:2.65rem!important;font-weight:650!important;line-height:1.15!important;}
p,label {line-height:1.6;}
.brand {display:flex;align-items:center;gap:12px;font-weight:700;font-size:19px;}
.brandmark {display:grid;place-items:center;background:#087F82;color:white;border-radius:13px;width:43px;height:43px;font-size:28px;}
.topbar {display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #E3ECEC;padding-bottom:23px;margin-bottom:30px;}
.eyebrow {font-size:11px;font-weight:750;letter-spacing:.13em;color:#55747A;text-transform:uppercase;}
.badge {font-size:11px;font-weight:650;background:#EDF7F6;color:#17686A;border:1px solid #D5E9E7;border-radius:30px;padding:7px 12px;}
.subtle {color:#5C747B;font-size:15px;}
.steps {display:flex;gap:8px;margin:24px 0 34px;}
.step {flex:1;border-top:3px solid #E3ECEC;padding-top:10px;font-size:12px;color:#687D83;}
.step.active {border-color:#087F82;color:#075E61;font-weight:700;}
.step.done {border-color:#8AC7BF;}
.panel {border:1px solid #DDEAE9;border-radius:20px;padding:26px;background:#F4FAF9;margin-bottom:18px;}
.panel.white {background:white;padding:20px;}
.panel h3 {font-size:1.25rem;margin:4px 0 12px;}
.fact {padding:13px 0;border-bottom:1px solid #DDEAE9;}
.fact:last-child {border:0;}
.fact small {display:block;font-size:11px;letter-spacing:.06em;color:#5D767C;text-transform:uppercase;margin-bottom:4px;}
.fact strong {font-size:15px;font-weight:600;overflow-wrap:anywhere;}
.note {font-size:12px;color:#617980;line-height:1.6;}
.doc {border:1px solid #E0EBEA;border-radius:14px;padding:16px;min-height:170px;margin-bottom:12px;}
.doc.selected {border-color:#087F82;background:#F0F9F7;}
.doc h4 {margin:0 0 4px;font-size:16px;}
.doc p {font-size:13px;color:#547078;margin:0 0 5px;}
.avatar {width:34px;height:34px;background:#DDEFEA;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:700;margin-bottom:10px;color:#146B65;}
.success-icon {width:58px;height:58px;background:#DBF0E8;border-radius:50%;color:#16765E;display:grid;place-items:center;font-size:29px;margin-bottom:20px;}
.footer {border-top:1px solid #E3ECEC;padding-top:18px;margin-top:34px;display:flex;justify-content:space-between;gap:12px;color:#70848A;font-size:11px;}
div[data-testid="stForm"] {border:0;padding:0;}
div[data-testid="stButton"] button,div[data-testid="stFormSubmitButton"] button {border-radius:10px;min-height:44px;font-weight:600;}
div[data-testid="stTextInput"] input {min-height:43px;}
@media(max-width:640px) {.block-container {padding:1rem!important;}h1 {font-size:2rem!important;}.steps {gap:5px;}.step {font-size:10px;}.panel {padding:20px;}.topbar {margin-bottom:22px;}.brand {font-size:16px;}.badge {font-size:9px;padding:6px 8px;}.footer {flex-direction:column;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def bootstrap(path, today):
    seed_database(Path(path), start_date=today)
    return True


def go(step):
    st.session_state.step = step


def clear_time():
    for key in ("slot", "reference", "slot_choice"):
        st.session_state.pop(key, None)


def date_changed():
    clear_time()
    st.session_state.chosen_date = st.session_state.date_picker
    st.session_state.calendar_version += 1
    st.session_state.pop("last_calendar_result", None)


def doctor_changed():
    clear_time()
    st.session_state.selected_doctor = st.session_state.doctor_choice
    st.session_state.chosen_date = None
    st.session_state.calendar_version += 1
    st.session_state.pop("last_calendar_result", None)


def facts(items):
    return "".join(f'<div class="fact"><small>{escape(label)}</small><strong>{escape(str(value))}</strong></div>'
                   for label, value in items)


def time_label(value):
    return parse_time(value).strftime("%I:%M %p").lstrip("0")


def date_label(value):
    return date.fromisoformat(str(value)).strftime("%A, %B %d, %Y")


def reset_booking():
    for key in list(st.session_state):
        del st.session_state[key]


def summary():
    patient = st.session_state.get("patient")
    slot = st.session_state.get("slot")
    items = [("Patient", patient.full_name if patient else "Your details come first"),
             ("Visit", st.session_state.get("purpose", "Choose a reason for your visit"))]
    if slot:
        items += [("Doctor", slot.doctor_name), ("Date", date_label(slot.appointment_date)),
                  ("Time", f"{time_label(slot.start_time)} – {time_label(slot.end_time)}")]
    else:
        items += [("Appointment", "Choose a doctor, then a time")]
    st.markdown('<div class="panel"><div class="eyebrow">YOUR APPOINTMENT</div><h3>A little planning.<br>A healthier you.</h3>'
                + facts(items) + '<p class="note">All appointment times are in America/Los_Angeles (Pacific time).</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="panel white"><div class="eyebrow">WHAT TO EXPECT</div><p>30 minutes, just for you.</p>'
                '<p class="note">Choose from four fictional doctors. Review every detail before reserving your visit.</p>'
                '<p class="note">Demo only. Please enter fictional patient information.</p></div>', unsafe_allow_html=True)


def patient_screen(today):
    st.subheader("Let's start with you")
    st.caption("Enter fictional patient information. Fields marked * are required.")
    saved = st.session_state.get("patient")
    with st.form("patient_form"):
        first = st.text_input("First name *", value=saved.first_name if saved else "", max_chars=80, placeholder="e.g. Avery", key="patient_first")
        middle = st.text_input("Middle name (optional)", value=saved.middle_name if saved else "", max_chars=80, key="patient_middle")
        last = st.text_input("Last name *", value=saved.last_name if saved else "", max_chars=80, placeholder="e.g. Taylor", key="patient_last")
        dob = st.date_input("Date of birth *", value=saved.dob if saved else None,
                            min_value=date(MIN_BIRTH_YEAR, 1, 1), max_value=today, format="MM/DD/YYYY", key="patient_dob")
        st.caption("Date of birth is saved with the demo booking, but is never shown on the confirmation.")
        st.form_submit_button("Continue to visit", type="primary", use_container_width=True, on_click=save_patient)
    if st.session_state.get("patient_error"):
        st.error(st.session_state.pop("patient_error"))


def save_patient():
    try:
        st.session_state.patient = Patient.validate(
            st.session_state.patient_first, st.session_state.patient_middle,
            st.session_state.patient_last, st.session_state.patient_dob, today=clinic_now().date())
    except ValidationError as exc:
        st.session_state.patient_error = str(exc)
    else:
        st.session_state.pop("reference", None)
        go(2)


def purpose_screen():
    st.subheader("What brings you in?")
    st.caption("Choose the option that best describes your visit.")
    purpose = st.radio("Purpose of visit", PURPOSES, index=PURPOSES.index(st.session_state.get("purpose", PURPOSES[0])), key="purpose_choice")
    other = ""
    if purpose == "Other":
        other = st.text_area("Brief description (optional)", value=st.session_state.get("other", ""), max_chars=300,
                             placeholder="Use a fictional reason for this demonstration.", key="other_choice")
    left, right = st.columns([1, 2])
    left.button("Back", use_container_width=True, on_click=go, args=(1,))
    right.button("Continue to doctors", type="primary", use_container_width=True, on_click=save_purpose)


def save_purpose():
    st.session_state.purpose = st.session_state.purpose_choice
    st.session_state.other = st.session_state.get("other_choice", "") if st.session_state.purpose_choice == "Other" else ""
    st.session_state.pop("reference", None)
    go(3)


def doctor_screen(today):
    st.subheader("Find the right person for your visit")
    st.caption("Have a preference? Choose a doctor, or see everyone's availability.")
    doctors = get_doctors()
    options = [None] + [d["doctor_id"] for d in doctors]
    names = {d["doctor_id"]: f'{d["doctor_name"]} · {d["specialty"]}' for d in doctors}
    selected = st.session_state.get("selected_doctor")
    st.selectbox("Choose your doctor", options, index=options.index(selected) if selected in options else 0,
                 format_func=lambda i: names.get(i, "Any Available Doctor"), key="doctor_choice", on_change=doctor_changed)
    selected = st.session_state.doctor_choice
    st.session_state.selected_doctor = selected
    if selected is None:
        st.info("See appointments across all doctors. The doctor for your chosen time will be shown before you confirm.")
    all_slots = get_available_slots(today, today + timedelta(days=BOOKING_DAYS - 1))
    columns = st.columns(2)
    for index, doc in enumerate(doctors):
        slots = [s for s in all_slots if s.doctor_id == doc["doctor_id"]]
        next_visit = f'{date.fromisoformat(slots[0].appointment_date).strftime("%b %d")} at {time_label(slots[0].start_time)}' if slots else "No appointments in this window"
        available_days = sorted({date.fromisoformat(s.appointment_date).weekday() for s in slots})
        days = " · ".join(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[d] for d in available_days)
        initials = "".join(n[0] for n in doc["doctor_name"].split()[1:])
        with columns[index % 2]:
            st.markdown(f'<div class="doc {"selected" if selected == doc["doctor_id"] else ""}"><div class="avatar">{initials}</div>'
                        f'<h4>{escape(doc["doctor_name"])}</h4><p>{escape(doc["specialty"])}</p><p>{escape(doc["clinic_name"])}</p>'
                        f'<p>{days}</p><p><b>Next:</b> {next_visit}</p></div>', unsafe_allow_html=True)
    left, right = st.columns([1, 2])
    left.button("Back", use_container_width=True, on_click=go, args=(2,))
    right.button("Continue to calendar", type="primary", use_container_width=True, on_click=go, args=(4,))


def appointment_screen(today):
    st.subheader("Make time for your health")
    st.caption("Choose an available date, then an appointment. All times are Pacific time.")
    selected_doctor = st.session_state.get("selected_doctor")
    end = today + timedelta(days=BOOKING_DAYS - 1)
    all_slots = get_available_slots(today, end, selected_doctor)
    counts = Counter(s.appointment_date for s in all_slots)
    chosen = st.session_state.get("chosen_date")
    if not chosen or chosen < today or chosen > end:
        chosen = date.fromisoformat(next(iter(counts))) if counts else today
        st.session_state.chosen_date = chosen
    events = [{"id": day, "title": f"{count} open", "start": day, "allDay": True,
               "backgroundColor": "#E5F3EF", "borderColor": "#E5F3EF", "textColor": "#146A62"}
              for day, count in counts.items()]
    result = calendar(events=events, options={
        "initialView": "dayGridMonth", "initialDate": chosen.isoformat(),
        "headerToolbar": {"left": "prev,next", "center": "title", "right": "today"},
        "validRange": {"start": today.isoformat(), "end": (end + timedelta(days=1)).isoformat()},
        "height": 440, "fixedWeekCount": False, "showNonCurrentDates": False,
        "editable": False, "selectable": False, "dayMaxEvents": 1, "firstDay": 0,
        "buttonText": {"today": "Today"},
    }, callbacks=["dateClick", "eventClick"], key=f'calendar-{selected_doctor}-{st.session_state.calendar_version}',
        custom_css=""".fc {font-family:system-ui,sans-serif;font-size:12px;}
        .fc .fc-toolbar-title {font-size:19px;color:#183C46;}
        .fc .fc-button-primary {background:#087F82;border-color:#087F82;}
        .fc .fc-daygrid-day.fc-day-today {background:#F0F8F7;}
        .fc .fc-daygrid-event {border-radius:4px;padding:2px;cursor:pointer;}
        .fc .fc-daygrid-day-number {padding:7px;}
        .fc-theme-standard td,.fc-theme-standard th {border-color:#E2ECEA;}
        @media(max-width:500px){.fc {font-size:10px;}.fc .fc-toolbar-title {font-size:15px;}}
        """)
    # Process each component payload only once; unrelated Streamlit reruns must not
    # replay an old click and override the keyboard-friendly date picker below.
    if result and result != st.session_state.get("last_calendar_result"):
        st.session_state.last_calendar_result = result
        raw = None
        if result.get("callback") == "dateClick":
            raw = result.get("dateClick", {}).get("date")
        elif result.get("callback") == "eventClick":
            raw = result.get("eventClick", {}).get("event", {}).get("start")
        if raw:
            try:
                clicked = date.fromisoformat(raw[:10])
                if today <= clicked <= end:
                    chosen = clicked
                    st.session_state.chosen_date = chosen
                    st.session_state.date_picker = chosen
                    clear_time()
            except (ValueError, TypeError):
                pass
    st.date_input("Appointment date", value=chosen, min_value=today, max_value=end, format="MM/DD/YYYY",
                  key="date_picker", on_change=date_changed,
                  help="You can also use this field to select a date with the keyboard.")
    chosen = st.session_state.date_picker
    slots = [s for s in all_slots if s.appointment_date == chosen.isoformat()]
    st.markdown(f"**Available appointments · {chosen.strftime('%A, %B %d')}**")
    if not slots:
        st.info("No available appointments on this date. Try another date or doctor.")
        clear_time()
    else:
        by_key = {s.key: s for s in slots}
        if st.session_state.get("slot_choice") not in by_key:
            st.session_state.pop("slot_choice", None)
        key = st.selectbox("Choose a time and doctor", list(by_key), index=None,
                           format_func=lambda k: by_key[k].label, key="slot_choice", placeholder="Select an appointment")
        if key:
            st.session_state.slot = by_key[key]
            st.caption(f"Selected: {by_key[key].doctor_name} · {by_key[key].clinic_name} · {time_label(by_key[key].start_time)} Pacific time")
        else:
            st.session_state.pop("slot", None)
            st.session_state.pop("reference", None)
    left, middle, right = st.columns([1, 1, 2])
    left.button("Back", use_container_width=True, on_click=go, args=(3,))
    middle.button("Refresh", use_container_width=True, on_click=refresh_slots)
    right.button("Review appointment", type="primary", use_container_width=True,
                 disabled=not st.session_state.get("slot"), on_click=prepare_review)


def refresh_slots():
    clear_time()
    st.session_state.calendar_version += 1
    st.session_state.pop("last_calendar_result", None)


def prepare_review():
    st.session_state.reference = new_reference()
    go(5)


def review_screen():
    slot = st.session_state.slot
    st.subheader("One last look")
    st.caption("Check your appointment details before confirming. Your time is reserved only after confirmation.")
    items = [("Patient", st.session_state.patient.full_name), ("Doctor", slot.doctor_name),
             ("Clinic", slot.clinic_name), ("Purpose", validate_purpose(st.session_state.purpose, st.session_state.get("other", ""))),
             ("Date", date_label(slot.appointment_date)),
             ("Time", f"{time_label(slot.start_time)} – {time_label(slot.end_time)} · Pacific time")]
    st.markdown('<div class="panel white">' + facts(items) + '</div>', unsafe_allow_html=True)
    if st.session_state.get("booking_error"):
        st.error(st.session_state.pop("booking_error"))
    left, right = st.columns([1, 2])
    left.button("Change appointment", use_container_width=True, on_click=go, args=(4,))
    right.button("Confirm appointment", type="primary", use_container_width=True, on_click=confirm_booking)


def confirm_booking():
    slot = st.session_state.slot
    try:
        result = book_appointment(st.session_state.patient, st.session_state.purpose, slot.doctor_id,
                                  slot.appointment_date, slot.start_time, other=st.session_state.get("other", ""),
                                  reference=st.session_state.reference)
    except SlotUnavailable as exc:
        st.session_state.booking_error = str(exc)
        clear_time()
        st.session_state.calendar_version += 1
        go(4)
    except (ValidationError, BookingBusy) as exc:
        st.session_state.booking_error = str(exc)
    except sqlite3.DatabaseError:
        # No patient data or SQL parameters go to the log.
        logging.error("Booking persistence error")
        st.session_state.booking_error = "We couldn't save your appointment. Please try again."
    else:
        st.session_state.confirmation = result
        go(6)


def confirmation_screen():
    result = st.session_state.confirmation
    st.markdown('<div class="success-icon">✓</div>', unsafe_allow_html=True)
    st.title("You're all booked.")
    st.write("Your appointment is confirmed. Keep your booking reference for this demonstration.")
    items = [("Status", result.booking_status), ("Booking reference", result.booking_reference),
             ("Patient", result.patient_name), ("Doctor", result.doctor_name), ("Clinic", result.clinic_name),
             ("Purpose", result.purpose_of_visit), ("Date", date_label(result.appointment_date)),
             ("Time", f"{time_label(result.appointment_time)} – {time_label(result.end_time)} · Pacific time")]
    st.markdown('<div class="panel">' + facts(items) + '</div>', unsafe_allow_html=True)
    st.caption("Demo confirmation only. No email or SMS has been sent.")
    st.button("Book another appointment", type="primary", on_click=reset_booking)


def main():
    today = clinic_now().date()
    try:
        bootstrap(str(DB_PATH), today)
    except sqlite3.Error:
        st.error("The local appointment database is unavailable. Check that the data folder is writable, then restart.")
        st.stop()
    for key, value in {"step": 1, "calendar_version": 0}.items():
        st.session_state.setdefault(key, value)
    st.markdown('<div class="topbar"><div class="brand"><span class="brandmark">✚</span>Willow Creek<span style="font-weight:400">Clinic</span></div>'
                '<span class="badge">FICTIONAL CLINIC · DEMO</span></div>', unsafe_allow_html=True)
    step = st.session_state.step
    if step == 6:
        left, right = st.columns([1.8, 1], gap="large")
        with left:
            confirmation_screen()
        with right:
            st.markdown('<div class="panel white"><div class="eyebrow">ALL SET</div><h3>Care starts with a plan.</h3>'
                        '<p class="subtle">Your selected doctor and appointment time have been saved.</p>'
                        '<p class="note">This is a local technical demonstration. It does not schedule a real medical appointment.</p></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="eyebrow">BOOK A VISIT · STEP {step} OF 5</div>', unsafe_allow_html=True)
        st.title("Your care, on your schedule.")
        st.markdown('<p class="subtle">A few simple steps to your next appointment.</p>', unsafe_allow_html=True)
        labels = ["Your details", "Your visit", "Your doctor", "Date & time", "Review"]
        st.markdown('<div class="steps">' + ''.join(f'<div class="step {"active" if i == step else "done" if i < step else ""}">{i:02d} &nbsp; {label}</div>'
                    for i, label in enumerate(labels, 1)) + '</div>', unsafe_allow_html=True)
        left, right = st.columns([1.8, 1], gap="large")
        with left:
            if step == 4 and st.session_state.get("booking_error"):
                st.error(st.session_state.pop("booking_error"))
            {1: lambda: patient_screen(today), 2: purpose_screen,
             3: lambda: doctor_screen(today), 4: lambda: appointment_screen(today), 5: review_screen}[step]()
        with right:
            summary()
    st.markdown('<div class="footer"><span>Willow Creek Clinic · Patient appointments</span>'
                '<span>Fictional information only · Local demonstration</span></div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
