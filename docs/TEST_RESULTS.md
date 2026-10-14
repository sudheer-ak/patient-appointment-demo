# Test results

**Result: 45 passed, 0 failed.** The final recorded run completed in **2.24 seconds** with Python 3.12.14, Streamlit 1.51.0, streamlit-calendar 1.4.0 and pytest 8.4.2 on Linux.

Command:

```bash
python -m pytest -v --junitxml=docs/pytest-results.xml
```

The complete run is preserved in `pytest-results.txt`; JUnit results are in `pytest-results.xml`.

## Requested scenarios

| Scenario | Automated evidence | Result |
| --- | --- | --- |
| Successful booking | `test_successful_booking_and_confirmation_excludes_dob`, `test_ui_full_booking_workflow` | Pass |
| Required fields missing | Parameterized `test_required_fields`, `test_ui_required_fields` | Pass |
| Invalid DOB | Parameterized `test_invalid_dob`, `test_backend_revalidates_patient` | Pass |
| Past appointment date/time | Parameterized `test_past_date_and_time_rejected` | Pass |
| Simultaneous same-doctor/same-slot booking | Two independent SQLite connections, synchronized threads in `test_simultaneous_same_slot_has_exactly_one_winner` | Pass: one confirmed, one unavailable |
| Different doctors at the same time | `test_same_time_different_doctors` | Pass: both confirmed |
| Doctor switching updates availability | `test_doctor_switch_changes_availability`, `test_ui_doctor_switch_and_closed_day` | Pass |
| Any Available Doctor | `test_any_doctor_identified_and_not_silently_reassigned`, complete UI workflow | Pass |
| Restart persistence | `test_restart_persists_appointments` reads the booking in a fresh Python process, then reseeds without losing it | Pass |
| No slots for selected date | `test_no_slots_on_closed_day`, `test_fully_booked_date_has_no_slots`, closed-date UI test | Pass |

Additional checks cover direct SQL uniqueness enforcement, foreign keys, malformed/overlapping schedules, cancelled-record uniqueness behavior, seeding idempotence, optional middle names and Unicode, lunch/off-grid times, inactive doctors, clinic timezone handling, transaction rollback, safe retries, stale-slot recovery in the UI, editing patient details, and injected calendar event callbacks.

## Delivered database check

The packaged database was checkpointed and checked separately from the test databases:

- SQLite integrity check: **ok**.
- Foreign-key violations: **0**.
- Fictional doctors: **4**.
- Seeded appointment slots: **1,566**.
- Patient appointments: **0**.
- Initial schedule range: **October 13–December 11, 2026**. Startup automatically extends the rolling schedule using the current clinic date.

## What was and was not verified

The actual Streamlit application was executed through its AppTest runner. Native forms, doctor and time selectors, the booking service, confirmation, and navigation were exercised. Calendar callback payloads were injected to test Python-side event processing.

A real browser preview was not available, so the calendar iframe's JavaScript rendering/click delivery, responsive desktop/mobile appearance, keyboard focus behavior and screenshots remain unverified. No screenshot files are included, and no local server or hosted deployment is claimed. `MANUAL_QA.md` provides the remaining browser checks.

All test patients are fictional, and tests use temporary databases. No test patient records were included in the delivered database.
