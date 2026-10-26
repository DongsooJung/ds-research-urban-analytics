"""Import the official 250m-based native population archive without joining legacy codes."""
from __future__ import annotations
import calendar
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATASET_URL = "https://data.seoul.go.kr/dataList/OA-23016/A/1/datasetView.do"
AGES = ["0~9세", "10~14세", "15~19세", "20~24세", "25~29세", "30~34세", "35~39세", "40~44세", "45~49세", "50~54세", "55~59세", "60~64세", "65~69세", "70세 이상"]
HEADER = ["일자", "시간", "행정동코드", "생활인구합계"] + [sex + " " + age for sex in ("남자", "여자") for age in AGES]

def number(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid population number") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("Population must be finite and nonnegative")
    return parsed

def import_archive(file: Path, month: str, *, strict_month: bool = True) -> dict:
    if not re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", month):
        raise ValueError("Invalid source month")
    raw = file.read_bytes()
    seen = set()
    counts = Counter()
    code_sets = defaultdict(set)
    masked = Counter()
    selected = []
    last = ("", "")
    members = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in sorted(archive.namelist()):
            match = re.fullmatch(r"250_LOCAL_RESD_ADMDONG_(\d{8})\.csv", member)
            if not match or not match[1].startswith(month):
                raise ValueError("Unexpected source ZIP member")
            members.append(member)
            with archive.open(member) as stream:
                text = io.TextIOWrapper(stream, encoding="cp949")
                if next(csv.reader([next(text)])) != HEADER:
                    raise ValueError("Native source schema changed")
                # The official archive uses a comma header and semicolon data rows.
                for values in csv.reader(text, delimiter=";"):
                    if not values:
                        continue
                    if len(values) != len(HEADER):
                        raise ValueError("Native source row width changed")
                    values = [v.strip() for v in values]
                    day, hour, code = values[:3]
                    if day != match[1] or not re.fullmatch(r"[0-2]\d", hour) or int(hour) > 23:
                        raise ValueError("Source date/hour mismatch")
                    if not re.fullmatch(r"11\d{6}", code):
                        raise ValueError("Unexpected administrative code")
                    key = (day, hour, code)
                    if key in seen:
                        raise ValueError("Duplicate date/hour/code")
                    seen.add(key)
                    counts[(day, hour)] += 1
                    code_sets[(day, hour)].add(code)
                    total = number(values[3])  # A masked total cannot be summed.
                    for label, value in zip(HEADER[4:], values[4:]):
                        if value == "*":
                            masked[label] += 1
                        else:
                            number(value)
                    if "*" not in values[4:] and total != sum(map(number, values[4:])):
                        raise ValueError("Unmasked age/sex values do not match total")
                    stamp = (day, hour)
                    if stamp > last:
                        last, selected = stamp, []
                    if stamp == last:
                        selected.append(values)
    if not selected:
        raise ValueError("Empty official archive")
    days = calendar.monthrange(int(month[:4]), int(month[4:]))[1]
    expected = {(f"{month}{day:02d}", f"{hour:02d}") for day in range(1, days + 1) for hour in range(24)}
    if strict_month and set(counts) != expected:
        raise ValueError("Incomplete month date/hour coverage")
    if any(codes != code_sets[last] for codes in code_sets.values()):
        raise ValueError("Administrative coverage changed within source month")
    selected.sort(key=lambda row: row[2])
    return {
        "month": month,
        "reference_date": last[0],
        "reference_hour": last[1],
        "total_population_exact": str(sum(number(row[3]) for row in selected)),
        "dong_count": len(selected),
        "rows": [dict(zip(HEADER, row)) for row in selected],
        "validation": {"archive_sha256": hashlib.sha256(raw).hexdigest(), "archive_bytes": len(raw), "member_count": len(members), "rows_checked": len(seen), "date_hours": len(counts), "per_hour_min": min(counts.values()), "per_hour_max": max(counts.values()), "monthly_masked_cells": dict(masked), "selected_masked_cells": sum(v == "*" for row in selected for v in row[4:]), "age_sex_rates": None, "scope": "Last date/hour snapshot; not a monthly sum or average. Suppressed values remain *. No legacy code/name join."},
    }
