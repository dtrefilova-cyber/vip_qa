"""Читає журнал Betking / 777 / Vegas і друкує CSV проблем.

Нічого не змінює, доки немає --fix-safe і явного підтвердження.
Не чіпає аркуші «Гайди», «Менеджери VIP», «Зведення», «Правки».
«Менеджери VIP» лише читається.
"""

from __future__ import annotations

import argparse
import csv
import sys

from vip_journal_sheets import (
    JOURNAL_LAYOUT,
    VIP_JOURNAL_MANAGERS_WORKSHEET,
    _READ_ONLY_SHEETS,
    apply_safe_fixes,
    audit_block,
    block_layout,
    load_journal_managers,
    plan_safe_fixes,
    qualified_range,
)


def _read_block(book, route: dict, call_type: str) -> list[dict]:
    from vip_journal_sheets import _row_map, _values_batch

    block = block_layout(call_type)
    title = route["title"]
    worksheet = book.get_worksheet_by_id(int(route["sheet_id"]))
    if worksheet.title in _READ_ONLY_SHEETS:
        raise SystemExit(f"Аркуш {worksheet.title} не входить в аудит запису.")
    last = int(worksheet.row_count)
    data_ref = qualified_range(title, f"{block['start']}{route['start_row']}:{block['end']}{last}")
    formula_letter = block["formula"]["letter"]
    formula_ref = qualified_range(title, f"{formula_letter}{route['start_row']}:{formula_letter}{last}")
    data_rows = _values_batch(book, [data_ref], "UNFORMATTED_VALUE")[0]
    formula_values = _values_batch(book, [formula_ref], "FORMULA")[0]
    mapped = []
    for offset, row in enumerate(data_rows):
        item = _row_map(row, block["start"])
        formula = ""
        if offset < len(formula_values) and formula_values[offset]:
            formula = formula_values[offset][0]
        item[formula_letter] = formula
        mapped.append(item)
    return mapped


def collect(google_client) -> tuple[list[dict], list[dict], object]:
    from vip_journal_sheets import _open_book

    book = _open_book(google_client)
    directory = load_journal_managers(google_client)
    issues = []
    plans = []
    for key, route in JOURNAL_LAYOUT["projects"].items():
        full = {"key": key, **route}
        for call_type in ("short", "friendly"):
            rows = _read_block(book, full, call_type)
            issues.extend(
                audit_block(
                    sheet_title=route["title"],
                    call_type=call_type,
                    rows=rows,
                    start_row=route["start_row"],
                    directory=directory,
                    project_key=key,
                )
            )
            plans.extend(
                plan_safe_fixes(
                    sheet_title=route["title"],
                    call_type=call_type,
                    rows=rows,
                    start_row=route["start_row"],
                    directory=directory,
                    project_key=key,
                    sheet_id=route["sheet_id"],
                )
            )
    return issues, plans, book


def _print_issues(issues: list[dict]) -> None:
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["sheet", "block", "row", "client_id", "issue", "detail"],
    )
    writer.writeheader()
    writer.writerows(issues)


def _print_plan(plans: list[dict]) -> None:
    print("План безпечних виправлень:", file=sys.stderr)
    if not plans:
        print("немає", file=sys.stderr)
        return
    for plan in plans:
        print(
            f"{plan['sheet']} рядок {plan['row']} {plan['letter']} → {plan['value']!r} ({plan['reason']})",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Аудит журналу VIP. За замовчуванням лише читання.")
    parser.add_argument(
        "--fix-safe",
        action="store_true",
        help="Дописати порожній TL і замінити N/M, якщо бал у тексті збігається з клітинкою.",
    )
    args = parser.parse_args(argv)
    from google_sheets import connect_google

    client = connect_google()
    issues, plans, book = collect(client)
    _print_issues(issues)
    if not args.fix_safe:
        return 0
    _print_plan(plans)
    if not plans:
        return 0
    if not sys.stdin.isatty():
        print("Немає підтвердження в терміналі. Виправлення не застосовано.", file=sys.stderr)
        return 1
    answer = input("Застосувати ці виправлення? так/ні: ").strip().casefold()
    if answer != "так":
        print("Скасовано.", file=sys.stderr)
        return 1
    for plan in plans:
        if plan["sheet"] in _READ_ONLY_SHEETS or plan["sheet"] == VIP_JOURNAL_MANAGERS_WORKSHEET:
            raise SystemExit("Безпечне виправлення не пише в довідник і службові аркуші.")
    apply_safe_fixes(book, plans)
    print(f"Застосовано {len(plans)}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
