#!/usr/bin/env python3
# Scan all calendar collections for the specified CalDAV user.
# Complete pending tasks due today whose titles include Anki.

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


CALDAV_URL = "http://andrew.local:5232/andrew/"
DEFAULT_USERNAME = "andrew"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_KEYWORD = "Anki"

APP_DIR = (
    Path.home()
    / ".local"
    / "share"
    / "complete-anki-tasks-today"
)

VENV_DIR = APP_DIR / "venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"


def using_managed_venv() -> bool:
    try:
        return (
            Path(sys.executable).resolve()
            == VENV_PYTHON.resolve()
        )
    except OSError:
        return False


def managed_python_has_dependencies() -> bool:
    if not VENV_PYTHON.exists():
        return False

    result = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            (
                "import caldav; "
                "from caldav import get_davclient"
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    return result.returncode == 0


def ensure_runtime() -> None:
    """
    Always use this script's venv to avoid incompatible system caldav versions.
    """

    if using_managed_venv():
        return

    APP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not VENV_PYTHON.exists():
        print(
            "First run: creating a virtual environment: "
            f"{VENV_DIR}"
        )

        subprocess.run(
            [
                sys.executable,
                "-m",
                "venv",
                str(VENV_DIR),
            ],
            check=True,
        )

    if not managed_python_has_dependencies():
        print(
            "Installing or repairing dependencies: "
            "caldav 3.2.1、tzdata……"
        )

        subprocess.run(
            [
                str(VENV_PYTHON),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--upgrade",
                "caldav==3.2.1",
                "tzdata",
            ],
            check=True,
        )

    os.execve(
        str(VENV_PYTHON),
        [
            str(VENV_PYTHON),
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
        os.environ.copy(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan all collections belonging to the current CalDAV user and "
            "complete pending tasks due today whose titles contain the specified keyword."
        )
    )

    parser.add_argument(
        "--username",
        default=os.environ.get(
            "CALDAV_USERNAME",
            DEFAULT_USERNAME,
        ),
        help=(
            "CalDAV username"
            f"(default: {DEFAULT_USERNAME})"
        ),
    )

    parser.add_argument(
        "--timezone",
        default=os.environ.get(
            "TASK_TIMEZONE",
            DEFAULT_TIMEZONE,
        ),
        help=(
            "Timezone used to determine today"
            f"(default: {DEFAULT_TIMEZONE})"
        ),
    )

    parser.add_argument(
        "--keyword",
        default=DEFAULT_KEYWORD,
        help=(
            "Case-sensitive text required in task titles"
            f"(default: {DEFAULT_KEYWORD})"
        ),
    )

    parser.add_argument(
        "--date",
        dest="target_date",
        help=(
            "Target date YYYY-MM-DD; "
            "defaults to the current date"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only; do not modify any tasks",
    )

    return parser.parse_args()


def component_property(
    component: Any,
    name: str,
) -> Any | None:
    prop = component.get(name)

    if prop is None:
        return None

    return getattr(
        prop,
        "dt",
        prop,
    )


def due_local_date(
    component: Any,
    local_tz: Any,
) -> date | None:
    due = component_property(
        component,
        "DUE",
    )

    if isinstance(due, datetime):
        if due.tzinfo is None:
            due = due.replace(
                tzinfo=local_tz
            )

        return due.astimezone(
            local_tz
        ).date()

    if isinstance(due, date):
        return due

    if isinstance(due, str):
        try:
            return date.fromisoformat(
                due[:10]
            )
        except ValueError:
            return None

    return None


def task_component(todo: Any) -> Any:
    component = getattr(
        todo,
        "icalendar_component",
        None,
    )

    if component is not None:
        return component

    component = getattr(
        todo,
        "component",
        None,
    )

    if component is not None:
        return component

    raise RuntimeError(
        "Task object has no readable VTODO component"
    )


def is_pending(component: Any) -> bool:
    status = str(
        component.get(
            "STATUS",
            "NEEDS-ACTION",
        )
    ).upper()

    return (
        status
        not in {
            "COMPLETED",
            "CANCELLED",
        }
        and component.get("COMPLETED")
        is None
    )


def calendar_name(calendar: Any) -> str:
    getter = getattr(
        calendar,
        "get_display_name",
        None,
    )

    if callable(getter):
        try:
            value = getter()

            if value:
                return str(value)
        except Exception:
            pass

    value = getattr(
        calendar,
        "name",
        None,
    )

    if value and not callable(value):
        return str(value)

    url = str(
        getattr(
            calendar,
            "url",
            "",
        )
        or ""
    )

    path = urlparse(
        url
    ).path.rstrip("/")

    if path:
        return unquote(
            path.rsplit(
                "/",
                1,
            )[-1]
        )

    return "Unnamed collection"


def get_principal(client: Any) -> Any:
    getter = getattr(
        client,
        "get_principal",
        None,
    )

    if callable(getter):
        return getter()

    return client.principal()


def get_calendars(principal: Any) -> list[Any]:
    getter = getattr(
        principal,
        "get_calendars",
        None,
    )

    if callable(getter):
        return list(getter())

    return list(
        principal.calendars()
    )


def get_pending_todos(
    calendar: Any,
) -> list[Any]:
    getter = getattr(
        calendar,
        "get_todos",
        None,
    )

    if callable(getter):
        return list(
            getter(
                include_completed=False
            )
        )

    return list(
        calendar.todos(
            include_completed=False
        )
    )


def main() -> int:
    ensure_runtime()

    import caldav
    from zoneinfo import (
        ZoneInfo,
        ZoneInfoNotFoundError,
    )

    args = parse_args()

    try:
        local_tz = ZoneInfo(
            args.timezone
        )
    except ZoneInfoNotFoundError:
        print(
            "Error: timezone not found: "
            f"{args.timezone!r}",
            file=sys.stderr,
        )
        return 2

    if args.target_date:
        try:
            target_date = date.fromisoformat(
                args.target_date
            )
        except ValueError:
            print(
                "Error: --date must use "
                "YYYY-MM-DD format.",
                file=sys.stderr,
            )
            return 2
    else:
        target_date = datetime.now(
            local_tz
        ).date()

    password = os.environ.get(
        "CALDAV_PASSWORD"
    )

    if password is None:
        password = getpass.getpass(
            "Enter the password for CalDAV user "
            f"{args.username}: "
        )

    if not password:
        print(
            "Error: password must not be empty.",
            file=sys.stderr,
        )
        return 2

    matched: list[
        tuple[
            Any,
            str,
            str,
            str,
            date,
        ]
    ] = []

    successful_collections = 0
    failed_collections = 0
    total_pending = 0

    try:
        with caldav.get_davclient(
            url=CALDAV_URL,
            username=args.username,
            password=password,
        ) as client:
            principal = get_principal(
                client
            )

            calendars = get_calendars(
                principal
            )

            print(
                "Principal："
                f"{getattr(principal, 'url', CALDAV_URL)}"
            )

            print(
                f"Found {len(calendars)} "
                "Calendar Collections："
            )

            for index, calendar in enumerate(
                calendars,
                start=1,
            ):
                name = calendar_name(
                    calendar
                )

                collection_url = str(
                    getattr(
                        calendar,
                        "url",
                        "",
                    )
                    or ""
                )

                print(
                    f"  [{index}/"
                    f"{len(calendars)}] "
                    f"{name}"
                )

                print(
                    f"      URL："
                    f"{collection_url}"
                )

                try:
                    todos = get_pending_todos(
                        calendar
                    )
                except Exception as exc:
                    failed_collections += 1

                    print(
                        "      Skipping: could not read tasks: "
                        f"{exc}",
                        file=sys.stderr,
                    )
                    continue

                successful_collections += 1
                total_pending += len(todos)

                print(
                    "      Pending tasks: "
                    f"{len(todos)}"
                )

                for todo in todos:
                    try:
                        component = task_component(
                            todo
                        )
                    except Exception as exc:
                        print(
                            "      Skipping an unparseable task: "
                            f"{exc}",
                            file=sys.stderr,
                        )
                        continue

                    summary = str(
                        component.get(
                            "SUMMARY",
                            "",
                        )
                    )

                    if args.keyword not in summary:
                        continue

                    if not is_pending(component):
                        continue

                    due_date = due_local_date(
                        component,
                        local_tz,
                    )

                    if due_date != target_date:
                        continue

                    uid = str(
                        component.get(
                            "UID",
                            getattr(
                                todo,
                                "id",
                                "No UID",
                            ),
                        )
                    )

                    matched.append(
                        (
                            todo,
                            summary,
                            uid,
                            name,
                            due_date,
                        )
                    )

            print(
                "\nCollection scan complete: "
                f"Succeeded: {successful_collections}，"
                f"Failed: {failed_collections}，"
                f"Pending tasks read: {total_pending} pending tasks."
            )

            print(
                f"Date: {target_date.isoformat()}"
                f"({args.timezone})"
            )

            print(
                f"Keyword: {args.keyword!r}"
            )

            print(
                f"Matched {len(matched)} tasks:"
            )

            for index, item in enumerate(
                matched,
                start=1,
            ):
                (
                    _,
                    summary,
                    uid,
                    name,
                    due_date,
                ) = item

                print(
                    f"  {index}. {summary}  "
                    f"[Collection: {name}; "
                    f"Due: {due_date}; "
                    f"UID: {uid}]"
                )

            if args.dry_run:
                print(
                    "\nPreview mode: "
                    "No tasks were modified."
                )
                return 0

            completed = 0
            failed = 0

            completion_time = datetime.now(
                timezone.utc
            )

            for item in matched:
                (
                    todo,
                    summary,
                    uid,
                    name,
                    _,
                ) = item

                try:
                    todo.complete(
                        completion_timestamp=(
                            completion_time
                        ),
                        handle_rrule=True,
                        rrule_mode="safe",
                    )

                    completed += 1

                    print(
                        f"Completed: {summary}  "
                        f"[Collection: {name}; "
                        f"UID: {uid}]"
                    )

                except Exception as exc:
                    failed += 1

                    print(
                        f"Could not complete: {summary} "
                        f"[Collection: {name}; "
                        f"UID: {uid}]：{exc}",
                        file=sys.stderr,
                    )

    except Exception as exc:
        print(
            f"CalDAV operation failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        "\nProcessing complete: "
        f"Succeeded: {completed}，"
        f"Failed: {failed}。"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
