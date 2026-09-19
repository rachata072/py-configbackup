# Py-ConfigBackup

A Netmiko-based command-line tool that connects to every device in an inventory file over SSH, pulls the running configuration, saves a timestamped backup, diffs it against the previous backup, and (optionally) sends an email alert when something changed.

I built this because "did anyone touch the router config" is a question that should never require someone to remember what it looked like last week. This tool keeps that history automatically and tells me the moment something is different.

## What it does

1. Reads a CSV inventory of devices (hostname, IP, platform, SSH credentials by reference to environment variables, never a plaintext password in the file itself).
2. Connects to each device with [Netmiko](https://github.com/ktbyers/netmiko) and pulls its running configuration.
3. Saves the config as a timestamped file under `backups/<hostname>/`.
4. Diffs the new backup against the most recent previous one using Python's `difflib`.
5. If anything changed, builds a summary of every changed device and diff, and emails it via Gmail SMTP with an App Password.
6. Exits with a status code that reflects what happened, so it's safe to run from `cron` or a CI pipeline and alert on failure separately from alerting on a config change.

## Why it's useful in a real environment

Config drift is one of the most common causes of "it worked yesterday" outages: someone makes a manual change on a device outside of a documented maintenance window, doesn't tell anyone, and it isn't discovered until something breaks. A scheduled run of this tool (nightly, hourly, whatever fits) means every config change gets a timestamp, a diff, and a notification, without anyone having to remember to go check.

See [MEETING-SCRIPT.md](MEETING-SCRIPT.md) for the specific incident this addresses and who it affects in a real org, and [INTERVIEW-STAR.md](INTERVIEW-STAR.md) for how I talk about it in an interview.

## Requirements

- Python 3.10+
- A Gmail account with an App Password, if email alerts are wanted (optional; the tool works fine with `--no-email`)
- Network devices reachable over SSH. I tested this against a free two-node VyOS lab built with [containerlab](https://containerlab.dev/); the full lab build steps are in [RUNBOOK.md](RUNBOOK.md). Netmiko also supports Cisco IOS/IOS-XE, Arista EOS, Juniper Junos, and a long list of other platforms without any code changes, since the platform-specific "show config" command is looked up from a small map in `backup.py`.

## Install

```bash
git clone https://github.com/rachata072/py-configbackup.git
cd py-configbackup
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Inventory file format

CSV with these columns:

| Column | Required | Meaning |
|---|---|---|
| `hostname` | yes | A unique name for the device; used as the folder name under `backups/`. |
| `ip` | yes | The management IP or hostname to SSH to. |
| `device_type` | yes | Netmiko platform string, e.g. `cisco_ios`, `vyos`, `arista_eos`. |
| `username` | yes | SSH username. |
| `port` | no | SSH port, defaults to 22. |
| `password_env` | one of these two | Name of an environment variable holding the SSH password. Preferred over `password`. |
| `password` | one of these two | A literal password in the CSV. Only meant for a throwaway lab; the tool prints a warning every time this is used. |
| `secret_env` | no | Name of an environment variable holding an enable/privileged-mode secret, for platforms that need one. |

See `examples/inventory.csv` for a working example against the lab in RUNBOOK.md.

## Usage

```bash
configbackup --inventory my-inventory.csv --backup-dir backups
```

Flags:

- `--inventory PATH` (required): path to the inventory CSV.
- `--backup-dir PATH` (default `backups`): where timestamped backups are stored, one subfolder per device.
- `--no-email`: skip sending an alert even if something changed. Useful for a dry run, or if email isn't configured yet.

Exit codes:

- `0`: ran cleanly. Every device in the inventory was backed up, whether or not anything changed.
- `1`: at least one device could not be reached or backed up.
- `2`: bad arguments or an unusable inventory file. No devices were touched.

## Screenshots

<!-- screenshots/03-first-run-baseline.png -->
![First run baseline output](screenshots/03-first-run-baseline.png)

<!-- screenshots/04-change-detected.png -->
![Change detected output](screenshots/04-change-detected.png)

More screenshots, and the full walkthrough that produced them, are in [RUNBOOK.md](RUNBOOK.md).

## Email alerts

Set these environment variables (see `.env.example`):

```bash
CONFIGBACKUP_SMTP_HOST=smtp.gmail.com
CONFIGBACKUP_SMTP_PORT=587
CONFIGBACKUP_SMTP_USERNAME=youraddress@gmail.com
CONFIGBACKUP_SMTP_APP_PASSWORD=xxxxxxxxxxxxxxxx
CONFIGBACKUP_ALERT_FROM=youraddress@gmail.com
CONFIGBACKUP_ALERT_TO=youraddress@gmail.com
```

`CONFIGBACKUP_SMTP_APP_PASSWORD` must be a Gmail App Password, not the account's normal password; RUNBOOK.md walks through generating one. The email is only sent when at least one device's diff is non-empty, so a normal no-change run produces no email at all.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

All 42 tests run against a mocked Netmiko `ConnectHandler` and a mocked `smtplib.SMTP`, so they run in well under a second and never touch a real device or send a real email. That also means they run the same whether or not the lab from RUNBOOK.md happens to be up.

## Project layout

```
src/configbackup/
  inventory.py    # load + validate the CSV inventory
  backup.py       # Netmiko connection + platform-specific "show config" commands
  diffing.py      # timestamped backup storage + unified diff
  alert.py        # SMTP email alert (Gmail App Password)
  cli.py          # argparse entry point, ties the above together
  exceptions.py   # this package's own exception types
tests/            # pytest suite, one file per module above
examples/         # example inventory.csv matching the RUNBOOK lab
```

## What I'd add next

- A `--dry-run` flag that connects and diffs but never writes a backup file, for testing inventory changes safely.
- Config retention/pruning (right now every backup is kept forever, which is fine for a lab but would need a cleanup policy on a large fleet).
- Slack/Teams webhook alerts as an alternative to email.
- A "break the diff on purpose" test against a second platform (Cisco IOS) once I have one available, to confirm the platform-specific command map actually works beyond VyOS.

## License

MIT, see [LICENSE](LICENSE).
