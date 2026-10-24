from decimal import Decimal
import pytest
from app.etl import parse_amount,parse_date,normalize_type,normalized_header,extract

@pytest.mark.parametrize('value,expected',[
    ('1.200.000',Decimal('1200000.00')),
    ('1,200,000',Decimal('1200000.00')),
    ('1.200.000,50',Decimal('1200000.50')),
    ('1,200,000.50',Decimal('1200000.50')),
    (1250,Decimal('1250.00')),
])
def test_currency_parsing(value,expected):
    assert parse_amount(value)==expected

@pytest.mark.parametrize('bad',['abc','1,23,4','-3',None,0,'=SUM(A1:A3)'])
def test_bad_amount_rejected(bad):
    with pytest.raises(ValueError): parse_amount(bad)

def test_vietnamese_header_and_dates():
    assert normalized_header('Số tiền (VNĐ)')=='so tien vnd'
    assert parse_date('15/10/2026').isoformat()=='2026-10-15'
    assert normalize_type('Công nợ phải thu')=='RECEIVABLE'

def test_messy_workbook(examples_dir):
    events=list(extract((examples_dir/'02_messy_mixed_departments.xlsx').read_bytes()))
    ok=[e for e in events if e[2] is not None]
    invalid=[e for e in events if e[3] is not None and e[1]>0]
    assert len(ok)==6  # duplicate detected at persistence layer
    assert len(invalid)==1
    assert any(e[1]==0 for e in events) # skipped metadata-only worksheet logged


def test_merged_data_cell_is_reviewed_not_silently_filled():
    from io import BytesIO
    from openpyxl import Workbook
    wb=Workbook()
    ws=wb.active
    ws.append(['Invoice','Date','Department','Customer','Type','Amount','Status'])
    ws.append(['A-1','01/10/2026','Sales','One','Revenue','1000','paid'])
    ws.append(['A-2','02/10/2026',None,'Two','Revenue','2000','paid'])
    ws.merge_cells('C2:C3')
    out=BytesIO()
    wb.save(out)
    events=list(extract(out.getvalue()))
    assert events[0][2] is not None
    assert events[1][2] is None
    assert events[1][3]=='Missing document number or department'
