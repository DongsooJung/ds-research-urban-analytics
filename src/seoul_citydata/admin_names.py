"""Read the separately dated official name reference without changing population rows."""
import csv
import hashlib
import io
import re
import zipfile

HEADER = ["SIDO_NM", "SGG_NM", "ADMI_NM", "ADMI_CD", "FULL_NM", "BASE_YM"]
SOURCE_URL = "https://data.seoul.go.kr/dataVisual/seoul/seoulLivingPopulation.do"


def parse_name_reference(raw: bytes, month: str, expected_codes: set[str]) -> dict:
    if not re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", month):
        raise ValueError("Invalid name reference month")
    if not expected_codes or any(not re.fullmatch(r"11\d{6}", c) for c in expected_codes):
        raise ValueError("Invalid target codes")
    member = f"SEOUL_ADMI/ADMI_{month}.csv"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist().count(member) != 1:
            raise ValueError("Missing or duplicate monthly reference member")
        if archive.getinfo(member).file_size > 10_000_000:
            raise ValueError("Reference file too large")
        csv_raw = archive.read(member)
    reader = csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig")))
    if reader.fieldnames != HEADER:
        raise ValueError("Name reference schema changed")
    selected, seen, nationwide = [], set(), 0
    for row in reader:
        if None in row or any(not row.get(key, "").strip() for key in HEADER):
            raise ValueError("Missing name reference fields")
        row = {key: row[key].strip() for key in HEADER}
        code = row["ADMI_CD"]
        if row["BASE_YM"] != month or not re.fullmatch(r"\d{8}", code):
            raise ValueError("Name reference month/code mismatch")
        if code in seen:
            raise ValueError("Duplicate name reference code")
        seen.add(code)
        nationwide += 1
        if code.startswith("11") != (row["SIDO_NM"] == "서울특별시"):
            raise ValueError("Province/code mismatch")
        if code.startswith("11"):
            if row["FULL_NM"] != " ".join(row[k] for k in ("SIDO_NM", "SGG_NM", "ADMI_NM")):
                raise ValueError("Full name mismatch")
            selected.append(row)
    if {r["ADMI_CD"] for r in selected} != expected_codes:
        raise ValueError("Reference code set does not exactly match snapshot")
    return {"reference_month": month[:4] + "-" + month[4:], "rows": sorted(selected, key=lambda r: r["ADMI_CD"]),
            "code_count": len(selected), "archive_sha256": hashlib.sha256(raw).hexdigest(),
            "member": member, "member_sha256": hashlib.sha256(csv_raw).hexdigest(),
            "validation": {"nationwide_rows": nationwide, "duplicate_codes": 0, "missing_codes": 0, "extra_codes": 0}}
