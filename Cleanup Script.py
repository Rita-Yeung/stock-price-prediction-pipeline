"""
Purpose: Clean up abnormal data in collected database
"""
__author__ = "Rita Yeung"

#%% Definition & Initialization
from sqlalchemy import create_engine
import os
from datetime import datetime
import pandas as pd
import winsound
from dotenv import load_dotenv
import sys

load_dotenv()
db_password = os.getenv('DB_PASSWORD')
engine = create_engine(f'postgresql://postgres:{db_password}@localhost:5432/us_stock')
database_table_name = 'annual_financials_full'
clean_table_name = 'annual_financials_clean'
damaged_table_name = 'damaged_data'
less_table_name = 'company_less_data'
log_table_name = 'annual_financials_full_log'

pd.set_option('future.no_silent_downcasting', True)
PER=20

#%% Functions

def find_desktop():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                             r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        desktop_path, _ = winreg.QueryValueEx(key, "Desktop")  # 'Desktop' is the variable name recording desktop location in Windows registry
        target_desktop = os.path.expandvars(desktop_path)  # Handle environment variable expansion (e.g. %USERPROFILE% format)
        print(f"ℹ️ OneDrive detected, saving file to: {target_desktop}")
        return target_desktop
    except Exception:
        # Fallback to default path if reading fails
        target_desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop") 
        print(f"ℹ️ Using default desktop path: {target_desktop}")
        return target_desktop

def calculate_financials(df, run_log):
    target_mask = df['shares#'].notnull() & df['eps'].isnull()
    fix_targets = df.loc[target_mask, ['ticker', 'fy']]
    print(f"Found {len(target_mask)} rows needing repair...")
    
    new_eps_values = df.loc[target_mask, 'net_income'] / df.loc[target_mask, 'shares#']
    df.loc[target_mask, 'eps'] = new_eps_values
    
    for idx in fix_targets.index:
        t = df.loc[idx, 'ticker']
        f = df.loc[idx, 'fy']
        n_eps = new_eps_values.loc[idx]
        msg = f"year {f} eps is recovered from nan into {n_eps:.2f}, "
        
        if t in run_log['ticker'].values:
            current_msg = run_log.loc[run_log['ticker'] == t, 'update_after_cleanup'].values[0]
            new_msg = f"{current_msg}. {msg}" if pd.notna(current_msg) else msg
            run_log.loc[run_log['ticker'] == t, 'update_after_cleanup'] = new_msg
    
    return df, len(target_mask)

def export_csv():
    filename1 = f"{clean_table_name}_{now}.csv"
    filename2 = f"{damaged_table_name}_{now}.csv"
    filename3 = f"{less_table_name}_{now}.csv"
    
    target_desktop = find_desktop()
    path1 = os.path.join(target_desktop, filename1)
    path2 = os.path.join(target_desktop, filename2)
    path3 = os.path.join(target_desktop, filename3)
    
    try:
        if not df.empty:
            query1 = f"SELECT * FROM {clean_table_name} ORDER BY ticker, fy, fp"
            df_temp = pd.read_sql(query1, engine)
            df_temp = df_temp.fillna("NULL")
            df_temp.to_csv(path1, index=False, encoding='utf-8-sig')
            print(f"Exported csv files: {filename1} to desktop")
        if not damaged_data.empty:
            query2 = f"SELECT * FROM {damaged_table_name} ORDER BY ticker, fy, fp"
            df_temp = pd.read_sql(query2, engine)
            df_temp = df_temp.fillna("NULL")
            df_temp.to_csv(path2, index=False, encoding='utf-8-sig')
            print(f"Exported csv files: {filename2} to desktop")
        if not company_less_data.empty:
            query3 = f"SELECT * FROM {less_table_name} ORDER BY ticker, fy, fp"
            df_temp = pd.read_sql(query3, engine)
            df_temp = df_temp.fillna("NULL")
            df_temp.to_csv(path3, index=False, encoding='utf-8-sig')
            print(f"Exported csv files: {filename3} to desktop")
    except Exception as e:
        print(f"Export failed: {e}")

#%% Main

now = datetime.now().strftime("%Y-%m-%d %H-%M-%S")

# Step 1 Remove broken data: company data with missing net_income ============
df = pd.read_sql(f"SELECT * FROM {database_table_name}", engine)
run_log = pd.read_sql(f"SELECT * FROM {log_table_name}", engine)
print(f"Original total records:{len(df)}")

print("Executing Step 1: Removing companies with missing recurring profit and net income data")
tickers_miss_ni = set(df[df['net_income'].isnull()]['ticker'])
tickers_miss_rp = set(df[df['recurrent_profit'].isnull()]['ticker'])
tickers_to_relocate = list(tickers_miss_ni | tickers_miss_rp)

# Relocate damaged data into 'damaged_data' table
damaged_data = df[df['ticker'].isin(tickers_to_relocate)].copy()

for ticker in tickers_to_relocate:
    in_ni = ticker in tickers_miss_ni
    in_rp = ticker in tickers_miss_rp
    if in_ni and in_rp:
        msg = 'Relocated to table "damaged_data" due to missing recurrent_profit and net_income.'
    elif in_ni:
        msg = 'Relocated to table "damaged_data" due to missing net_income.'
    else:
        msg = 'Relocated to table "damaged_data" due to missing recurrent_profit.'
    run_log.loc[run_log['ticker'] == ticker, 'update_after_cleanup'] = msg

df = df[~df['ticker'].isin(tickers_to_relocate)].copy()
print(f"Step 1 complete: Relocated data for {len(tickers_to_relocate)} companies to 'damaged_data' table.")
print(f"Remaining records: {len(df)} ({df['ticker'].nunique()} companies)")

winsound.MessageBeep(64)  # System Information sound
user_input = input("Continue to step 2: fill missing share numbers? (Y/N): ").strip().upper()
if user_input != 'Y':
    print("Program stopped.")
    sys.exit()

# Step 2 Recover shares# using fill===========================================
print("Continuing Step 2: Filling missing share numbers")
counter = 0
for ticker in df['ticker'].unique():
    mask = df['ticker'] == ticker
    company_data = df.loc[mask, :].copy()
    if company_data['shares#'].isna().any():
        nan_indices = company_data[company_data['shares#'].isna()].index
        filled_values = company_data['shares#'].ffill().bfill()
        df.loc[mask, 'shares#'] = filled_values
        log_msgs = []
        for idx in nan_indices:
            fy = df.loc[idx, 'fy']
            val = filled_values.loc[idx]
            log_msgs.append( f'year {fy} shares# is filled into {val}')
        run_log.loc[run_log['ticker'] == ticker, 'update_after_cleanup'] = " , ".join(log_msgs)
        counter += 1
print(f"Filled missing share numbers for {counter} companies.")

print("Checking if any companies still have missing share number values")
bad_shares_tickers = df[df['shares#'] == 0]['ticker'].unique()

if len(bad_shares_tickers) > 0:
    bad_shares_data = df[df['ticker'].isin(bad_shares_tickers)].copy()
    damaged_data = pd.concat([damaged_data, bad_shares_data], ignore_index=True)
    df = df[~df['ticker'].isin(bad_shares_tickers)].copy()
    # Update run_log for excluded companies
    for ticker in bad_shares_tickers:
        run_log.loc[run_log['ticker'] == ticker, 'update_after_cleanup'] = 'Deleted due to missing shares#.'
        print(f"Step 2 complete: Moved {len(bad_shares_tickers)} companies with abnormal share numbers to 'damaged_data'.")
else:
    print("Step 2 complete: No companies with 0 shares found.")

winsound.MessageBeep(64)  # System Information sound
user_input = input("Continue to step 3: fill missing EPS? (Y/N): ").strip().upper()
if user_input != 'Y':
    print("Program stopped.")
    sys.exit()

# Step 3 Recover eps using calculation net_income/shares# ====================
print("Continuing Step 3: Filling missing EPS")
df, rowNum = calculate_financials(df, run_log)

cols_to_convert = ['operating_cash', 'dividend', 'lt_asset', 'lt_liabilities', 
                   'cash', 'inven_other', 'curr_liabilities', 'asset', 'equity', 
                   'shares#', 'stock_price', 'net_income', 'profit', 'stock_price_unadjusted']

for col in cols_to_convert:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.assign(
    per = df['stock_price'] / df['eps'],
    equity_ratio = df['equity'] / df['asset'],
    bps = df['equity'] / df['shares#'],
    pbr = lambda x: x['stock_price'] / x['bps'],
    cash_flow_ratio = df['operating_cash'] / df['curr_liabilities'],
    cash_reinvest_ratio = (df['operating_cash'] - df['dividend'].fillna(0))/(df['lt_asset'] 
                          + df['lt_liabilities'] + (df['cash'] + df['inven_other'].fillna(0) 
                          - df['curr_liabilities'])),
    cash_per_asset_ratio = df['operating_cash'] / df['asset'],
    cashflowps_ratio =  (df['operating_cash'] - df['dividend'].fillna(0)) / df['shares#'],
    ocfperprofit_ratio = df['operating_cash'] / df['profit'],
    debt_assurance_ratio = df['operating_cash'] /( df['curr_liabilities'] + df['lt_liabilities']),
    roa_discount =  lambda x: x['equity_ratio'].apply( lambda val: 0.8 if val>0.8 else 0.75 if val >0.67 
                    else 0.7 if val>0.5 else 0.65 if val>0.33 else 0.6 if val>0.1 else 0.5 if val>0 else 0),
    roa = df['net_income'] / df['asset'],
    financial_leverage_ratio = lambda x: 1 / x['equity_ratio'],
    leverage_factor = lambda x: x['financial_leverage_ratio'].apply(lambda val: 1.5 if val >3 
                    else 1.36 if val >2.5 else 1.2 if val >2 else 1),
    risk_factor = lambda x: x['pbr'].apply(lambda val: 1 if val>0.5 else 0.8 if val>0.4
                  else 0.66 if val>0.33 else 0.5 if val>0.25 
                  else 0.15*(val/50*5) if val>0.03 else 0.01*(( val -1)*10+5)),
    asset_value = lambda x: x['roa_discount'] * x['bps'],
    career_value = lambda x: x['roa'].clip(upper=0.3)* x['eps'] * x['leverage_factor'] * PER * 10,
    theoretical_price = lambda x:(x['asset_value'] + x['career_value']) * x['risk_factor'],
    current_ratio = (df['cash'] + df['inven_other'].fillna(0)) / df['curr_liabilities'],
    quick_ratio = (df['cash'] ) / df['curr_liabilities'],
    fixedasset_per_ltcapital_ratio = df['lt_asset'] / (df['equity'] + df['lt_liabilities']),
    fixedasset_per_equity_ratio = df['lt_asset'] / df['equity'],
    roe = df['net_income'] / df['equity'],
    theoretical_price_upper = lambda x: x['theoretical_price'] *2,
    theoretical_roe = lambda x: x['theoretical_price'] / x['eps'],
    theoretical_pbr = lambda x: x['theoretical_price'] / x['bps'],
    asset_pershare = df['asset'] / df['shares#'] ,
    market_cap = df['stock_price_unadjusted'] * df['shares#'])

print(f"Step 3 complete: Repaired {rowNum} EPS entries and recalculated derived columns.")

winsound.MessageBeep(64)  # System Information sound
user_input = input("Continue to step 4: segment companies with less data? (Y/N): ").strip().upper()
if user_input != 'Y':
    print("Program stopped.")
    sys.exit()

print("Continuing Step 4: Segmenting companies")

company_less_data = pd.DataFrame()
cols_to_check = ['cost', 'expense_general/admin', 'currasset', 'curr_liabilities']

df['is_missing'] = df[cols_to_check].isna().any(axis=1)
missing_tickers = df[df['is_missing'] == True]['ticker'].unique()
if len(missing_tickers) > 0:
    company_less_data = df[df['ticker'].isin(missing_tickers)].copy()
    company_less_data = company_less_data.drop(columns=['is_missing'])
    df = df[~df['ticker'].isin(missing_tickers)].copy()
    print(f"Moved {len(missing_tickers)} companies with missing data to 'company_less_data' table.")
    print(f"Remaining df records: {len(df)} ({df['ticker'].nunique()} companies)")
else:
    print("No companies with missing data found.")
    
if 'is_missing' in df.columns:
    df = df.drop(columns=['is_missing'])

winsound.MessageBeep(64)  # System Information sound
print("--- Post-processing Statistics ---")
print(f"df: {len(df)} records ({df['ticker'].nunique() if not df.empty else 0} companies)")
print(f"damaged_data: {len(damaged_data)} records ({damaged_data['ticker'].nunique() if not damaged_data.empty else 0} companies)")
print(f"company_less_data: {len(company_less_data)} records ({company_less_data['ticker'].nunique() if not company_less_data.empty else 0} companies)")

user_input = input("Upload tables to database? (Y/N): ").strip().upper()
if user_input != 'Y':
    print("Program stopped.")
    sys.exit()

if not df.empty:
    df.to_sql(clean_table_name, engine, if_exists='replace', index=False)
    print(f"✅ Uploaded {clean_table_name} to database")
else:
    print("⚠️ No clean data available to write.")

if not damaged_data.empty:
    damaged_data.to_sql(damaged_table_name, engine, if_exists='replace', index=False)
    print(f"✅ Uploaded {damaged_table_name} to database")

if not company_less_data.empty:
    company_less_data.to_sql(less_table_name, engine, if_exists='replace', index=False)
    print(f"✅ Uploaded {less_table_name} to database")
    
run_log.to_sql(log_table_name, engine, if_exists='replace', index=False)
print(f"✅ Uploaded {log_table_name} to database.")

#%% Done program run

winsound.MessageBeep(64)
user_input = input("Export csv? (Y/N): ").strip().upper()
if user_input != 'Y':
    print("Program stopped.")
    sys.exit()

run_log.to_sql(log_table_name, engine, if_exists='replace', index=False)
print(f"✅ Uploaded {log_table_name} to database.")

export_csv()
run_log.to_csv(os.path.join(find_desktop(), f"run_log_df_{now}.csv"), index=False)
print(f"Exported csv files: run_log_df_{now}.csv to desktop")