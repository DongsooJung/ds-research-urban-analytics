"""Publish an explicitly dated name reference; never rewrite the population snapshot."""
import argparse
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seoul_citydata.admin_names import HEADER, SOURCE_URL, parse_name_reference


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("--month", required=True)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--collected-at", required=True)
    p.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs")
    args = p.parse_args()
    if datetime.datetime.fromisoformat(args.collected_at).tzinfo is None:
        raise ValueError("Collection time must include timezone")
    original = args.snapshot.read_bytes()
    snapshot = json.loads(original)
    if args.month > snapshot["month"]:
        raise ValueError("Name reference is later than the snapshot")
    codes = [r["행정동코드"] for r in snapshot["rows"]]
    if len(codes) != len(set(codes)) or len(codes) != snapshot["dong_count"]:
        raise ValueError("Snapshot code uniqueness/count mismatch")
    result = parse_name_reference(args.archive.read_bytes(), args.month, set(codes))
    result.update({"source": {"url": SOURCE_URL, "download_url": "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false", "post_fields": {"infId": "DOWNLOAD", "infSeq": "4", "seq": "18"}},
                   "collected_at": args.collected_at, "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "for_snapshot": {"month": snapshot["month"], "date": snapshot["reference_date"], "hour": snapshot["reference_hour"], "sha256_lf": hashlib.sha256(original.replace(b"\r\n", b"\n")).hexdigest()},
                   "scope": "Names in the official reference month only; exact code-set match does not establish names/boundaries at the later observation date.",
                   "names_effective_at_observation": "not_verified", "historical_comparability": "not_established"})
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(result["rows"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = "native-admin-names-" + args.month
    for suffix, text in [(".json", json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"), (".csv", buf.getvalue())]:
        file = args.output_dir / (stem + suffix)
        temp = file.with_suffix(file.suffix + ".tmp")
        with temp.open("w", encoding="utf-8-sig" if suffix == ".csv" else "utf-8", newline="") as stream:
            stream.write(text)
        temp.replace(file)
    print(json.dumps({"reference_month": result["reference_month"], "matched_codes": result["code_count"], "population_changed": False}))


if __name__ == "__main__":
    main()
