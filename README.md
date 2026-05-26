# instafetch

Python CLI to download all photos from an Instagram profile using [instagrapi](https://github.com/subzeroid/instagrapi).

## Requirements

- Python 3.10+
- Instagram account(s) in `accounts.json` (login required for the private API)

## Installation

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy accounts.example.json accounts.json
```

Edit `accounts.json` with your Instagram credentials.

### Windows: venv activation error in PowerShell

If you see *"running scripts is disabled on this system"*, use one of these options:

**Option A — without activating the venv** (recommended; does not change system policies):

```powershell
.venv\Scripts\python.exe instafetch.py fetch --profile instagram_user
```

**Option B — Command Prompt (cmd)** instead of PowerShell:

```cmd
.venv\Scripts\activate.bat
pip install -r requirements.txt
python instafetch.py fetch --profile instagram_user
```

**Option C — allow scripts for your user only** (one-time):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

After that, `.venv\Scripts\activate` works in PowerShell.

## Usage

```powershell
.venv\Scripts\python.exe instafetch.py fetch --profile instagram_user
```

With cmd and the venv activated: `python instafetch.py fetch --profile instagram_user`.

Photos are saved to `media/instagram_user/`. The active account session is stored in `sessions/<ig_username>.json`.

### Commands

```powershell
# Download photos from a profile
.venv\Scripts\python.exe instafetch.py fetch --profile instagram_user

# List accounts with status
.venv\Scripts\python.exe instafetch.py accounts

# Remove account from the banned list
.venv\Scripts\python.exe instafetch.py unban account_1
```

`accounts` output:

```json
[
  {
    "ig_username": "account_1",
    "in_use": true,
    "banned": false,
    "on_queue": false
  },
  {
    "ig_username": "account_2",
    "in_use": false,
    "banned": true,
    "on_queue": false
  },
  {
    "ig_username": "account_3",
    "in_use": false,
    "banned": false,
    "on_queue": true
  }
]
```

Flags:

| Flag | Meaning |
|------|---------|
| `in_use` | Currently active account (last successful login) |
| `banned` | Listed in `banned_accounts.txt` |
| `on_queue` | Available and waiting to be used |

## Account pool (accounts.json)

Create `accounts.json` from `accounts.example.json`:

```json
{
  "accounts": [
    { "ig_username": "abc", "ig_password": "def" }
  ]
}
```

Flow:

- The script tries to log in with the first available account (or the `in_use` account, if still valid).
- Each account session is saved to `sessions/<ig_username>.json`.
- The active account is recorded in `active_account.txt`.
- If an account fails (login/download), it is added to `banned_accounts.txt`.
- The script automatically moves on to the next account.

### Options

| Command / option | Description |
|------------------|-------------|
| `fetch --profile` | Target username (required) |
| `accounts` | List accounts with `in_use`, `banned`, `on_queue` flags |
| `unban <username>` | Remove account from `banned_accounts.txt` |
| `--output-dir` | Base output folder (default: `media`) |
| `--accounts-file` | Accounts JSON (default: `accounts.json`) |
| `--banned-file` | Banned/failed accounts TXT (default: `banned_accounts.txt`) |
| `--active-account-file` | Active account TXT (default: `active_account.txt`) |
| `--sessions-dir` | Per-account sessions folder (default: `sessions`) |

## Notes

- Only **photos** and **album/carousel** images are downloaded; videos and Reels are skipped.
- Respect Instagram's terms of use and only access profiles you are allowed to.
