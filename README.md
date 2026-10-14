# Willow Creek Clinic

A local patient appointment scheduling demonstration built with **Python, Streamlit, SQLite, and streamlit-calendar**. It includes a five-step booking flow, four fictional doctors, a calendar of available dates, an explicit doctor/time selection, and a confirmation page.

**Use fictional information only.** This is a technical demonstration, not a production healthcare system or a HIPAA-compliant application. It does not schedule real medical appointments.

## 1. Install

Use Python **3.11 or 3.12**. The delivered project was tested with Python 3.12.14. Internet access is needed to install dependencies; the application then uses the local database and packaged calendar component. No API keys or external accounts are needed.

Extract `patient_appointments.zip`, then open a terminal inside the extracted `patient_appointments` folder.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows commands below can use `.\.venv\Scripts\python.exe` in place of `python`; activating the environment is optional.

## 2. Run

```bash
python -m streamlit run app.py
```

Open **http://localhost:8501** in your browser. The included Streamlit configuration binds the server to `127.0.0.1`, keeping it on your computer. Stop it with **Ctrl+C**. Run from the project folder so Streamlit loads `.streamlit/config.toml`.

The initialized `data/clinic.sqlite3` already contains four fictional doctors and 60 days of schedules. At application startup, seeding extends the schedule from the current clinic date without deleting existing bookings. You can also seed explicitly:

```bash
python seed_data.py
```

Restarting the app keeps saved appointments. Refreshing the browser may restart the unfinished form session, but committed appointments remain in SQLite.

## 3. Try a fictional booking

1. Enter **Avery Taylor**, with a fictional date of birth such as **June 15, 1992**. Middle name is optional.
2. Select a visit purpose. Choosing **Other** reveals an optional description.
3. Choose a doctor or **Any Available Doctor**.
4. Click a date with an “open” count in the interactive calendar. The labeled date field below the calendar is an alternate keyboard-friendly input.
5. Choose a time. Every option names the actual doctor, including when browsing all doctors.
6. Review the patient name, doctor, clinic, purpose, date, and time; select **Confirm appointment**.
7. The confirmation shows a unique reference and **Confirmed** status. It does not show date of birth.

Appointments last 30 minutes. All dates and times are interpreted in **America/Los_Angeles**, including daylight-saving time. No appointment is held while a patient is reviewing it. If another patient books it first, confirmation returns the user to the calendar with a useful error.

### Fictional doctor schedules

Times below are Pacific time. Lunch, **12:00–13:00**, is unavailable for every doctor.

| Doctor | Specialty | Days | Schedule before lunch exclusion |
| --- | --- | --- | --- |
| Dr. Maya Rowan | Family Medicine | Monday–Friday | 09:00–17:00 |
| Dr. Ethan Vale | Internal Medicine | Monday, Wednesday, Friday | 09:00–15:00 |
| Dr. Lena Brooks | Preventive Medicine | Tuesday–Friday | 10:00–17:00 |
| Dr. Noah Ellis | General Practice | Monday, Tuesday, Thursday, Friday, Saturday | 09:00–13:00 |

All four work at fictional **Willow Creek Clinic**. All are eligible for every demonstration visit purpose; specialty-based clinical triage is outside this project's scope.

## 4. Project files

| File | Responsibility |
| --- | --- |
| `app.py` | Five-step Streamlit UI, calendar callbacks, review and confirmation |
| `booking.py` | Availability queries, atomic booking, safe retries, confirmation model creation |
| `database.py` | Schema, constraints, indexes, SQLite connection lifecycle |
| `models.py` | Patient validation, purpose validation, slots and confirmation values |
| `seed_data.py` | Idempotent fictional doctor/schedule seeding and CLI |
| `config.py` | Clinic hours, timezone, appointment duration, booking window, database path |
| `data/clinic.sqlite3` | Initialized SQLite database; no patient bookings in the delivered copy |
| `.streamlit/config.toml` | Light teal theme, local server binding, disabled usage telemetry |
| `requirements.txt` | Runtime and test dependencies |
| `tests/` | Booking, database, and Streamlit workflow tests |
| `docs/ARCHITECTURE.md` | Design, schema, booking transaction and tradeoffs |
| `docs/TEST_RESULTS.md` | Coverage mapping, results and verification limits |
| `docs/pytest-results.txt` | Actual verbose test run |
| `docs/pytest-results.xml` | Machine-readable JUnit test results |
| `docs/MANUAL_QA.md` | Browser, mobile, keyboard, and screenshot checks |

## 5. Architecture

Streamlit collects input and displays availability. The Python booking service validates input and queries SQLite. Confirmation runs in a `BEGIN IMMEDIATE` transaction: acquire the write lock, recheck the slot, insert the booking, and commit. A **partial unique index** separately guarantees that a doctor cannot have two confirmed appointments at the same date/time.

The three tables are `doctors`, `doctor_availability`, and `appointments`. Each availability row represents one concrete appointment slot. Appointments reference that exact slot through a composite foreign key. Overlap triggers prevent conflicting schedule intervals. Connections enable foreign keys, use WAL mode and a five-second busy timeout, and close after every operation.

“Any Available Doctor” is a combined list of doctor-specific slots. It never silently assigns or changes a doctor during confirmation. More details are in `docs/ARCHITECTURE.md`.

## 6. Run tests

```bash
python -m pytest -q
```

To produce your own detailed reports:

```bash
python -m pytest -v --junitxml=docs/pytest-results.xml > docs/pytest-results.txt
```

Tests use isolated temporary SQLite databases and fictional patients. They do not populate or clear the bundled demo database. The suite includes simultaneous attempts on one slot, direct database uniqueness checks, separate doctors at the same time, fresh-process persistence, invalid inputs, empty dates, doctor switching, and the full Streamlit booking flow.

**Verification boundary:** Streamlit's AppTest executes the actual application and exercises native widgets. It cannot render the third-party calendar's JavaScript iframe. Browser preview was unavailable in the build environment, so browser screenshots and desktop/mobile visual inspection were not performed. The calendar callback handling is covered with injected event payloads, and the alternate date/time controls are exercised end to end. See the manual browser checklist before presenting the demo.

## 7. Configuration

Edit `config.py` for clinic opening/closing times, the lunch interval, `SLOT_MINUTES` (default 30), `BOOKING_DAYS` (default 60), and timezone. Edit `DOCTORS` in `seed_data.py` for fictional doctor schedules. Only same-day working hours are supported, and the seeder intersects doctor hours with clinic hours and excludes overlapping lunch slots.

Seeding only adds missing schedules and preserves existing data. **After changing schedule configuration, use a fresh demonstration database** so old slots do not conflict with the new schedule. Keep the original database if you want to preserve its bookings.

macOS / Linux:

```bash
CLINIC_DB_PATH=data/alternate_demo.sqlite3 python -m streamlit run app.py
```

Windows PowerShell:

```powershell
$env:CLINIC_DB_PATH = "data/alternate_demo.sqlite3"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The default path is resolved relative to `config.py`, independent of the terminal directory. An environment-provided relative path is relative to the current working directory.

## 8. Boundaries and practical notes

- No admin dashboard, authentication, registration, payments, insurance, messaging, medical records, or external healthcare integrations.
- No live push updates: availability reloads on interaction or **Refresh**; the final transaction is always authoritative.
- SQLite holds fictional names and dates of birth in a local file. Do not enter real patient information or share a database populated with real information.
- Only a confirmed booking occupies a slot. The schema accepts `Cancelled` for future extensibility, but this project has no cancellation UI or service.
- The confirmation stays in the current session. There is no patient lookup or public booking-reference search.
- Names allow Unicode letters, spaces, hyphens, apostrophes and periods, up to 80 characters per field. DOB must be between January 1, 1900 and the current clinic date.
- The responsive layout uses native Streamlit controls and custom CSS; labels remain visible. Full accessibility certification and browser/mobile visual verification are outside the completed checks.
- Do not run this SQLite database from a network-synced/shared folder. Keep it on local disk.

If a port is already in use, run `python -m streamlit run app.py --server.port 8502` and open http://localhost:8502. If the database is unavailable, ensure its parent folder is writable. To restart with an empty demonstration, point `CLINIC_DB_PATH` at a new file; the application creates and seeds it automatically.

## Reference documentation

- Streamlit testing: https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest
- Streamlit calendar component and callback API: https://github.com/im-perativa/streamlit-calendar
- FullCalendar standard calendar: https://fullcalendar.io/docs

The UI uses the standard month grid, not premium resource scheduling views.
