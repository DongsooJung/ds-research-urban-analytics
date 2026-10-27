import csv
import io
import zipfile
import pytest
from seoul_citydata.admin_names import HEADER, parse_name_reference


def reference(rows):
    text = io.StringIO(newline="")
    w = csv.writer(text, lineterminator="\n")
    w.writerow(HEADER)
    w.writerows(rows)
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("SEOUL_ADMI/ADMI_202608.csv", text.getvalue().encode("utf-8-sig"))
    return raw.getvalue()


def row(code="11230515", month="202608", name="신설동"):
    return ["서울특별시", "동대문구", name, code, "서울특별시 동대문구 " + name, month]


def test_reference_month_is_preserved_and_rows_are_not_population_estimates():
    r = parse_name_reference(reference([row()]), "202608", {"11230515"})
    assert r["reference_month"] == "2026-08"
    assert r["rows"][0]["ADMI_NM"] == "신설동"
    assert "생활인구합계" not in r["rows"][0]


def test_duplicate_code_cannot_multiply_a_population_join():
    with pytest.raises(ValueError, match="Duplicate"):
        parse_name_reference(reference([row(), row()]), "202608", {"11230515"})


@pytest.mark.parametrize("codes", [{"11230515", "11230533"}, {"11230533"}])
def test_partial_or_stale_mapping_is_rejected(codes):
    with pytest.raises(ValueError, match="exactly match"):
        parse_name_reference(reference([row()]), "202608", codes)


def test_mixed_months_cannot_be_relabelled_as_latest():
    with pytest.raises(ValueError, match="month/code"):
        parse_name_reference(reference([row(month="202609")]), "202608", {"11230515"})


def test_missing_name_does_not_become_a_display_label():
    with pytest.raises(ValueError, match="Missing"):
        parse_name_reference(reference([row(name="")]), "202608", {"11230515"})
