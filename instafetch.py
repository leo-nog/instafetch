#!/usr/bin/env python3
"""Download all photos from an Instagram profile to media/<profile>."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import LoginRequired

MEDIA_TYPE_PHOTO = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_ALBUM = 8
DEFAULT_ACCOUNTS_FILE = "accounts.json"
DEFAULT_BANNED_FILE = "banned_accounts.txt"
DEFAULT_ACTIVE_ACCOUNT_FILE = "active_account.txt"
DEFAULT_SESSIONS_DIR = "sessions"
DEFAULT_OUTPUT_DIR = "media"


def add_shared_account_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--accounts-file",
        default=DEFAULT_ACCOUNTS_FILE,
        help=f"JSON account pool (default: {DEFAULT_ACCOUNTS_FILE}).",
    )
    parser.add_argument(
        "--banned-file",
        default=DEFAULT_BANNED_FILE,
        help=f"TXT file for banned/failed accounts (default: {DEFAULT_BANNED_FILE}).",
    )
    parser.add_argument(
        "--active-account-file",
        default=DEFAULT_ACTIVE_ACCOUNT_FILE,
        help=f"TXT file for the active account (default: {DEFAULT_ACTIVE_ACCOUNT_FILE}).",
    )
    parser.add_argument(
        "--sessions-dir",
        default=DEFAULT_SESSIONS_DIR,
        help=f"Per-account sessions directory (default: {DEFAULT_SESSIONS_DIR}).",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Instagram profile photos with an account pool."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Download photos from a profile.",
    )
    fetch_parser.add_argument(
        "--profile",
        required=True,
        help="Target profile username (without @).",
    )
    fetch_parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    add_shared_account_args(fetch_parser)

    accounts_parser = subparsers.add_parser(
        "accounts",
        help="List accounts with in_use, banned, and on_queue status.",
    )
    add_shared_account_args(accounts_parser)

    unban_parser = subparsers.add_parser(
        "unban",
        help="Remove an account from banned_accounts.txt.",
    )
    unban_parser.add_argument(
        "username",
        help="Username to remove from the banned list (without @).",
    )
    add_shared_account_args(unban_parser)

    return parser.parse_args()


def require_available_accounts(
    accounts_file: Path,
    banned_file: Path,
) -> list[tuple[str, str]]:
    if not accounts_file.exists():
        print(
            f"File {accounts_file} not found. Copy accounts.example.json to {accounts_file}.",
            file=sys.stderr,
        )
        sys.exit(1)

    banned = load_banned_accounts(banned_file)
    accounts = [
        account
        for account in load_accounts(accounts_file)
        if account[0] not in banned
    ]
    if not accounts:
        print(
            f"No available accounts in {accounts_file}. Add accounts or run unban.",
            file=sys.stderr,
        )
        sys.exit(1)
    return accounts


def load_banned_accounts(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def save_banned_accounts(path: Path, banned: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(sorted(banned)) + ("\n" if banned else ""),
        encoding="utf-8",
    )


def append_banned_account(path: Path, username: str, banned: set[str]) -> None:
    if username in banned:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(f"{username}\n")
    banned.add(username)


def load_active_account(path: Path) -> str | None:
    if not path.exists():
        return None
    username = path.read_text(encoding="utf-8").strip()
    return username or None


def set_active_account(path: Path, username: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{username}\n", encoding="utf-8")


def clear_active_account(path: Path, username: str | None = None) -> None:
    if not path.exists():
        return
    if username is None or load_active_account(path) == username:
        path.unlink(missing_ok=True)


def load_accounts(accounts_file: Path) -> list[tuple[str, str]]:
    if not accounts_file.exists():
        return []

    try:
        data = json.loads(accounts_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {accounts_file}: {exc}") from exc

    if isinstance(data, dict):
        raw_accounts = data.get("accounts", [])
    elif isinstance(data, list):
        raw_accounts = data
    else:
        raise ValueError(
            "Invalid accounts.json format. Use a list or an object with an 'accounts' key."
        )

    accounts: list[tuple[str, str]] = []
    for item in raw_accounts:
        if not isinstance(item, dict):
            continue
        username = str(item.get("ig_username", "")).strip()
        password = str(item.get("ig_password", "")).strip()
        if username and password:
            accounts.append((username, password))
    return accounts


def build_account_status_list(
    accounts_file: Path,
    banned_file: Path,
    active_account_file: Path,
) -> list[dict[str, object]]:
    accounts = load_accounts(accounts_file)
    if not accounts:
        return []

    banned = load_banned_accounts(banned_file)
    active = load_active_account(active_account_file)
    if active in banned:
        active = None

    statuses: list[dict[str, object]] = []
    for username, _ in accounts:
        is_banned = username in banned
        is_in_use = not is_banned and username == active
        is_on_queue = not is_banned and not is_in_use
        statuses.append(
            {
                "ig_username": username,
                "in_use": is_in_use,
                "banned": is_banned,
                "on_queue": is_on_queue,
            }
        )
    return statuses


def login_client(username: str, password: str, session_path: Path) -> Client:
    client = Client()

    if session_path.exists():
        client.load_settings(session_path)
    client.login(username, password)
    client.dump_settings(session_path)
    return client


def download_album_photos_only(
    client: Client,
    media,
    folder: Path,
) -> int:
    """Download only images from a carousel (skip album videos)."""
    if not media.resources:
        media = client.media_info(media.pk)

    count = 0
    for resource in media.resources:
        if resource.media_type != MEDIA_TYPE_PHOTO:
            continue
        filename = f"{media.user.username}_{resource.pk}"
        client.photo_download_by_url(
            str(resource.thumbnail_url),
            filename,
            folder,
        )
        count += 1
    return count


def download_profile_photos(
    client: Client,
    profile: str,
    output_dir: Path,
) -> int:
    try:
        user_id = client.user_id_from_username(profile)
    except Exception as exc:
        print(f"Profile not found: @{profile} ({exc})", file=sys.stderr)
        sys.exit(1)

    destination = output_dir / profile
    destination.mkdir(parents=True, exist_ok=True)

    medias = client.user_medias(user_id, amount=0)
    downloaded = 0

    for media in medias:
        try:
            if media.media_type == MEDIA_TYPE_VIDEO:
                continue
            if media.media_type == MEDIA_TYPE_PHOTO:
                client.photo_download(media.pk, folder=destination)
                downloaded += 1
            elif media.media_type == MEDIA_TYPE_ALBUM:
                downloaded += download_album_photos_only(
                    client, media, destination
                )
        except Exception as exc:
            print(f"Warning: failed to download media {media.pk}: {exc}", file=sys.stderr)

    return downloaded


def run_download_with_account_pool(
    profile: str,
    output_dir: Path,
    accounts_file: Path,
    banned_file: Path,
    active_account_file: Path,
    sessions_dir: Path,
) -> tuple[int, str]:
    banned = load_banned_accounts(banned_file)
    accounts = require_available_accounts(accounts_file, banned_file)

    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_files = {
        username: sessions_dir / f"{username}.json"
        for username, _ in accounts
    }

    active = load_active_account(active_account_file)
    if active and active not in banned:
        accounts.sort(key=lambda item: 0 if item[0] == active else 1)

    for username, password in accounts:
        print(f"Trying account @{username}...")
        session_path = session_files[username]
        try:
            client = login_client(username, password, session_path)
            set_active_account(active_account_file, username)
            count = download_profile_photos(client, profile, output_dir)
            return count, username
        except Exception as exc:
            append_banned_account(banned_file, username, banned)
            clear_active_account(active_account_file, username)
            print(
                f"Account @{username} failed and was added to {banned_file}: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError(
        "No available account could complete the download."
    )


def cmd_fetch(args: argparse.Namespace) -> None:
    profile = args.profile.lstrip("@")
    output_dir = Path(args.output_dir)
    accounts_file = Path(args.accounts_file)
    banned_file = Path(args.banned_file)
    active_account_file = Path(args.active_account_file)
    sessions_dir = Path(args.sessions_dir)

    try:
        count, active_username = run_download_with_account_pool(
            profile=profile,
            output_dir=output_dir,
            accounts_file=accounts_file,
            banned_file=banned_file,
            active_account_file=active_account_file,
            sessions_dir=sessions_dir,
        )
    except LoginRequired:
        print(
            "Invalid session. Remove the account session file and log in again.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dest = output_dir / profile
    print(f"Done with @{active_username}: {count} photo(s) saved to {dest.resolve()}")


def cmd_accounts(args: argparse.Namespace) -> None:
    accounts_file = Path(args.accounts_file)
    banned_file = Path(args.banned_file)
    active_account_file = Path(args.active_account_file)

    try:
        statuses = build_account_status_list(
            accounts_file, banned_file, active_account_file
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not statuses and not accounts_file.exists():
        print(
            f"File {accounts_file} not found.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(json.dumps(statuses, indent=2, ensure_ascii=False))


def cmd_unban(args: argparse.Namespace) -> None:
    username = args.username.lstrip("@")
    banned_file = Path(args.banned_file)
    active_account_file = Path(args.active_account_file)
    banned = load_banned_accounts(banned_file)

    if username not in banned:
        print(f"@{username} is not listed in {banned_file}.")
        return

    banned.remove(username)
    save_banned_accounts(banned_file, banned)
    print(f"@{username} removed from {banned_file}.")

    if load_active_account(active_account_file) == username:
        clear_active_account(active_account_file, username)


def main() -> None:
    args = parse_args()

    if args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "accounts":
        cmd_accounts(args)
    elif args.command == "unban":
        cmd_unban(args)


if __name__ == "__main__":
    main()
