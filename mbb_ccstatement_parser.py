# MBB Credit Card Statement Parser
# (based on TNG Statement in CSV by Rexpert https://github.com/Rexpert/TNG_Statement_in_CSV)

import argparse
import pandas as pd
import numpy as np
import camelot
import PyPDF2
import datetime

parser = argparse.ArgumentParser(
                          description='Converts MBB\'s Credit Card statement to CSV',
                          epilog='Not extensively tested. Not affliated with MBB.'
                        )
parser.add_argument('filename', default='statementcc.pdf', nargs='?', help='PDF file of MBB Credit Card Statement')
parser.add_argument('-pw', '--password', help='Password for MBB Credit Card Statement')
parser.add_argument('-p', '--pages', help='No of statement pages (minus TreatPoints & promo pages)')
parser.add_argument('-y', '--year', help='Statement year <default=current year>')
args = parser.parse_args()

reader = PyPDF2.PdfFileReader(args.filename)

password = args.password
pageNumber = args.pages
stmtYear = args.year

if reader.is_encrypted:
    if not password:
        password = input('PDF encrypted! Please enter password: ')
    reader.decrypt(password)

# If # of pages is supplied, we'll use that (+1 because we'll minus it when running camelot). If not, we'll read number of pages from the PDF (and assume we'll not take the last page)
if not pageNumber:
    pageNumber = str(reader.numPages - 1)
else:
    if not pageNumber.isdigit():
        print('Error! Page argument isn\'t a number')
        exit()

# MBB CC statements does not contain the year in the Posting & Transaction Date columns. One way is to read the year from the top part of the statement, but that's too much work. Defaults to current year
if not stmtYear:
    stmtYear = str(datetime.date.today().year)
else:
    if not stmtYear.isdigit():
        print('Error! Statement year isn\'t a number')
        exit()
    else:
        if not (int(stmtYear) >= 1950 and int(stmtYear) <= 2050):
            print('Error! Year should be 4 digits between 1950-2050')
            exit()


# Process 1st page. This will be messy since the formatting is different for different cards
try:
    table = camelot.read_pdf(args.filename, pages='1', flavor='stream', password=password,
                            table_regions=['20,430,590,40'], table_areas=['20,430,590,40'], 
                            columns=['85,160,380,500'], 
                            split_text=True, strip_text='\n')
except:
    (
        print('Error opening file:', args.filename),
        print('Some possible resolutions:'),
        print(' - Ensure filename is correct'),
        print(' - Ensure PyCryptodome is installed to decrypt password'),
        print(' - Wrong password, maybe?'),
        exit()
    )

df = (
    pd
    .concat([tbl.df for tbl in table._tables], ignore_index=True)
    .set_axis(['Posting_Date', 'Transaction_Date', 'Description', 'Details', 'Amount'], axis=1)
    .query('Posting_Date.str.contains(r"^\d|^$", na=True) & ~Description.str.contains(r"^$") & ~Description.str.startswith(r"TOTAL CREDIT THIS MONTH") & ~Description.str.startswith(r"TOTAL DEBIT THIS MONTH") & ~Description.str.startswith(r"(JUMLAH KREDIT)") & ~Description.str.startswith(r"(JUMLAH DEBIT)") & ~Description.str.startswith(r"RETAIL INTEREST RATE") & ~Description.str.startswith(r"YOUR COMBINED CREDIT LIMIT") & ~Description.str.startswith(r"YOUR PREVIOUS STATEMENT BALANCE") & ~Details.str.startswith(r"SUB TOTAL/JUMLAH")', engine='python')
    .assign(idx=lambda x: (~x.Posting_Date.str.contains('^$')).cumsum())
    .groupby('idx')
    .apply(lambda x: x.apply(lambda y: ' '.join(y.fillna('').astype(str))).str.strip())
    .reset_index(drop=True)
    .drop(['idx'], axis=1)
    .replace(r'^\s*$', np.nan, regex=True)
)

# Drop items without amount (usually non-transactional items)
df.dropna(subset=['Amount'], inplace=True)

# If DataFrame isn't empty, do some clean-up, and change Credit items (payments, reversal, cashback, etc) to negative
if not df.empty:
    df = df.assign(
        Transaction_Date = lambda x: pd.to_datetime(x.Transaction_Date + '/' + stmtYear, format=r'%d/%m/%Y'),
        Posting_Date = lambda x: pd.to_datetime(x.Posting_Date + '/' + stmtYear, format=r'%d/%m/%Y'),
        **{
            'Amount': lambda x: np.where(
                x['Amount'].str.endswith('CR'),
                -x['Amount'].str.removesuffix('CR').str.replace(r'[^0-9\.]', '', regex=True).astype(float),
                x['Amount'].str.replace(r'[^0-9\.]', '', regex=True).astype(float)
            )
        }
    )

# Check if there are more than 2 pages. The last page is for TreatsPoint, so we skip it. But... Sometimes MBB adds another extra page, so the parser will mistakenly process the TreatsPoint page. Tried to clean-up the best I can, but might not be enough
if int(pageNumber) > 1:
    table = camelot.read_pdf(args.filename, pages='2-'+pageNumber, flavor='stream', password=password,
                        table_regions=['20,800,590,195'], table_areas=['20,800,590,195'], 
                        columns=['85,160,380,500'], 
                        split_text=True, strip_text='\n')

# I use query to filter out undesirable items. Might have missed some, and it might be different for different cards/statement. Some of this are specific to the MBB Shopee card. A better way is to skip the TreatPoint page. Huhu
    df2 = (
        pd
        .concat([tbl.df for tbl in table._tables], ignore_index=True)
        .set_axis(['Posting_Date', 'Transaction_Date', 'Description', 'Details', 'Amount'], axis=1)
        .query('Posting_Date.str.contains(r"^\d|^$", na=True) & ~Description.str.contains(r"^$") & ~Description.str.startswith(r"TOTAL CREDIT THIS MONTH") & ~Description.str.startswith(r"TOTAL DEBIT THIS MONTH") & ~Description.str.startswith(r"(JUMLAH KREDIT)") & ~Description.str.startswith(r"(JUMLAH DEBIT)") & ~Description.str.startswith(r"RETAIL INTEREST RATE") &  ~Description.str.startswith(r"YOUR COMBINED CREDIT LIMIT") & ~Description.str.startswith(r"YOUR PREVIOUS STATEMENT BALANCE") & ~Description.str.contains(r"Mata Ganjaran") & ~Description.str.contains(r"Shopee Coins") & ~Description.str.contains(r"Dipindahkan") & ~Description.str.startswith(r"Terkumpul") & ~Details.str.startswith(r"SUB TOTAL/JUMLAH")', engine='python')
        .assign(idx=lambda x: (~x.Posting_Date.str.contains('^$')).cumsum())
        .groupby('idx')
        .apply(lambda x: x.apply(lambda y: ' '.join(y.fillna('').astype(str))).str.strip())
        .reset_index(drop=True)
        .drop(['idx'], axis=1)
        .replace(r'^\s*$', np.nan, regex=True)
    )
 
    #Drop items without amount (usually non-transactional items)
    df2.dropna(subset=['Amount'], inplace=True)

# If DataFrame isn't empty, do some clean-up, and change Credit items (payments, reversal, cashback, etc) to negative
    if not df2.empty:
        # Clean-up items that might be captured in Posting Date field
        df2_f = df2.loc[:,'Posting_Date'].str.match('([1-9]|0[1-9]|[12][0-9]|3[01])\/([1-9]|0[1-9]|1[1,2])', case=False)
        df2 = df2.loc[df2_f]

        df2 = df2.assign(
            Transaction_Date = lambda x: pd.to_datetime(x.Transaction_Date + '/' + stmtYear, format=r'%d/%m/%Y'),
            Posting_Date = lambda x: pd.to_datetime(x.Posting_Date + '/' + stmtYear, format=r'%d/%m/%Y'),
            **{
                'Amount': lambda x: np.where(
                    x['Amount'].str.endswith('CR'),
                    -x['Amount'].str.removesuffix('CR').str.replace('[^0-9\.]', '', regex=True).astype(float),
                    x['Amount'].str.replace('[^0-9\.]', '', regex=True).astype(float)
                )
            }
        )

# Debug to print out dataframes
print(df)
print(df2)

# Merge & output to CSV
(
    pd
    .concat([df, df2])
    .to_csv(args.filename.replace('pdf', 'csv'), index=False, encoding='utf-8'),

    print("\nAll done"),
    print('File saved to:', args.filename.replace('pdf', 'csv'))
)
