"""
Purpose: Recovery of ETL error and maximise sample data
"""
__author__ = "Rita Yeung"

#%% (1) Definition & Initialization

import requests
import pandas as pd
import itertools
import yfinance as yf
from sqlalchemy import create_engine, text
import re
import traceback
import winsound
import os
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# =============================================================================
# Record console output and save to a txt file
class Logger:
    def __init__(self, filename):
        # 1. Record original screen output channel in self.terminal
        self.terminal = sys.stdout
        # 2. Create and open a file to write text into self.log
        # open mode ("a" append / "w" write/overwrite): In "w" mode, whenever Python opens the file, it automatically clears old content ensuring it only contains this run's logs.
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message):
        # 3. Write message back to screen so output remains visible
        self.terminal.write(message)
        # Write same message to opened file
        self.log.write(message)
        self.log.flush()

    def flush(self):
        # Ensure buffer text is written immediately to prevent log loss on interruption
        self.terminal.flush()
        self.log.flush()
        
    def close(self):
        self.log.close() # Force close file to release resources

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

now = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
sys.stdout = Logger(os.path.join(find_desktop(), f"console_output_{now}.txt"))
# =============================================================================

pd.set_option('future.no_silent_downcasting', True)

headers={'User-Agent':"your_email@example.com"} # fill in your email address here
load_dotenv()
db_password = os.getenv('DB_PASSWORD')
engine = create_engine(f'postgresql://postgres:{db_password}@localhost:5432/us_stock')
database_table_name = 'annual_financials_full'
database_log_table_name = 'annual_financials_full_log' # 🆕

# =============================================================================
# 🆕 Get the cik list of this recovery company target
fail_query = f"""
    SELECT cik 
    FROM {database_log_table_name} 
    WHERE error_after_recovery1 LIKE '%%division by zero%%'
    AND status_after_recovery1 = 'Fail'
"""
failed_ciks_df = pd.read_sql(fail_query, engine)
failed_ciks_df['cik'] = failed_ciks_df['cik'].astype(str).str.zfill(10)
failed_ciks_list = failed_ciks_df['cik'].astype(str).tolist() # Convert to list for easy querying
# =============================================================================

StudyStart = 2019
StudyEnd = 2025
expected_records = 7
PER=20
REPORT_FORM_FILTER = r'^(10-K|20-F)(/A)?$'  # find report 10-K, 10-K/A, 20-F

revenueDataTag=['RevenueFromContractWithCustomerExcludingAssessedTax',
                'CostOfGoodsAndServicesSold',
                'SellingGeneralAndAdministrativeExpense',
                'OperatingIncomeLoss',
                'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
                'IncomeTaxExpenseBenefit','NetIncomeLoss',
                'WeightedAverageNumberOfSharesOutstandingBasic',
                'EarningsPerShareBasic']

revenueDataName = ['gross_revenue',
                   'cost',
                   'expense_general/admin',
                   'operating_income',
                   'recurrent_profit',
                   'tax','net_income',
                   'shares#',
                   'eps']

assetDataTag=['StockholdersEquity','AssetsCurrent',
              'InventoryNet','OtherAssetsCurrent','LiabilitiesCurrent']

assetDataName = ['equity','currasset',
                 'inventory','other_currasset','curr_liabilities']

cashflowDataTag=['NetCashProvidedByUsedInOperatingActivities',
                 'NetCashProvidedByUsedInInvestingActivities',
                 'PaymentsToAcquirePropertyPlantAndEquipment',
                 'PaymentsToAcquireIntangibleAssets',
                 'NetCashProvidedByUsedInFinancingActivities',
                 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
                 'IncreaseDecreaseInInventories','PaymentsOfDividendsCommonStock']

cashflowDataName = ['operating_cash',
                    'investing_cash',
                    'payment_cap','payment_intangible',
                    'financing_cash',
                    'cash_end',
                    'inventory_delta','dividend']

fallback_map = {
        'RevenueFromContractWithCustomerExcludingAssessedTax' : ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet', 'SalesRevenueGoodsNet'],
        'CostOfGoodsAndServicesSold' : ['CostOfGoodsAndServicesSold', 
                                        'CostOfRevenue', 'CostOfGoodsSold', 
                                        'CostsAndExpenses'], #eg.BRK-B only has CostsAndExpenses tag
        'OperatingExpenses': ['OperatingExpenses', 'OperatingCosts', 'TotalOperatingExpenses', 'OperatingCostsAndExpenses'],
        'ga_fallbacks' : ['GeneralAndAdministrativeExpense', 'AdministrativeExpenses'],
        'sm_fallbacks' : ['MarketingAndAdvertisingExpense', 'SellingAndMarketingExpense',
                          'SellingAndAdvertisingExpense', 'AdvertisingExpense'],
        'NetIncomeLoss': ['NetIncomeLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'ProfitLoss'], # AVGO used ProfitLoss to declare NetIncomeLoss in 2025
        'OperatingIncomeLoss': ['OperatingIncomeLoss', 'OperatingProfitLoss', 
                                'IncomeLossFromContinuingOperations',
                                'IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest',
                                'NetInterestIncome',
                                'ProfitLoss'],  #'ProfitLoss' is not the same as the rest but there are companies that do not separate operating and non-operating (XOM) 
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest': ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', # Standard tag
                                                                                                        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments', # Used by Amazon
                                                                                                        'IncomeBeforeTax'], # Some companies use simplified versions
        'OtherAssetsCurrent' : ['OtherAssetsCurrent', 'PrepaidExpenseAndOtherAssetsCurrent'],
        'StockholdersEquity': ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
        'PaymentsToAcquirePropertyPlantAndEquipment': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'],
        'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents' : ['CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', # Standard
                                                                           'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations', # Total end-of-period cash statement sum
                                                                           'CashAndCashEquivalentsAtCarryingValue' # Ordinary cash (ordinary cash + restricted cash = total end-of-period cash statement sum)
                                                                           ]
    }

allow_nan_tags = {
        'CostOfGoodsAndServicesSold',  # absence in finance/insurance industry
        'SellingGeneralAndAdministrativeExpense',
        'InventoryNet', 
        'OtherAssetsCurrent',
        'LiabilitiesCurrent',  # Some financial or structured companies (e.g. holding companies like JPM, some insurance firms) do not use standard LiabilitiesCurrent tag in SEC report structure
        'PaymentsToAcquirePropertyPlantAndEquipment', 
        'PaymentsToAcquireIntangibleAssets',
        'IncreaseDecreaseInInventories',
        'PaymentsOfDividendsCommonStock'
    }

curr_liabilities_tags = [
    'InterestBearingDepositLiabilities',
    'NoninterestBearingDepositLiabilities',
    'TradingLiabilities',
    'DerivativeLiabilities',
    'OtherAccruedLiabilities',
    'LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseIncurredClaimsCurrentYear',
    'LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseClaimsPaidCurrentYear',
    'OperatingLeasesFutureMinimumPaymentsDueCurrent',
    'IncreaseDecreaseInOtherOperatingLiabilities',
    'AccruedIncomeTaxesCurrent',
    'DerivativeLiabilities'
]

FirstItem = ['Assets']  # 'Assets' as 1st item to establish main df framework
FirstItemName ='asset'  # , due to the consistency of its presence across companies and stable tag name over time

failed_companies_tags_data = []
run_log = []
success_count = 0

#%% (2) Functions

def skip_to_next():
    # EDGAR restriction: API access separate by at least 1sec
    end_time = time.perf_counter()
    if end_time-start_time < 1.0:
        time.sleep(1.0-(end_time-start_time))

def get_financial_value(facts_json, tag_list):
# For main df to access tag data from 'us-gaap', 'ifrs-full' namespace
    for namespace in ['us-gaap', 'ifrs-full']:
        data_source = facts_json.get('facts', {}).get(namespace, {})
        
        # Access tag data by looping through alternate tag name list
        for tag in tag_list:
            if tag in data_source:
                tag_data = data_source[tag]
                unit = list(tag_data['units'].keys())[0]
                return tag_data['units'][unit], namespace, data_source
    return None, None, None

def downloadData(tag, name):
# Access tag data then filter it into same format as main df for merging
    if tag == 'WeightedAverageNumberOfSharesOutstandingBasic':
        used_tag, dfiRaw = get_share_no(data_source, name)
        return used_tag, dfiRaw
    if tag in fallback_map: # tag with fallback list
        tag_list = fallback_map[tag]
        used_tag, dfiRaw = get_value_fallback(data_source, tag_list, name)
        if dfiRaw is not None:
            return used_tag, dfiRaw
    else:
        tag_data_i = data_source.get(tag) # tag with only one unique tag name
        
        if tag_data_i:
            used_tag = tag
            unit = list(tag_data_i['units'].keys())[0]
            dfiRaw = pd.DataFrame(tag_data_i['units'][unit])
            
            if tag == 'EarningsPerShareBasic' and dfiRaw['fy'].max() < StudyStart: 
            # WMT has missing eps data even dfiRaw is not empty
                used_tag = get_eps()
                return used_tag, None 
        # Some companies separate general&admin and selling&marketing.
        elif (tag_data_i is None) and (tag == 'SellingGeneralAndAdministrativeExpense'):
            used_tag, dfiRaw = get_total_sga(data_source, name)
            if dfiRaw is not None:
                return used_tag, dfiRaw
        # Some companies does not report 'AssetsCurrent'. Need to back calculate.
        elif (tag_data_i is None) and (tag == 'AssetsCurrent'):
            used_tag, dfiRaw = get_currasset(data_source, name)
            if dfiRaw is not None:
                return used_tag, dfiRaw
        else:
            dfiRaw = None
        
    if dfiRaw is None:
        used_tag = 'none'
        # Create empty column for reasonable absence of tag data
        if tag in allow_nan_tags: 
            print(f"ℹ️ {tag} not found, automatically creating empty time series to keep pipeline smooth.")
            dfi = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'val'])
            dfi = dfi.set_index('end')
            dfi.rename(columns={"val": name}, inplace=True)
            return used_tag, dfi
        # Allow return None for intermediate step for finding 'SellingGeneralAndAdministrativeExpense' and current asset
        elif tag in ['ga_fallbacks', 'sm_fallbacks', 'PropertyPlantAndEquipmentNet'
                     , 'Goodwill', 'EquityMethodInvestments', 'NonoperatingIncomeExpense',
                     'OtherNonoperatingIncomeExpense']:
            return used_tag, dfiRaw
        # Companies like VISA does not include eps in report. 
        # Run get_eps() to manipulate the main df to assign eps = net_income / shares#
        elif tag == 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest':
            used_tag, dfiRaw = get_recurrent_profit()
            return used_tag, dfiRaw
        elif tag == 'EarningsPerShareBasic':
            used_tag = get_eps()
            return used_tag, None
        elif tag in curr_liabilities_tags: 
            return used_tag, dfiRaw
        # Except for the above acceptable absence, ValueError will be raised to alert missing of indicators
        else:
            skip_to_next()
            raise ValueError(f"No {tag} Tag Found")
            
    dfiRaw['end'] = pd.to_datetime(dfiRaw['end'])
    dfiRaw['filed'] = pd.to_datetime(dfiRaw['filed'])
    
    if 'start' in dfiRaw.columns:
        dfi = dfiRaw[(dfiRaw['form'].str.match(REPORT_FORM_FILTER, na=False)) &
                     (dfiRaw['fy'] >= StudyStart)].loc[:,['start','end','fy','fp','filed','val']]
        dfi['start'] = pd.to_datetime(dfi['start'])
        dfi['duration'] = (dfi['end'] - dfi['start']).dt.days
        dfi = dfi[(dfi['duration'] >= 300)]  # to get annual value instead of quarterly value
        dfi = dfi.drop(columns=['start','duration'])
    else:
        dfi = dfiRaw[(dfiRaw['form'].str.match(REPORT_FORM_FILTER, na=False)) &
                     (dfiRaw['fy'] >= StudyStart)].loc[:,['end','fy','fp','filed','val']]
    
    dfi = dfi.sort_values(by=['end', 'filed']).drop_duplicates(subset=['fy','fp'], keep='last')
    dfi = dfi.set_index('end')
    dfi.rename(columns={"val": name}, inplace=True)
    return used_tag, dfi

def get_value_fallback(data_source, tag_list, name, is_namespace_pair=False):
# for handle tags with multiple possible names
    df_list = []
    latest_available_fy = 0
    last_valid_val = 0
    used_tag_list = []
    used_tag = ''
    
    if is_namespace_pair == True:  # called by def get_share_no
        for namespace, tag_name in tag_list:  # tag list = fallback_map_share
            facts = raw_json.get('facts', {})
            tag_data = facts.get(namespace, {}).get(tag_name, {})
            if not tag_data or 'units' not in tag_data:
                continue
            unit = list(tag_data['units'].keys())[0]
            sub_df = pd.DataFrame(tag_data['units'][unit])
            tag_path = f"[{namespace}] {tag_name}"
            used_tag_list.append(tag_path)
            
            sub_df['end'] = pd.to_datetime(sub_df['end'])
            sub_df['filed'] = pd.to_datetime(sub_df['filed'])
            sub_df = sub_df[sub_df['form'].str.match(REPORT_FORM_FILTER, na=False)].loc[:,['end','fy','fp','filed','val']]

            if 'fy' not in sub_df.columns:  # for cases like VISA ('dei', 'EntityCommonStockSharesOutstanding')
                sub_df['fy'] = sub_df['end'].dt.year
            if 'fp' not in sub_df.columns:       
                sub_df['fp'] = 'FY'
            
            if sub_df['fy'].max() > latest_available_fy:
                latest_available_fy = sub_df['fy'].max()
                last_valid_val = sub_df.sort_values('fy').iloc[-1]['val']
            
            df_list.append(sub_df)
            
        if len(df_list) == 0:
                raise ValueError("No WeightedAverageNumberOfSharesOutstandingBasic Tag Found")
    else:
        if 'NetInterestIncome' in tag_list:  # eg. JPM
            tag_list.append('NoninterestIncome')  # if NetInterestIncome is present also check for NoninterestIncome
            
        for tag in tag_list:
            tag_data = data_source.get(tag)
            if tag_data is not None:
                unit = list(tag_data['units'].keys())[0]
                sub_df = pd.DataFrame(tag_data['units'][unit])
                sub_df['end'] = pd.to_datetime(sub_df['end'])
                sub_df['filed'] = pd.to_datetime(sub_df['filed'])
                if 'start' in sub_df.columns:
                    sub_df = sub_df[(sub_df['form'].str.match(REPORT_FORM_FILTER, na=False)) &
                                 (sub_df['fy'] >= StudyStart)].loc[:,['start','end','fy','fp','filed','val']]
                    sub_df['start'] = pd.to_datetime(sub_df['start'])
                    sub_df['duration'] = (sub_df['end'] - sub_df['start']).dt.days
                    sub_df = sub_df[(sub_df['duration'] >= 300)]  # to get annual value instead of quarterly value
                    sub_df = sub_df.drop(columns=['start','duration'])
                    
                else:
                    sub_df = sub_df[(sub_df['form'].str.match(REPORT_FORM_FILTER, na=False)) &
                                 (sub_df['fy'] >= StudyStart)].loc[:,['end','fy','fp','filed','val']]
                if not sub_df.empty and not sub_df['val'].isna().all():
                    used_tag_list.append(tag)
                    df_list.append(sub_df)
            
    if is_namespace_pair == True and latest_available_fy < StudyStart:
    # For no. of basic shares data, if all data is before Study Start,
    # only use the latest available data to broadcast to current
        print(f"⚠️ Detected timeline gap data for {name} (latest only up to {latest_available_fy}). Activating timeline duplication broadcast mechanism...")
        broadcast_df = date_template.copy()
        broadcast_df['val'] = last_valid_val
        broadcast_df = broadcast_df.set_index('end')
        broadcast_df.rename(columns={"val": name}, inplace=True)
        return used_tag, broadcast_df
            
    # Fill in value with first available tag data then fill in null with later available tag data
    if len(df_list) > 1:
        dfiRaw = date_template.copy()
        dfiRaw['val'] = pd.NA
        for i, sub_df in enumerate(df_list):
            if is_namespace_pair == True:
                sub_df = sub_df[sub_df['fy'] >= StudyStart]
                
            temp_df = sub_df.rename(columns={'val': 'temp_val'})
            temp_df = temp_df.sort_values(by=['end', 'filed']).drop_duplicates(subset=['fy','fp'], keep='last')
            
            if is_namespace_pair == True:
                temp_df = temp_df[['fy', 'temp_val']]
                dfiRaw = pd.merge(dfiRaw, temp_df, on=['fy'], how='left', validate='1:1')
            else:
                dfiRaw = pd.merge(dfiRaw, temp_df, on=['end','fy','fp','filed'], how='left', validate='1:1')
            pre_fill_mask = dfiRaw['val'].isna()
            
            if used_tag_list[i] == 'NoninterestIncome':  # add up value of NoninterestIncome, instead of combine_first
                dfiRaw['val'] = dfiRaw['val'].fillna(0) + dfiRaw['temp_val'].fillna(0)
            else:
                dfiRaw['val'] = dfiRaw['val'].combine_first(dfiRaw['temp_val'])
            
            post_fill_mask = dfiRaw['val'].notna()
            contributed_mask = post_fill_mask & pre_fill_mask
            years = dfiRaw.loc[contributed_mask, 'fy'].dropna().unique().tolist()
            if len(years) > 0:
                year_range = f"[{int(min(years))}-{int(max(years))}]" if len(years) > 1 else f"[{int(years[0])}]"
                used_tag_list[i] = f"{year_range} {used_tag_list[i]}"
            
            dfiRaw = dfiRaw.drop(columns=['temp_val'])
            if dfiRaw['val'].notna().all():
                break
        dfi = dfiRaw.set_index('end')
        dfi.rename(columns={"val": name}, inplace=True)
    # If only one tag data is available, go straight to filter
    elif len(df_list) == 1:
        if is_namespace_pair == True:
            sub_df = sub_df[sub_df['fy'] >= StudyStart]
        dfiRaw = df_list[0]      
        dfi = dfiRaw.sort_values(by=['end', 'filed']).drop_duplicates(subset=['fy','fp'], keep='last')
        dfi = dfi.set_index('end')
        dfi.rename(columns={"val": name}, inplace=True)
    else:
        dfi = None
        
    if used_tag_list is not None:
        used_tag = " + ".join(used_tag_list)
        
    return used_tag, dfi
  
def get_share_no(data_source, name):
    fallback_map_share = [
                ('us-gaap', 'WeightedAverageNumberOfSharesOutstandingBasic'),
                ('us-gaap', 'CommonStockSharesIssued'),
                ('us-gaap', 'CommonStockSharesOutstanding'),
                ('dei', 'EntityCommonStockSharesOutstanding'), 
                ('us-gaap', 'WeightedAverageNumberOfSharesOutstandingBasicAndDiluted'),
            ]
    
    used_tag, df = get_value_fallback(data_source, fallback_map_share, name, is_namespace_pair=True)
    
    if df is None:
        skip_to_next()
        print(f"DEBUG: {name} failed all attempted tags.")
        raise ValueError(f"No {name} Tag Found")
    else:
        return used_tag, df
         
def get_eps(date_template=None):
    global df
    used_tag = 'calculated: net_income / shares#'
    df['eps'] = df['net_income'] / df['shares#']
    return used_tag

def get_total_sga(data_source, name):
    df_total_sga = None
    ga_used_tag, dfi_ga = downloadData('ga_fallbacks', 'ga')
    sm_used_tag, dfi_sm = downloadData('sm_fallbacks', 'sm')
            
    if dfi_ga is not None or dfi_sm is not None:
        valid_base = dfi_ga if dfi_ga is not None else dfi_sm
        
        if dfi_ga is None:
            dfi_ga = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'ga']).set_index('fy')
            ga_used_tag = 'ga: none'
        else:
            dfi_ga = dfi_ga.reset_index().set_index('fy')
            ga_used_tag = f"ga: {ga_used_tag}"
            
        if dfi_sm is None:
            dfi_sm = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'sm']).set_index('fy')
            sm_used_tag = 'sm: none'
        else:
            dfi_sm = dfi_sm.reset_index().set_index('fy')
            sm_used_tag = f"sm: {sm_used_tag}"
        
        df_total_sga = dfi_ga[['ga']].add(dfi_sm[['sm']], fill_value=0)
        df_total_sga = pd.DataFrame(df_total_sga.sum(axis=1))
        df_total_sga.columns = [name]
        base_timestamp = valid_base.reset_index().set_index('fy')[['end', 'fp', 'filed']]
        df_total_sga = df_total_sga.join(base_timestamp, how='left').reset_index()
        df_total_sga.set_index('end', inplace=True)
        used_tag = ga_used_tag + " " + sm_used_tag
        
    if dfi_ga is None and dfi_sm is None:
        if ticker in ['BRK-A', 'BRK-B']:        
            print("ℹ️ SG&A expense not found, automatically creating empty time series to keep pipeline smooth.")
            df_total_sga = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'val'])
            df_total_sga = df_total_sga.set_index('end')
            df_total_sga.rename(columns={"val": name}, inplace=True)
            used_tag = 'none'
        else:
            raise ValueError("No SellingGeneralAndAdministrativeExpense Tag Found")
    return used_tag, df_total_sga

def update_curr_liabilities():
    global df
    curr_liabilities = date_template.copy()  # date_template has 4 columns
    for tag in curr_liabilities_tags:
        used_tag, val = downloadData(tag, tag)
        if val is not None:
           curr_liabilities = pd.merge(curr_liabilities, val, on = ['fy','fp','filed','end'], how='left', validate='1:1') 
           data_cols = curr_liabilities.columns.drop(['fy', 'fp', 'filed', 'end'])
    if len(data_cols) > 0:
        curr_liabilities['curr_liabilities_sum'] = curr_liabilities[data_cols].fillna(0).sum(axis=1)
        curr_liabilities = curr_liabilities.set_index('end')
        df.update(curr_liabilities[['curr_liabilities_sum']].rename(columns={'curr_liabilities_sum': 'curr_liabilities'}))
        
def get_currasset(data_source, name):
    df_currasset = None
    asset_uesd_tag, dfi_asset = downloadData('Assets', 'asset')
    ppe_uesd_tag, dfi_ppe = downloadData('PropertyPlantAndEquipmentNet', 'ppe')
    gw_uesd_tag, dfi_gw = downloadData('Goodwill', 'gw')
    emi_uesd_tag, dfi_emi = downloadData('EquityMethodInvestments', 'emi')
    used_tag_list =['Assets']
    
    if dfi_ppe is not None or dfi_gw is not None or dfi_emi is not None:
        if dfi_ppe is None:
            dfi_ppe = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'ppe']).set_index('fy')
        else:
            dfi_ppe = dfi_ppe.reset_index().set_index('fy')
            used_tag_list.append(ppe_uesd_tag)
            
        if dfi_gw is None:
            dfi_gw = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'gw']).set_index('fy')
        else:
            dfi_gw = dfi_gw.reset_index().set_index('fy')
            used_tag_list.append(gw_uesd_tag)
            
        if dfi_emi is None:
            dfi_emi = pd.DataFrame(columns=['end', 'fy', 'fp', 'filed', 'emi']).set_index('fy')
        else:
            dfi_emi = dfi_emi.reset_index().set_index('fy')
            used_tag_list.append(emi_uesd_tag)
        used_tag = " + ".join(used_tag_list)
        
        dfi_asset = dfi_asset.reset_index().set_index('fy')
        df_currasset = dfi_asset[['asset']].sub(dfi_ppe[['ppe']], fill_value=0)\
            .sub(dfi_gw[['gw']], fill_value=0)\
            .sub(dfi_emi[['emi']], fill_value=0)
        df_currasset = pd.DataFrame(df_currasset.sum(axis=1))
        df_currasset.columns = [name]
        base_timestamp = dfi_asset.reset_index().set_index('fy')[['end', 'fp', 'filed']]
        df_currasset = df_currasset.join(base_timestamp, how='left').reset_index()
        df_currasset.set_index('end', inplace=True)
    else:
        used_tag = 'Assets'
    return used_tag, df_currasset 

def get_recurrent_profit():
# eg. ORCL it does not have recurrent profit tag data, need to back calculate using non-operating income
    global df
    used_tag_list = []
    dfiRaw = df.loc[:,['fy','fp','filed','operating_income']].copy()
    dfiRaw = dfiRaw.reset_index().set_index('fy')
    
    used_tag_1, non_op_1 = downloadData('NonoperatingIncomeExpense','non_operating_income')
    used_tag_2, non_op_2 = downloadData('OtherNonoperatingIncomeExpense','other_non_operating_income')

    is_op1_invalid = (non_op_1 is None or non_op_1.empty)
    is_op2_invalid = (non_op_2 is None or non_op_2.empty)
    
    if is_op1_invalid and is_op2_invalid:
        raise ValueError("No IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest Tag Found")
    else:
        def transform_df(df_target, df_ref, column_name):
            # To handle case where one of them is None, convert all of them to empty DataFrames for easy summation
            if df_target is None or df_target.empty: 
                return pd.Series(0, index=df_ref.index)
            df_target = df_target.reset_index(drop=True).set_index('fy')
            return df_target[column_name].reindex(df_ref.index).fillna(0)

        if not (non_op_1 is None or non_op_1.empty):
            used_tag_list.append(used_tag_1)
        if not (non_op_2 is None or non_op_2.empty):
            used_tag_list.append(used_tag_2)
        
        non_op_1 = transform_df(non_op_1, dfiRaw, 'non_operating_income')
        non_op_2 = transform_df(non_op_2, dfiRaw, 'other_non_operating_income')
        
        dfiRaw['recurrent_profit'] = dfiRaw['operating_income'] + non_op_1.values + non_op_2.values
        dfiRaw = dfiRaw.drop(columns=['operating_income'])
        dfiRaw = dfiRaw.reset_index().set_index('end')
        used_tag = " + ".join(used_tag_list)
        return used_tag, dfiRaw
    
def get_market_reaction_price(row, daily_prices):
    # 
    
    filing_date = row['filed']
    if pd.isna(filing_date): 
        return None
    
    # Daily_prices: ticker of input stock_price dataframe
    after_filing = daily_prices.loc[filing_date:].iloc[:5] 
    if not after_filing.empty:
        return after_filing['Close'].mean()
    
    # In case no hist data(stock price) after filed date/ Company Suspension. Avoid crash in .mean()
    return None 

def get_all_tags(data_source):
    # List all available EDGAR tags for debug
    
    if not data_source:
        return "No data source available."
    
    tags = sorted(list(data_source.keys()))
    
    return tags

def auto_search_tags(missing_tag, data_source):
    # Search for alternate tag name for missing tag
    
    if not data_source:
        return []
    
    # Separate words in tag name, e.g. "GrossProfit" -> ['Gross', 'Profit']
    raw_words = re.findall(r'[A-Z][a-z]*', missing_tag)
    
    ignore_word = {
        'And', 'At', 'Including', 'Excluding', 'Increase', 'Decrease', 
        'Than', 'Of', 'Before', 'After', 'In', 'Or', 'With', 'By', 
        'From', 'To', 'During', 'Period', 'Effect'
    }
    
    search_words = [word for word in raw_words if word not in ignore_word]    
    
    all_tags = data_source.keys()

    potential_matches = [
        t for t in all_tags 
        if any(word in t for word in search_words)
    ]
    
    return potential_matches
        
def export_csv():
# For saving database query command result in csv file to desktop
# Call in console after running program when decided to save a copy
    filename = f"{database_table_name}_{now}.csv"
    
    target_desktop = find_desktop()
    path = os.path.join(target_desktop, filename)
    
    try:
        query = f"SELECT * FROM {database_table_name} ORDER BY ticker, fy, fp"
        df = pd.read_sql(query, engine)
        df = df.fillna("NULL")
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print(f"✅ Successfully exported to: {path}")
    except Exception as e:
        print(f"❌ Export failed: {e}")

#%% (3) Main

companyTickers = requests.get("https://www.sec.gov/files/company_tickers.json",
    headers=headers)
companyInfo = pd.DataFrame.from_dict(companyTickers.json(), orient='index')
companyInfo['cik_str'] = companyInfo['cik_str'].astype(str).str.zfill(10)

# 🆕 Filter companyInfo to those having the cik listed in failed_ciks_list
retry_df = companyInfo[companyInfo['cik_str'].isin(failed_ciks_list)]

loop_start_time = time.perf_counter()
print(f"--- Run Start: {now} ---")

# (i) Loop for each company to access filing metadata & facts data.
for index, row in retry_df.iterrows():
    start_time = time.perf_counter()
    current_status = "Fail"
    error_msg = ""
    used_namespace = None
    
    try:
        cik = row['cik_str']
        ticker = row['ticker']
        company_name = row['title']
        source_index = index
        print(f"Retrying: {cik} - {ticker} ({company_name})")
        # =====================================================================
        # Company filing metadata : get industry info
        filingMetadata = requests.get(f'https://data.sec.gov/submissions/CIK{cik}.json',
            headers=headers)
        if filingMetadata.status_code != 200:
            error_msg = f"Request Failure on filingMetadata: {filingMetadata.status_code} ({filingMetadata.reason})"
            print(error_msg)
            continue
        sic = filingMetadata.json()['sic']
        sicDescription = filingMetadata.json()['sicDescription']
        industry = sic + " " + sicDescription
        # =====================================================================
        # Company facts data : get tag data
        companyFacts = requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json',
            headers=headers)
        if companyFacts.status_code != 200:
            error_msg = f"Request Failure on companyFacts: {companyFacts.status_code} ({companyFacts.reason})"
            print(error_msg)
            continue
        raw_json = companyFacts.json()
        # =====================================================================
        # (ii) Get first item tag data
        dfRaw, used_namespace, data_source = get_financial_value(raw_json, FirstItem)
        
        if dfRaw is None:
            skip_to_next()                
            raise ValueError(f"No {FirstItemName} Tag Found")
        else:
            dfRaw = pd.DataFrame(dfRaw)

        dfRaw['end'] = pd.to_datetime(dfRaw['end']) 
        dfRaw['filed'] = pd.to_datetime(dfRaw['filed']) # 'filed' : report release date 
        
        # Only study companies with continuous 10-K reports between year 2019 to 2025 (inclusive)
        earliest_fy = dfRaw['fy'].min()
        latest_fy = dfRaw['fy'].max()
        has_history = earliest_fy <= StudyStart
        is_still_alive = latest_fy >= StudyEnd
        
        # Establish framework for main df 
        df = dfRaw[(dfRaw['form'].str.match(REPORT_FORM_FILTER, na=False)) &
                   (dfRaw['fy'] >= StudyStart)].loc[:,['end','fy','fp','filed','val']]
        
        df = df.sort_values(by=['end', 'filed']).drop_duplicates(subset=['fy','fp'], keep='last')
        
        has_enough_data = len(df) >= expected_records
        if not (has_history and is_still_alive and has_enough_data):
            error_msg = f"Skip CIK {cik} ({ticker} {company_name}): Data incomplete or period not matched."
            print(error_msg) 
            skip_to_next()
            continue
        
        FiscalMonth = dfRaw['end'].iat[0].strftime('%b').upper() 
        
        date_template = df[['fy', 'fp', 'filed', 'end']]
        
        df = df.set_index('end')
        
        df.rename(columns={"val": FirstItemName}, inplace=True)
        df.insert(0,'industry',industry)
        df.insert(0,'name',company_name)
        df.insert(0,'ticker',ticker)
        
        df['tag_history'] = ""
        # =====================================================================
        # (iii) Add all items into main df columns
        for tag, name in zip(itertools.chain(revenueDataTag,assetDataTag,cashflowDataTag)
                             ,itertools.chain(revenueDataName,assetDataName,cashflowDataName)):
            used_tag, addData = downloadData(tag, name)
            df['tag_history'] = df['tag_history'].apply(lambda x: f"{x}; {name} = {used_tag}" if x else name + " = " + used_tag)
            if addData is None and tag in ['InventoryNet', 'EarningsPerShareBasic', 'EarningsPerShareBasic']:
                continue
            df=pd.merge(df, addData, on = ['fy','fp','filed','end'], how='left', validate='1:1') 
            
        if industry in ['6021 National Commercial Banks', '6331 Fire, Marine & Casualty Insurance']:
            update_curr_liabilities()
        # =====================================================================
        # (iv) Calculated items:
        df = df.assign(
            gross_profit = df['gross_revenue'] - df['cost'].fillna(0),
            expense_others = lambda x: x['gross_profit'].sub(x['operating_income']).sub(x['expense_general/admin'], fill_value=0),
            operating_income = df['operating_income'].fillna(df['recurrent_profit']),  # eg. LLY changed structure in year 2020 to not separate operating/non-operating income
            nonoperating_income = lambda x: x['recurrent_profit'] - x['operating_income'],
            profit = df['recurrent_profit'] - df['tax'],
            noncontrolling_interest = lambda x: x['net_income'] - x['profit'],
            liabilities = df['asset'] - df['equity'],
            inven_other = df['inventory'].fillna(0) + df['other_currasset'].fillna(0), 
            cash = lambda x: x['currasset'] - x['inven_other'].fillna(0),
            lt_asset = df['asset'] - df['currasset'],
            lt_liabilities = lambda x: x['liabilities'] - x['curr_liabilities'],
            cap_ex = df['payment_cap'].fillna(0) + df['payment_intangible'].fillna(0),
            fcf = lambda x: x['operating_cash'] - x['cap_ex']
            )
                    
        # Re-order columns
        new_order = ['ticker','name','industry','fy','fp', 'filed','gross_revenue',
                     'cost','gross_profit','expense_general/admin',
                     'expense_others','operating_income',
                     'nonoperating_income','recurrent_profit','tax','profit',
                     'noncontrolling_interest','net_income','shares#','eps',
                     'asset','equity','liabilities','currasset','inventory',
                     'other_currasset','inven_other','cash','lt_asset',
                     'curr_liabilities','lt_liabilities',
                     'operating_cash','investing_cash','payment_cap','payment_intangible','cap_ex','financing_cash','fcf','cash_end',
                     'inventory_delta','dividend','tag_history']
        df=df[new_order]
        # =====================================================================
        # (v) Get stock price
        stockticker = yf.Ticker(ticker)
        hist_adj = stockticker.history(start="2019-1-1", auto_adjust=True) # adjusted close : included stock split impact
        hist_adj.index = pd.to_datetime(hist_adj.index).tz_localize(None)  # Remove timezone info from date index to prevent Timestamp comparison errors during merge
        
        hist_unadj = stockticker.history(start="2019-1-1", auto_adjust=False) # unadjusted close : excluded stock split impact
        hist_unadj.index = pd.to_datetime(hist_unadj.index).tz_localize(None)
        
        df['stock_price'] = df.apply(lambda row: get_market_reaction_price(row, hist_adj), axis=1)
        df['stock_price_unadjusted'] = df.apply(lambda row: get_market_reaction_price(row, hist_unadj), axis=1)
        # ===================================================================== 
        # (vi) Calculate derivatives
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
        # =====================================================================
        # Rearrange 'tag_history' column at the end
        cols = df.columns.tolist()
        cols.remove('tag_history')
        cols.append('tag_history')
        df = df[cols]
        # =====================================================================
        # (vii) Add df into PostgreSQL database. if_exists takes 'append' mode instead of 'replace' mode.
        df.to_sql(database_table_name, engine, if_exists='append', index=False, method='multi',chunksize=1000)
        success_count += 1
        current_status = "Success"
        skip_to_next()
        
#%% (4) Handle error & record run_log
    except ValueError as e:
    # Handle for the missed tag data which is out of 'allow_nan_tags'
        error_msg = str(e)
        
        if "Critical API Error" in error_msg:
            print("Critical error, stopping program.")
            break  # stop and exit the entire for loop
        else:
            print(f"Skipping {ticker}: {error_msg}")
            traceback.print_exc()
            # --- Collect failed company tag information ---
            try:
                all_tags = get_all_tags(data_source)
                failed_companies_tags_data.append({
                    'index': index,
                    'ticker': ticker,
                    'company_name': company_name,
                    'tags': all_tags
                })
                print(f"📝 Recorded available tags for {ticker} to staging area.")
            except Exception as collect_err:
                print(f"⚠️ Error staging tag data: {collect_err}")
            # ----------------------------
            match = re.search(r"No (.+) Tag Found", error_msg)
            
            if match:
                missing_tag = match.group(1)
                suggestions = auto_search_tags(missing_tag, data_source)
                print(f"Tag not found: {missing_tag}\nSuggested alternative tags: {suggestions}")
            continue
        
    except Exception as e:
        error_msg = str(e)
        # Get complete error traceback list
        all_frames = traceback.extract_tb(e.__traceback__)
        # Search backwards from last line (bottom layer), looking for own code rather than pandas or built-in libraries
        my_frame = None
        for frame in reversed(all_frames):
            # As long as filename does not include site-packages (third-party library) and is main running file
            if "site-packages" not in frame.filename and "internal" not in frame.filename:
                my_frame = frame
                break
        # If own code line number found, print it
        if my_frame:
            filename = os.path.basename(my_frame.filename) # Get filename only (e.g. main.py) without long path
            line_no = my_frame.lineno
            func_name = my_frame.name
            print(f"❌ Warning: Error processing Index={index} Ticker={row['ticker']}!")
            print(f"   👉 Caught culprit! Error occurred in your code: [{filename}] line {line_no} (in `{func_name}` function)")
            print(f"   👉 Error reason: {error_msg}")
        else:
            # If not found (extremely rare), fallback to printing bottom-layer crash point
            print(f"❌ Warning: Error processing Index={index} Ticker={row['ticker']}: {error_msg} (Bottom-layer line: {all_frames[-1].lineno})")
        continue
    
    finally:
        updated_log_table = 'Fail'
        # ===================================================================== 
        # Add Follow-up status/error in annual_financials_full_log.
        # Those two new columns have been added inside Postgresql using SQL command
        try:          
            with engine.connect() as conn:            
                update_query = text(f"""
                    UPDATE {database_log_table_name} 
                    SET status_after_recovery2 = :status, 
                        error_after_recovery2 = :error 
                    WHERE cik = :cik
                """)
                conn.execute(update_query, {"status": current_status, "error": error_msg, "cik": cik})
                conn.commit()
                updated_log_table = 'Success'
        except Exception as e:
            print(f"annual_financials_full_log update failed: {e}")
            updated_log_table = 'Fail'
        # =====================================================================
        run_log.append({
            'source_index': source_index,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'cik': cik,
            'ticker': ticker,
            'company_name': company_name,
            'namespace': used_namespace, # store gaap or ifrs
            'status': current_status,
            'error': error_msg,
            'updated_log_table': updated_log_table
            })
        
run_log_df = pd.DataFrame(run_log)

if success_count > 0:
    print(f"Successfully synced {success_count} company datasets to PostgreSQL!")
else:
    print("Sync failed: No company datasets successfully processed.")

if failed_companies_tags_data:
# Aggregate all the available tag names for all the failed extraction 
# due to missing tag name, for the aid to complement fallback_map
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Available tags for failed companies_{timestamp}.txt"
        path = os.path.join(find_desktop(), filename)
        with open(path, "w", encoding="utf-8") as f:
            for item in failed_companies_tags_data:
                header_line = f"Index: {item['index']} | Ticker: {item['ticker']} | Name: {item['company_name']}\n"
                f.write(header_line)
                f.write("-" * len(header_line) + "\n")
                for tag in item['tags']:
                    f.write(f"{tag}\n")
                f.write("\n\n" + "="*80 + "\n\n")
        print(f"\n🚀 All failed company tags successfully exported to desktop: {filename}")
    except Exception as write_err:
        print(f"\n⚠️ Error saving tag file: {write_err}")

loop_end_time = time.perf_counter()
loop_duration = loop_end_time - loop_start_time
formatted_time = str(timedelta(seconds=int(loop_duration)))
print(f"--- Run End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
print(f"Loop duration: {formatted_time}")

# export database table and run_log in csv format to desktop
export_csv()
run_log_df.to_csv(os.path.join(find_desktop(), f"run_log_df_{now}.csv"), index=False)
winsound.MessageBeep(64)  # System Information sound

# Show success rate
success_count = (run_log_df['status'] == 'Success').sum()
total_count = len(run_log_df)
success_rate = (success_count / total_count) * 100
print("--- Final Data Statistics ---")
print(f"Success rate: {success_rate:.2f}% ({success_count}/{total_count})")

# Stop storing console output message
if isinstance(sys.stdout, Logger):
    sys.stdout.close()
    sys.stdout = sys.__stdout__ # Restore standard output
