from pyprojroot.here import here

DATA_DIR = here("data")
SRC_DIR = here("src")

SHEETS = {
    'BS':'Bảng cân đối kế toán',
    'IS':'Kết quả kinh doanh',
    'CF':'Lưu chuyển tiền tệ',
    'NOTES':'Thuyết minh'
}

CUM_CONST = {
    'cash_dau_ky':'CF_56',
    'cash_cuoi_ky':'CF_58',
    'notes_max': [f'NOTES_{i}' for i in range(1, 155)]
}

TOPNHNN = 'AGRB,BID,CTG,VCB'.split(',')
TOPNHTM = 'VPB,SHB,VIB,MBB,ACB,HDB,TCB'.split(',')
TOPNH = 'AGRB,BID,CTG,VPB,VCB,SHB,STB,VIB,LPB,MBB,ACB,HDB,EIB,SSB,MSB,ABB,TPB,OCB,NAB,BVB,TCB,VAB,VBB,PGB,BAB,NVB,KLB,SGB'.split(',')