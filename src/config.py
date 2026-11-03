from pyprojroot.here import here

DATA_DIR = here("data")
SRC_DIR = here("src")

SHEETS = {
    'BS':'Cân đối kế toán',
    'IS':'Báo cáo thu nhập',
    'CF':'Lưu chuyển tiền tệ',
    'NOTES':'Thuyết minh'
}

CUM_CONST = {
    'cash_dau_ky':'CF_47',
    'cash_cuoi_ky':'CF_48',
    'notes_max': [f'NOTES_{i}' for i in range(1, 120)]
}

# Các ngân hàng chỉ có dữ liệu Q2 (cộng dồn 6 tháng) và Q4, thiếu Q1 và Q3
SEMI_ANNUAL = []

TOPNHNN = 'AGRB,BID,CTG,VCB'.split(',')
TOPNHTM = 'VPB,SHB,VIB,MBB,ACB,HDB,TCB'.split(',')
TOPNH = 'AGRB,BID,CTG,VPB,VCB,SHB,STB,VIB,LPB,MBB,ACB,HDB,EIB,SSB,MSB,ABB,TPB,OCB,NAB,BVB,TCB,VAB,VBB,PGB,BAB,NVB,KLB,SGB'.split(',')