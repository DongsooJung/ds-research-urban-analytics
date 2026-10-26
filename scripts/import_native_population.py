"""Build a separate native-population snapshot from an official downloaded ZIP."""
import argparse
import csv
import datetime
import io
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seoul_citydata.native_population import DATASET_URL, HEADER, import_archive

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--month", required=True)
    parser.add_argument("--collected-at", required=True)
    parser.add_argument("--listed-file-modified-on")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs")
    args = parser.parse_args()
    stamp = datetime.datetime.fromisoformat(args.collected_at)
    if stamp.tzinfo is None:
        raise ValueError("Collection time must include timezone")
    result = import_archive(args.archive, args.month)
    result.update({"source": {"dataset": "[내국인] 행정동별 서울 생활인구(250m)", "url": DATASET_URL, "download_url": "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false", "download_post": {"infId": "OA-23016", "infSeq": "1", "seq": args.month}, "file_listed_modified_on": args.listed_file_modified_on}, "collected_at": args.collected_at, "snapshot_built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "unit": "추정 인구(명)", "classification": "native_only_250m_based_separate_snapshot", "legacy_comparability": "Not established. Do not calculate change versus discontinued July dataset.", "name_mapping": "Code-only display; legacy 424-code mapping is not applied to the 427-code source."})
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer)
    writer.writerow(HEADER)
    writer.writerows([row[key] for key in HEADER] for row in result["rows"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = "native-population-" + args.month
    # All parsing/validation completes before any published output is touched.
    for suffix, content in [(".json", encoded), (".csv", csv_buffer.getvalue())]:
        target = args.output_dir / (stem + suffix)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8-sig" if suffix == ".csv" else "utf-8")
        temp.replace(target)
    print(json.dumps({"date": result["reference_date"], "hour": result["reference_hour"], "codes": result["dong_count"], "total_exact": result["total_population_exact"], "checked_rows": result["validation"]["rows_checked"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
