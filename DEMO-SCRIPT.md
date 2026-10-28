# Demo video shot list (target 2:45, hard limit 3:00)

Record on the hosted Space (or locally with your key, not the stub). Screen at 1280x800 or larger,
browser zoom 110%, a terminal tab ready with the server log. Have the three samples from
`examples/` on disk, including `stat3120_applied_regression.pdf`.

| # | Time | On screen | Say (roughly) |
|---|---|---|---|
| 1 | 0:00-0:15 | The three sample syllabi side by side in a text editor; highlight "Week 10, Wednesday", "TBA" and a deadline buried in a paragraph. | "Every term starts with five syllabi in five formats. Getting them into a calendar takes an evening, and the clashes show up too late." |
| 2 | 0:15-0:30 | Termplan home page. Point at the status pill showing the Nemotron model on Token Factory. Open `/api/health` in a second tab for two seconds. | "Termplan reads them with NVIDIA Nemotron on Nebius Token Factory. Here is the model ID and the Token Factory endpoint it is calling." |
| 3 | 0:30-0:50 | Upload the STAT PDF with the file picker; paste or load BIO and HIST (or "Load 3 sample syllabi" and remove STAT, then upload the PDF). Set term dates; click "Build my plan". | "A PDF and two pasted syllabi, three different date styles." |
| 4 | 0:50-1:05 | While it runs, switch to the terminal: the `nemotron call model=... mode=json_schema finish=stop latency=...` log lines, one per course, in parallel. | "One Nemotron call per course, in parallel, through the OpenAI-compatible API with JSON-schema output." |
| 5 | 1:05-1:25 | Results: stats row and coach notes. | "Every dated item, how many quotes were verified, the crunch weeks ahead, and a second Nemotron pass that writes advice from the finished plan." |
| 6 | 1:25-1:45 | "All deadlines" tab; click a row to reveal the source quote; scroll to "No date yet". | "Every item carries the exact sentence it came from, and the app checks that sentence really is in the syllabus. TBA items stay out of the calendar." |
| 7 | 1:45-2:05 | "Agent log" tab: show a course that needed a repair (if none did live, say so and show the attempt count and checks passed). | "If the model returns broken JSON, a bad time, a paraphrased quote or a date outside the term, the app sends the exact errors back and Nemotron repairs its output." |
| 8 | 2:05-2:20 | "Conflicts" tab: back-to-back exams, the crunch week of Nov 2. | "Then plain code checks across courses: back-to-back exams, deadline pile-ups, crunch weeks." |
| 9 | 2:20-2:35 | "Study plan" tab: crunch badge, bars, a "start by" date and an "h short" warning. Then "Next 7 days". | "The plan starts crunch-week work early, and tells me honestly when my budget is too small." |
| 10 | 2:35-2:50 | Click "Download .ics", open it in Calendar or Google Calendar import; open one event showing the quote. | "One click and it is in my calendar, with the syllabus quote in every event." |
| 11 | 2:50-3:00 | README section "How Nemotron and Token Factory are used", then the GitHub URL. | "Open source, MIT. Termplan." |

Checklist before recording:
- `.env` has your key; `scripts/check_models.py` passes; `/api/health` shows `mode: nebius`.
- "Plan from" date = the recording day (default), so "Next 7 days" shows the late-October items.
- Close other tabs and notifications; do not show the API key anywhere (not in `.env`, not in the Space settings).
