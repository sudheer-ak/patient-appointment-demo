# Browser check and screenshot guide

These checks are provided for the local demonstration. They have **not** been marked as passed by automated tests. Use only fictional information.

1. Start `python -m streamlit run app.py` and open http://localhost:8501.
2. At desktop width (about 1440 pixels), inspect the white/teal layout, step navigation, form labels, doctor cards and appointment summary.
3. Capture `01-patient-details.png` before entering any data.
4. Use Avery Taylor / June 15, 1992 as fictional patient data. Choose a purpose and capture `02-doctors.png` on the doctor-selection screen.
5. Choose Any Available Doctor. Check calendar month navigation, date clicking, clicking an availability badge, and the keyboard-accessible alternate date field. Check that choosing a date updates the time/doctor list. Capture `03-calendar.png`.
6. Choose a time and capture `04-review.png`. Confirm, then capture `05-confirmation.png`. Verify DOB is absent and the actual doctor and reference are visible.
7. Start a second fictional booking. Verify the reserved doctor/time is absent while another doctor at the same time can still be booked.
8. In two separate browser sessions, bring the same slot to the review screen. Confirm in session A, then B. B should return to the calendar with an availability error.
9. Change doctors: choose Ethan Vale, then a Tuesday. Expect no slots. Switch to Maya Rowan and use a future Tuesday; expect available slots.
10. Resize to 390 pixels wide. Inspect stacked columns, readable labels, the full calendar toolbar, time selection and confirmation without page-level horizontal overflow. Capture `06-mobile.png` if useful.
11. Use Tab/Shift+Tab and keyboard controls through the native inputs and buttons. Check visible focus and use the date/time fields as the alternate calendar path.
12. Stop and restart Streamlit. Begin another booking and verify the earlier reserved slot remains unavailable.

Save screenshots only from the fictional demonstration. The original delivered database contains no patient bookings; test-created bookings during manual inspection will remain in your local database.
