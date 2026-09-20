# Screenshots

All captured against a real containerlab + VyOS lab, RUNBOOK.md walked through end to end on 2026-09-19.

- `01-containerlab-deploy.png` - `containerlab deploy` output showing both lab nodes up with their management IPs (RUNBOOK.md Part 3).
- `02-pytest-passing.png` - `pytest -v` output showing all tests passing (RUNBOOK.md Part 5). Captured before the noise-filtering fix in `backup.py` was added, so it shows 42 items collected rather than the current 46; the extra 4 came from a real bug (see `06.png` below) found after this screenshot was taken.
- `03-first-run-baseline.png` - first `configbackup` run against the fresh lab, showing "first backup saved" for both devices (RUNBOOK.md Part 8).
- `04-change-detected.png` - second run after changing `lab-r1`'s hostname, showing `lab-r1` as CHANGED and `lab-r2` as no change (RUNBOOK.md Part 9).
- `05-alert-email.png` - the alert email itself, showing the diff in the message body (RUNBOOK.md Part 9).
- `06.png` - bonus screenshot, `find backups -type f` plus a raw `diff` between `lab-r1`'s two backups (RUNBOOK.md Part 10). This is also the screenshot that caught a real bug: a stray `sudo: unable to resolve host lab-r1: System error` line and a `[?2004l` terminal-control line, both leaked into the actual saved backup files from the live SSH session. Neither is part of VyOS's real configuration. Fixed in `backup.py` with an explicit noise-line filter, see INTERVIEW-STAR.md Story 6 and BLOG-POST.md's "A second bug, found only by testing against a real device" section for the full writeup.
