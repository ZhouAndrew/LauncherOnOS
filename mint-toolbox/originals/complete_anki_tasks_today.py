#!/usr/bin/env python3
# 扫描指定用户的全部 CalDAV Calendar Collections，
# 完成今天到期且标题包含 Anki 的未完成任务。

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
    始终使用脚本自己的 venv，避免误用系统中较旧或错误的 caldav。
    """

    if using_managed_venv():
        return

    APP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not VENV_PYTHON.exists():
        print(
            "首次运行：正在创建虚拟环境："
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
            "正在安装或修复依赖："
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
            "扫描当前用户名下的全部 CalDAV Collections，"
            "完成今天到期且标题包含指定关键词的未完成任务。"
        )
    )

    parser.add_argument(
        "--username",
        default=os.environ.get(
            "CALDAV_USERNAME",
            DEFAULT_USERNAME,
        ),
        help=(
            "CalDAV 用户名"
            f"（默认：{DEFAULT_USERNAME}）"
        ),
    )

    parser.add_argument(
        "--timezone",
        default=os.environ.get(
            "TASK_TIMEZONE",
            DEFAULT_TIMEZONE,
        ),
        help=(
            "判断“今天”所用的时区"
            f"（默认：{DEFAULT_TIMEZONE}）"
        ),
    )

    parser.add_argument(
        "--keyword",
        default=DEFAULT_KEYWORD,
        help=(
            "任务标题必须包含的文字，区分大小写"
            f"（默认：{DEFAULT_KEYWORD}）"
        ),
    )

    parser.add_argument(
        "--date",
        dest="target_date",
        help=(
            "指定处理日期 YYYY-MM-DD；"
            "省略时使用当前日期"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览，不修改任何任务",
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
        "任务对象不包含可读取的 VTODO component"
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

    return "未命名 Collection"


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
            "错误：找不到时区 "
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
                "错误：--date 必须使用 "
                "YYYY-MM-DD 格式。",
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
            "请输入 CalDAV 用户 "
            f"{args.username} 的密码："
        )

    if not password:
        print(
            "错误：密码不能为空。",
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
                f"发现 {len(calendars)} 个 "
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
                        "      跳过：读取任务失败："
                        f"{exc}",
                        file=sys.stderr,
                    )
                    continue

                successful_collections += 1
                total_pending += len(todos)

                print(
                    "      未完成任务："
                    f"{len(todos)} 个"
                )

                for todo in todos:
                    try:
                        component = task_component(
                            todo
                        )
                    except Exception as exc:
                        print(
                            "      跳过一个无法解析的任务："
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
                                "无 UID",
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
                "\nCollection 扫描完成："
                f"成功 {successful_collections} 个，"
                f"失败 {failed_collections} 个，"
                f"共读取 {total_pending} 个未完成任务。"
            )

            print(
                f"日期：{target_date.isoformat()}"
                f"（{args.timezone}）"
            )

            print(
                f"关键词：{args.keyword!r}"
            )

            print(
                f"匹配到 {len(matched)} 个任务："
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
                    "\n预览模式："
                    "未修改任何任务。"
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
                        f"已完成：{summary}  "
                        f"[Collection: {name}; "
                        f"UID: {uid}]"
                    )

                except Exception as exc:
                    failed += 1

                    print(
                        f"完成失败：{summary} "
                        f"[Collection: {name}; "
                        f"UID: {uid}]：{exc}",
                        file=sys.stderr,
                    )

    except Exception as exc:
        print(
            f"CalDAV 操作失败：{exc}",
            file=sys.stderr,
        )
        return 1

    print(
        "\n处理结束："
        f"成功 {completed} 个，"
        f"失败 {failed} 个。"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
