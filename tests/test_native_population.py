"""Protect official source grain, suppression and full-month coverage."""
import io
import sys
import zipfile
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from seoul_citydata.native_population import HEADER, import_archive

def archive(tmp_path, rows):
    stream=io.BytesIO()
    body=','.join(HEADER)+'\n'+'\n'.join(';'.join(row) for row in rows)+'\n'
    with zipfile.ZipFile(stream,'w') as z:z.writestr('250_LOCAL_RESD_ADMDONG_20260930.csv',body.encode('cp949'))
    file=tmp_path/'official.zip';file.write_bytes(stream.getvalue());return file

def row(code='11110515', total='28.00'):
    return ['20260930','23',code,total]+['1.00']*28

def test_suppressed_age_is_preserved_and_never_a_zero_or_rate(tmp_path):
    values=row();values[4]='*'
    result=import_archive(archive(tmp_path,[values]),'202609',strict_month=False)
    assert result['total_population_exact']=='28.00'
    assert result['rows'][0][HEADER[4]]=='*'
    assert result['validation']['selected_masked_cells']==1
    assert result['validation']['age_sex_rates'] is None
    assert result['reference_date']=='20260930' and result['reference_hour']=='23'

def test_duplicate_source_key_cannot_inflate_population(tmp_path):
    with pytest.raises(ValueError,match='Duplicate'):import_archive(archive(tmp_path,[row(),row()]),'202609',strict_month=False)

@pytest.mark.parametrize('value',['*','NaN','Infinity','-1'])
def test_invalid_or_suppressed_total_cannot_be_summed(tmp_path,value):
    with pytest.raises(ValueError):import_archive(archive(tmp_path,[row(total=value)]),'202609',strict_month=False)

def test_partial_month_cannot_be_called_complete(tmp_path):
    with pytest.raises(ValueError,match='Incomplete month'):import_archive(archive(tmp_path,[row()]),'202609')

def test_unmasked_parts_must_equal_source_total(tmp_path):
    with pytest.raises(ValueError,match='do not match total'):import_archive(archive(tmp_path,[row(total='99')]),'202609',strict_month=False)
