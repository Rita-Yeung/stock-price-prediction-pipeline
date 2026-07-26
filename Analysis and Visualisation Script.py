"""
Purpose: Statistical analysis and predictive modeling on financial database, and visualization
"""
__author__ = "Rita Yeung"

#%% Library
from sqlalchemy import create_engine
import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import numpy as np
import seaborn as sns
from functools import partial
import math
import textwrap
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator
from sklearn.impute import SimpleImputer
import joblib
# Regression
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler
# forest tree
from sklearn.ensemble import RandomForestRegressor
from sklearn.tree import DecisionTreeRegressor
from sklearn.svm import SVR
from xgboost import XGBRegressor

#%% Definition & Initialization

load_dotenv()
db_password = os.getenv('DB_PASSWORD')
engine = create_engine(f'postgresql://postgres:{db_password}@localhost:5432/us_stock')

clean_table_name = 'annual_financials_clean'
damaged_table_name = 'damaged_data'
less_table_name = 'company_less_data'
log_table_name = 'annual_financials_full_log'

pd.set_option('future.no_silent_downcasting', True)
PER=20
now = datetime.now().strftime("%Y-%m-%d %H-%M-%S")

raw_factor_list = ['gross_revenue', 'cost', 'gross_profit', 'expense_general/admin', 
                   'expense_others', 'operating_income', 'nonoperating_income', 'recurrent_profit', 
                   'tax', 'profit', 'noncontrolling_interest', 'net_income', 'shares#', 'eps', 
                   'asset', 'equity', 'liabilities', 'currasset', 'inventory', 'other_currasset', 
                   'inven_other', 'cash', 'lt_asset', 'curr_liabilities', 'lt_liabilities', 
                   'operating_cash', 'investing_cash', 'payment_cap', 'payment_intangible', 
                   'cap_ex', 'financing_cash', 'fcf', 'cash_end', 'inventory_delta', 'dividend']

breakpoint_indicator = {'equity_ratio' :  [0.1, 0.2,0.5],
                        'current_ratio' :  [0.7, 1,2],
                        'quick_ratio' : [0.5,0.7,1.5],
                        'fixedasset_per_ltcapital_ratio' : [1.2,1,0.8],
                        'fixedasset_per_equity_ratio' : [1.5,1.2,1],
                        'cash_flow_ratio': [0.5, 1.0, 1.5],
                        'ocfperprofit_ratio': [0.5, 0.8, 1.0],
                        'cash_reinvest_ratio': [0.05, 0.1, 0.15],
                        'debt_assurance_ratio': [0.1, 0.25, 0.4]
    }

model_factor_list = ['risk_factor', 'career_value', 'asset_value',  
                     'theoretical_roe', 'theoretical_pbr', 'theoretical_price',
                     'theoretical_price_upper', 'financial_leverage_ratio', 
                     'leverage_factor', 'roa_discount', 'cashflowps_ratio', 
                     'asset_pershare', 'cash_per_asset_ratio']

price_list = ['stock_price', 'stock_price_unadjusted',  'market_cap', 'per', 'pbr']

exclude_list = (['ticker', 'industry', 'name', 'fy', 'fp', 'filed', 
                 'tag_history'] + list(breakpoint_indicator.keys()))

#%% Functions

def apply_financial_analysis(df):
    '''
    Process on raw financial data to calculate theoretical stock price
    , using revised version of 'Kessan model' in book (ISBN=9786267321430)
    '''
    df_processed = df.copy()

    df_processed = df_processed.assign(
        per = df['stock_price'] / df['eps'],
        equity_ratio = df['equity'] / df['asset'],
        bps = df['equity'] / df['shares#'],
        pbr = lambda x: x['stock_price'] / x['bps'],
        
        # 1. Set constraint for later-on formula
        capped_eps = lambda x: x['eps'].clip(upper=x['bps'] * 0.6),
        capped_roa = lambda x: x['roa'].clip(upper=0.3),
        
        cash_flow_ratio = df['operating_cash'] / df['curr_liabilities'],
        cash_reinvest_ratio = (df['operating_cash'] - df['dividend'].fillna(0))/(df['lt_asset'] + df['lt_liabilities'] + (df['cash'] + df['inven_other'].fillna(0) - df['curr_liabilities'])),
        cash_per_asset_ratio = df['operating_cash'] / df['asset'],
        cashflowps_ratio = (df['operating_cash'] - df['dividend'].fillna(0)) / df['shares#'],
        ocfperprofit_ratio = df['operating_cash'] / df['profit'],
        debt_assurance_ratio = df['operating_cash'] /( df['curr_liabilities'] + df['lt_liabilities']),
        
        roa_discount = lambda x: x['equity_ratio'].apply(lambda val: 0.8 if val>0.8 else 0.75 if val >0.67 else 0.7 if val>0.5 else 0.65 if val>0.33 else 0.6 if val>0.1 else 0.5 if val>0 else 0),
        
        roa = df['net_income'] / df['asset'],
        financial_leverage_ratio = lambda x: 1 / x['equity_ratio'],
        
        # 2. Leverage_factor and risk_factor after update
        leverage_factor = lambda x: x['financial_leverage_ratio'].apply(lambda val: 1.5 if val > 3 else 1.36 if val > 2.5 else 1.2 if val > 2 else 1.0),
        
        risk_factor = lambda x: x['pbr'].apply(lambda val: 1.0 if val >= 0.5 else 0.8 if val >= 0.41 else 0.66 if val >= 0.34 else 0.5 if val >= 0.26 else 0.33 if val >= 0.21 else (val/5*50+50)/100 if val >= 0.04 else 0.005),
        
        # 3. Apply logic in book (call the calculated capped_eps in (1), etc.)
        asset_value = lambda x: x['roa_discount'] * x['bps'],
        business_value = lambda x: x['capped_eps'] * x['capped_roa'] * 150 * x['leverage_factor'],
        
        theoretical_price = lambda x: (x['asset_value'] + x['business_value']) * x['risk_factor'],
        
        current_ratio = (df['cash'] + df['inven_other'].fillna(0)) / df['curr_liabilities'],
        quick_ratio = (df['cash'] ) / df['curr_liabilities'],
        fixedasset_per_ltcapital_ratio = df['lt_asset'] / (df['equity'] + df['lt_liabilities']),
        fixedasset_per_equity_ratio = df['lt_asset'] / df['equity'],
        roe = df['net_income'] / df['equity'],
        
        theoretical_price_upper = lambda x: x['theoretical_price'] * 2,
        theoretical_roe = lambda x: x['theoretical_price'] / x['eps'],
        theoretical_pbr = lambda x: x['theoretical_price'] / x['bps'],
        asset_pershare = df['asset'] / df['shares#'],
        market_cap = df['stock_price_unadjusted'] * df['shares#']
    )
    
    return df_processed

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
    
def calculate_score(row, ratio, breakpoints):
    val = row[ratio]
    is_reverse = breakpoints[0] > breakpoints[-1]
    if not is_reverse:
        if val < breakpoints[0]: return -5
        elif val < breakpoints[1]: return 0
        elif val < breakpoints[2]: return 5
        else: return 8
    else:
        if val > breakpoints[0]: return -5
        elif val > breakpoints[1]: return 0
        elif val > breakpoints[2]: return 5
        else: return 8

def get_broad_category(industry_str):
    '''
    Conversion of 'Standard Industrial Classification (SIC) Code' 
    into 'Office'(named as broad_industry in this script)
    '''
    try:
        # Take out the numeric part in string (default format: '3433 HEATING...')
        code_str = str(industry_str).split(' ')[0]      
        sic = int(code_str)
        if 100 <= sic <= 999: return 'Agriculture, Forestry and Fishing'
        elif 1000 <= sic <= 1499: return 'Mining'
        elif 1500 <= sic <= 1799: return 'Construction'
        elif 2000 <= sic <= 3999: return 'Manufacturing'
        elif 4000 <= sic <= 4999: return 'Transportation, Comm, Electric, Gas & Sanitary'
        elif 5000 <= sic <= 5199: return 'Wholesale Trade'
        elif 5200 <= sic <= 5999: return 'Retail Trade'
        elif 6000 <= sic <= 6799: return 'Finance, Insurance and Real Estate'
        elif 7000 <= sic <= 8999: return 'Services'
        elif 9100 <= sic <= 9999: return 'Public Administration'
        else: return 'Other/Unclassified'
    except:
        return 'Other/Unclassified'

#%% Main - Preprocess

clean_data = pd.read_sql(f"SELECT * FROM {clean_table_name}", engine)
clean_data = apply_financial_analysis(clean_data)

all_db_cols = clean_data.columns.tolist()
ratio_list = list(breakpoint_indicator.keys())
derived_others = [c for c in all_db_cols if c not in raw_factor_list + 
                  ratio_list + exclude_list + model_factor_list + price_list]

clean_data['ratio_score'] = 0
for ratio, bp in breakpoint_indicator.items():
    if ratio in clean_data.columns:
        clean_data['ratio_score'] += clean_data.apply(lambda row: calculate_score(row, ratio, bp), axis=1)

# Apply industry mapping
clean_data['broad_industry'] = clean_data['industry'].apply(get_broad_category)

plt.close('all')
clean_data['broad_industry'] = clean_data['industry'].apply(get_broad_category)

clean_data['ratio_score'] = 0
for ratio, bp in breakpoint_indicator.items():
    if ratio in clean_data.columns:
        func = partial(calculate_score, ratio=ratio, breakpoints=bp)
        clean_data['ratio_score'] += clean_data.apply(func, axis=1)

all_analysis_list = raw_factor_list + ratio_list + derived_others \
                    + ['ratio_score'] + model_factor_list + price_list
               
# Force to convert all numeric columns to float, and turn the unconvertable ones into NaN
# (currently, payment_intangible and cash_end are in text)
for f in all_analysis_list:
    if f in clean_data.columns:
        clean_data[f] = pd.to_numeric(clean_data[f], errors='coerce')     

# =============================================================================
# Turn item into per share amount for normalisation
base_factors = [
    'cap_ex', 'cash_end', 'cash', 'cost', 'curr_liabilities', 
    'currasset', 'dividend', 'expense_general/admin', 'expense_others', 
    'fcf', 'financing_cash', 'gross_profit', 'gross_revenue', 
    'inven_other', 'inventory_delta', 'inventory', 'investing_cash', 
    'liabilities', 'lt_asset', 'lt_liabilities', 'noncontrolling_interest', 
    'nonoperating_income', 'operating_cash', 'operating_income', 
    'other_currasset', 'payment_cap', 'payment_intangible', 'profit', 
    'recurrent_profit', 'tax'
]

# Avoid divided by zero to produce Inf error
clean_data['shares_safe'] = clean_data['shares#'].replace(0, np.nan)
per_share = []

# Calculate per sahre value and add suffix '_per_share'
for factor in base_factors:
    if factor in clean_data.columns:
        new_col = f"{factor}_per_share"
        clean_data[new_col] = clean_data[factor] / clean_data['shares_safe']
        per_share.append(new_col)

correlation_factor = per_share + ['bps', 'shares#', 'eps', 'asset_pershare', 'ratio_score']

# Log conversion on correlation_factor (except shares# and ratio_score)
cols_to_log = [c for c in correlation_factor if c not in ['shares#', 'ratio_score']]

for col in cols_to_log:
    if col in clean_data.columns:
        temp_data = clean_data[col].copy()
        temp_data[temp_data < 0] = 0
        clean_data[col] = np.log1p(temp_data.replace([np.inf, -np.inf], np.nan).fillna(0))

# =============================================================================

# Assign color for each broad_industry
all_broad_industry = clean_data['broad_industry'].unique()
cmap = mpl.colormaps.get_cmap('tab10')
color_map = {ind: cmap(i / len(all_broad_industry)) for i, ind in enumerate(all_broad_industry)}

plot_data = clean_data.copy()

# Remove outliner (only take 1% to 99% quartile of data)
lower_limit = plot_data['theoretical_price'].quantile(0.01)
price_lower_limit = plot_data['stock_price'].quantile(0.01)
upper_limit = plot_data['theoretical_price'].quantile(0.99)
price_upper_limit = plot_data['stock_price'].quantile(0.99)

plot_data = plot_data[
    (plot_data['theoretical_price'] >= lower_limit) & 
    (plot_data['stock_price'] >= price_lower_limit) & 
    (plot_data['theoretical_price'] <= upper_limit) &
    (plot_data['stock_price'] <= price_upper_limit)
]

#%% ============   Fig 0: Company count and market_cap    =====================
# 1. Data preparation
industry_stats = clean_data.groupby('broad_industry').agg({
    'ticker': 'count',
    'market_cap': 'sum'
}).rename(columns={'ticker': 'company_count'})

# Define a function to group small categories below the threshold (e.g., 0.35%) into "All other industries"
def group_small_categories(df, col, threshold=0.0035):
    total = df[col].sum()
    mask = (df[col] / total) < threshold
    if mask.any():
        other_sum = df.loc[mask, col].sum()
        df_filtered = df[~mask].copy()
        df_filtered.loc['All other industries', col] = other_sum
        return df_filtered
    return df

# Filter company count and market cap separately to avoid cluttering the pie chart with tiny categories
stats_count_pie = group_small_categories(industry_stats, 'company_count', 0.0035)
stats_cap_pie = group_small_categories(industry_stats, 'market_cap', 0.005)

# 2. Plot
fig, axes = plt.subplots(1, 2, figsize=(16, 8))

# Left plot: Ratio of company counts by industry
axes[0].pie(
    stats_count_pie['company_count'], 
    labels=stats_count_pie.index, 
    autopct='%1.1f%%', 
    startangle=140, 
    labeldistance=1.1, 
    pctdistance=0.8
)
axes[0].set_title('Ratio of Company Counts by Industry', fontsize=14)

# Right plot: Ratio of market cap by industry
axes[1].pie(
    stats_cap_pie['market_cap'], 
    labels=stats_cap_pie.index, 
    autopct='%1.1f%%', 
    startangle=140, 
    labeldistance=1.1, 
    pctdistance=0.8
)
axes[1].set_title('Ratio of Market Cap by Industry', fontsize=14)

plt.suptitle('Fig 0: Industry Market Structure: Count vs Market Cap', fontsize=18)
plt.tight_layout()
plt.savefig('fig0_industry_structure.png', dpi=300, bbox_inches='tight')
plt.show()

#%% ==========   Fig 1a: Factor Correlation to Stock Price    =================
results = plot_data[correlation_factor + ['stock_price']].corr()['stock_price'].drop('stock_price')
results = results.sort_values(ascending=True)

# Positively related labelled in green; Negatively related labelled in red.
bar_colors = ['green' if val > 0 else 'red' for val in results.values]

plt.figure(figsize=(10, 8))
ax = results.plot(kind='barh', color=bar_colors, alpha=0.7)
ax.xaxis.set_major_locator(MultipleLocator(0.1))
plt.title('Fig 1: Overall Correlation with Stock Price')
plt.xlabel('Correlation Coefficient')
plt.grid(axis='x', linestyle='--', alpha=0.6)
plt.tight_layout()
plt.savefig('fig1a_overall_correlation_with_stock_price.png', dpi=300, bbox_inches='tight')
plt.show()

#%% ==========   Fig 1b: Factor Correlation to Stock Price by Industry   ======

# 1. Get all the broad_indsutry
industries = sorted([ind for ind in plot_data['broad_industry'].unique() if ind != 'Other/Unclassified'])
num_industries = len(industries)
cols = 3
rows = math.ceil(num_industries / cols)

# 2. Build plot with multiple subplots
fig, axes = plt.subplots(rows, cols, figsize=(22, rows * 5.5), sharex=True)
axes = axes.flatten()

for i, ind in enumerate(industries):
    ax = axes[i]
    
    # filter out data under the broad_indsutry
    ind_subset = plot_data[plot_data['broad_industry'] == ind]
    
    # Avoid error by ensuring sample size is enough for calculating correlation coefficient
    if len(ind_subset) < 5:
        ax.text(0.5, 0.5, f'Insufficient Data\n(N={len(ind_subset)})', ha='center', va='center', fontsize=12)
        ax.set_title(textwrap.fill(ind, width=35), fontsize=12, fontweight='bold')
        continue
        
    # Calculate correlation coefficients of the correlation factors to stock price
    corr_series = ind_subset[correlation_factor + ['stock_price']].corr(numeric_only=True)['stock_price'].drop('stock_price', errors='ignore')
    corr_series = corr_series.dropna().sort_values(ascending=True)
    
    if corr_series.empty:
        ax.text(0.5, 0.5, 'No Correlation Data', ha='center', va='center', fontsize=12)
        ax.set_title(textwrap.fill(ind, width=35), fontsize=12, fontweight='bold')
        continue

    # Color: Positively related = green; Negatively related = red.
    bar_colors = ['green' if val > 0 else 'red' for val in corr_series.values]
    
    # Plot horizontal bar chart
    corr_series.plot(kind='barh', color=bar_colors, alpha=0.7, ax=ax)

    ax.set_title(textwrap.fill(ind, width=35), fontsize=12, fontweight='bold', pad=10)
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    ax.axvline(0, color='black', linewidth=0.8, linestyle='-')
    ax.tick_params(axis='y', labelsize=9)

# Hide unnused subplots
for j in range(i + 1, len(axes)):
    axes[j].axis('off')

plt.suptitle('Fig 1b: Factor Correlation with Stock Price by Broad Industry', fontsize=20, y=0.99, fontweight='bold')
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig('fig1b_factor_correlation_with_stock_price_by_broad_industry.png', dpi=300, bbox_inches='tight')
plt.show()

#%% ==========   Fig 2: Ratios and stock price over years    ==================
# 1. Data aggregation: Average on every broad_industry and financial year (fy)
agg_data = plot_data.groupby(['broad_industry', 'fy'])[ratio_list + ['stock_price']].mean().reset_index()

# 2. Create canvas: 9 subplots
industries = agg_data['broad_industry'].unique()
fig, axes = plt.subplots(3, 3, figsize=(20, 18), sharex=True)
axes = axes.flatten()

# Define 9 different markers
markers = ['o', 's', '^', 'D', 'v', 'p', '*', 'X', 'h']

ratio_directions = {'equity_ratio' : 'green',
                    'current_ratio' :  'green',
                    'quick_ratio' : 'green',
                    'fixedasset_per_ltcapital_ratio' : 'red',
                    'fixedasset_per_equity_ratio' : 'red',
                    'cash_flow_ratio': 'green',
                    'ocfperprofit_ratio': 'green',
                    'cash_reinvest_ratio': 'green',
                    'debt_assurance_ratio': 'green'
                    }

# Create variable to store legend controlling code (handles)
combined_lines = []
combined_labels = []

for i, industry in enumerate(industries):
    ax = axes[i]
    industry_data = agg_data[agg_data['broad_industry'] == industry]
    
    # --- Y-axis 1: Stock price (Left)
    line1 = ax.plot(industry_data['fy'], industry_data['stock_price'], 
                    color='black', lw=2, label='Stock Price', marker='D', markersize=6)
    ax.set_ylabel('Stock Price', color='black', fontsize=12)
    
    # --- Y-axis 2: Financial ratios (Right) ---
    ax2 = ax.twinx()
    lines = []
    
    for j, ratio in enumerate(ratio_list):
        line_color = ratio_directions.get(ratio, 'black')
        
        line, = ax2.plot(industry_data['fy'], industry_data[ratio], 
                         color=line_color, # Use the determined red/green color
                         marker=markers[j % len(markers)], 
                         linestyle='--', alpha=0.7, label=ratio)
        lines.append(line)
        
    ax2.set_ylabel('Ratio', color='black', fontsize=12)
    
    ax.set_title(industry, fontsize=16, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6)
    
    # Combined legend: show legends of the 2 axes together
    if i == 0: 
        combined_lines = line1 + lines
        combined_labels = [l.get_label() for l in combined_lines]

# Clear unused subplots
for j in range(i + 1, len(axes)):
    axes[j].axis('off')

plt.suptitle('Fig 2: Relationship of Financial Ratios to Stock Price\nin Each Broad Industry (Aggregate) Over Time', fontsize=20, y=0.97)
plt.tight_layout(rect=[0, 0, 1, 0.95], h_pad=2.0, w_pad=2.0)
fig.legend(combined_lines, combined_labels, loc='lower right', 
           bbox_to_anchor=(0.99, 0.91), fontsize=11, ncol=2)
plt.savefig('fig2_relationship_of_financial_ratios_to_stock_price_in_each_broad_industry_over_time.png', dpi=300, bbox_inches='tight')
plt.show()

#%% ==== FIG 3: Correlation of factors to stock price (by broad industry) =====

num_factors = len(correlation_factor)
cols = 5
rows = math.ceil(num_factors / cols) # ensure correct no. of rows
fig, axes = plt.subplots(rows, cols, figsize=(24, rows * 4))
axes = axes.flatten()

# Prepare data dot size according to market_cap (Nan values all cleaned before this)
cap_log = np.log1p(clean_data['market_cap'].fillna(0))
norm_size = 40 * (cap_log - cap_log.min()) / (cap_log.max() - cap_log.min() + 1e-9) + 5

for i, factor in enumerate(correlation_factor):
    valid_data = clean_data.dropna(subset=[factor, 'stock_price'])
    
    for ind, color in color_map.items():
        subset = valid_data[valid_data['broad_industry'] == ind]
        if not subset.empty:
            axes[i].axhline(0, color='darkgray', linestyle='-', linewidth=1.5, alpha=0.7) # y=0
            axes[i].axvline(0, color='darkgray', linestyle='-', linewidth=1.5, alpha=0.7) # x=0
            
            axes[i].scatter(subset[factor], subset['stock_price'], 
                            alpha=0.3, s=norm_size.loc[subset.index], c=[color], label=ind)
            axes[i].grid(True, linestyle='--', alpha=0.5)
            axes[i].tick_params(axis='x')
    axes[i].set_title(factor, fontsize=12)

if len(correlation_factor) < len(axes):
    legend_ax = axes[-1]
    legend_ax.axis('off') # hide subplots border
    
    # Get handles and labels from subplot 1
    handles, labels = axes[0].get_legend_handles_labels()
    legend_ax.legend(handles, labels, loc='center', title='Legend:', fontsize=12, title_fontsize=14)

for j in range(len(correlation_factor), len(axes) - 1):
    axes[j].axis('off')

plt.suptitle('Fig 3: Correlation of factors to stock price (by broad industry)', fontsize=20, y=1.01)
plt.tight_layout(rect=[0, 0.02, 1, 1])
fig.text(0.01, 0.01, "Data dot's color legend is same as Fig 5.", fontsize=16, style='italic', color='dimgray')
plt.savefig('fig3_correlation_of_factors_to_stock_price.png', dpi=300, bbox_inches='tight')
plt.show()

#%% ========== FIG 4: Factor Correlation Heatmap by Broad Industry ============

g = sns.FacetGrid(plot_data, col="broad_industry", col_wrap=3, height=5)
g.map_dataframe(lambda data, **kwargs: 
                sns.heatmap(data[correlation_factor + ['stock_price']].corr()[['stock_price']], 
                            annot=False, cmap='coolwarm', vmin=-1, vmax=1))

for ax in g.axes.flatten(): 
    ax.set_xlabel('')  
    current_title = ax.get_title() 
    if "=" in current_title:
        industry_name = current_title.split("=")[-1].strip()
        wrapped_name = textwrap.fill(industry_name, width=20)
        ax.set_title(wrapped_name, fontsize=11, fontweight='bold')
    
plt.subplots_adjust(top=0.93, hspace=0.2) # hspace: increase vertical gap between subplots
g.fig.suptitle('Fig 4: Factor Correlation Heatmap by Broad Industry', fontsize=16)
plt.savefig('fig4_factor_correlation_heatmap_by_broad_industry.png', dpi=300, bbox_inches='tight')
plt.show()

#%% =======   FIG 5: Regression Plot of Stock Price    =================

# 1. Prepare data: Filter out NaNs to prevent plotting issues
plot_data_clean = plot_data.dropna(subset=['theoretical_price', 'stock_price'])
num_companies = len(plot_data_clean)

# == Calculate overall R^2 score (using theoretical_price to predict stock_price) ==
y_true_fig5 = plot_data_clean['stock_price']
y_pred_fig5 = plot_data_clean['theoretical_price']
ss_res_fig5 = np.sum((y_true_fig5 - y_pred_fig5) ** 2)
ss_tot_fig5 = np.sum((y_true_fig5 - np.mean(y_true_fig5)) ** 2)
r2_fig5 = 1 - (ss_res_fig5 / ss_tot_fig5)

# 2. Create canvas
plt.figure(figsize=(14, 8))

# 3. Scatter plot
ax = sns.scatterplot(
    data=plot_data_clean, 
    x='theoretical_price', 
    y='stock_price', 
    hue='broad_industry', 
    style='broad_industry', 
    alpha=0.6, 
    s=40, 
    palette='tab10' 
)

# 4. Regression Line
sns.regplot(
    data=plot_data_clean, 
    x='theoretical_price', 
    y='stock_price', 
    scatter=False, 
    color='red', 
    line_kws={'lw': 2, 'ls': '--'},
    truncate=False
)

plt.title('Fig 5: Theoretical Stock Price vs Actual Stock Price', fontsize=16, pad=20)
plt.xlabel('Theoretical Stock Price')
plt.ylabel('Actual Stock Price')

# Add text box (sample size and R^2)
info_text = f'Total Sample Size: {num_companies}\n$R^2$ Score: {r2_fig5:.4f}'
plt.text(0.02, 0.91, info_text, 
         transform=plt.gca().transAxes, 
         fontsize=12,
         bbox=dict(facecolor='white', alpha=0.8, edgecolor='black', boxstyle='round,pad=0.5'))
plt.grid(True, linestyle='--', alpha=0.5)

# === Create custom legend (combining original industry legend and regression line details) ===
# Get handles and labels generated by the original scatter plot
handles, labels = ax.get_legend_handles_labels()

# Add custom regression line and shaded area legend elements
custom_lines = [
    Line2D([0], [0], color='red', linestyle='--', lw=2),
    Patch(facecolor='red', alpha=0.2)
]
custom_labels = ['Regression Trend Line', '95% Confidence Interval']

# Extend the original legend list
handles.extend(custom_lines)
labels.extend(custom_labels)

# Redraw the combined legend
plt.legend(handles=handles, labels=labels, bbox_to_anchor=(1.01, 1), loc='upper left', title="Legend")

plt.tight_layout()
plt.savefig('fig5_theoretical_stock_price_vs_actual_stock_price.png', dpi=300, bbox_inches='tight')
plt.show()

#%% =======================   FIG 6: Model Error   ============================
# 1. Calculate Model Error
plot_data['model_error'] = plot_data['stock_price'] - plot_data['theoretical_price']

# 2. Retrieve all fiscal years (fy) and sort them
years = sorted(plot_data['fy'].unique())
num_years = len(years)
cols = 3
rows = math.ceil(num_years / cols)

# 3. Plot
fig, axes = plt.subplots(rows, cols, figsize=(20, 6 * rows), sharey=True)
axes = axes.flatten()

for i, year in enumerate(years):
    subset = plot_data[plot_data['fy'] == year].copy()
    subset = subset.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    if subset.empty:
        axes[i].axis('off')
        continue
    
    # === Calculate the R^2 score of the fiscal year of this subplot ===
    n_sub = len(subset)
    y_true_sub = subset['stock_price']
    y_pred_sub = subset['theoretical_price']
    ss_res_sub = np.sum((y_true_sub - y_pred_sub) ** 2)
    ss_tot_sub = np.sum((y_true_sub - np.mean(y_true_sub)) ** 2)
    r2_sub = 1 - (ss_res_sub / ss_tot_sub) if ss_tot_sub != 0 else float('nan')
    
    # Use 'seaborn scatterplot' to handle multi-color and shape
    sns.scatterplot(
        data=subset, 
        x='model_error', 
        y='stock_price', 
        hue='broad_industry', 
        style='broad_industry', 
        alpha=0.6, 
        s=50, 
        ax=axes[i]
    )
    
    # 1. Get current plot limits (xlim and ylim)
    xlim = axes[i].get_xlim()
    ylim = axes[i].get_ylim()
    
    # 2. Calculate the 80% position
    # Take the smaller of the X and Y axis upper limits to ensure labels stay within the plot
    pos = min(xlim[1], ylim[1]) * 0.8
    
    # 2. Add baseline
    axes[i].axhline(0, color='dimgrey', linewidth=1, alpha=0.5) # y = 0
    axes[i].axvline(0, color='dimgrey', linewidth=1, alpha=0.5) # x = 0
    axes[i].axline((0, 0), slope=1, color='red', linestyle='--', alpha=0.6, label='y=x') # y=x
    axes[i].text(pos*0.95, pos*1.05, 'y=x', color='red', fontsize=12, fontweight='bold', 
                 ha='right', va='bottom',  # Position text above the line
                 alpha=0.8)
    
    axes[i].set_title(f'Fiscal Year: {year}')
    axes[i].grid(True, linestyle='--', alpha=0.5)
    axes[i].set_xlabel('Model Error (Stock Price - Theoretical Price) (USD$)')
    axes[i].set_ylabel('Stock Price (USD$)')
    
    # === Add text box (sample size and R^2) in top left corner of subplot ===
    sub_info_text = f'Sample Size: {n_sub}\n$R^2$: {r2_sub:.4f}'
    axes[i].text(0.02, 0.89, sub_info_text, 
                 transform=axes[i].transAxes, 
                 fontsize=10,
                 bbox=dict(facecolor='white', alpha=0.8, edgecolor='black', boxstyle='round,pad=0.4'))
    
    # Close legend in subplots
    axes[i].legend([], [], frameon=False)

# remove unused subplots
for j in range(i + 1, len(axes)):
    axes[j].axis('off')

plt.suptitle('Fig 6: Model Error over Study Period', fontsize=20, y=0.96)
plt.tight_layout(rect=[0, 0.1, 1, 0.95], h_pad=1.0, w_pad=1.0)

# Get handles from the first valid axis
handles, labels = axes[0].get_legend_handles_labels()
new_labels = [f"industry= {l}" if l not in ["y=x"] else l for l in labels]
fig.legend(handles, new_labels, loc='upper center', 
           bbox_to_anchor=(0.5, 0.10), 
           title="Legend:", fontsize=10, ncol=6)
plt.savefig('fig6_model_error_over_study_period.png', dpi=300, bbox_inches='tight')
plt.show()

#%% ==========   FIG 7: 3D Heatmap of Model Factor and Stock Price   ==========
# Convert data into a 3D-compatible matrix format first
# Bin career_value and asset_value to ensure proper grid mapping
plot_data['cv_bin'] = pd.cut(plot_data['career_value'], bins=100)
plot_data['av_bin'] = pd.cut(plot_data['asset_value'], bins=100)

# Prepare Data (get 2 pivot tables ready)
heatmap_stock = plot_data.pivot_table(index='av_bin', columns='cv_bin', values='stock_price', aggfunc='mean').fillna(0)
heatmap_theo = plot_data.pivot_table(index='av_bin', columns='cv_bin', values='theoretical_price', aggfunc='mean').fillna(0)

# Prepare Meshgrid (Location of X-, Y- axes)
x_pos, y_pos = np.meshgrid(np.arange(heatmap_stock.shape[1]), np.arange(heatmap_stock.shape[0]))
x_pos, y_pos = x_pos.flatten(), y_pos.flatten()
z_pos = np.zeros_like(x_pos)
dx = dy = 0.8

# Create canvas. Setting: 1 row, 2 column.
fig = plt.figure(figsize=(20, 10))

# --- Left：Stock Price ---
ax1 = fig.add_subplot(121, projection='3d')
dz1 = heatmap_stock.values.flatten()
ax1.bar3d(x_pos, y_pos, z_pos, dx, dy, dz1, shade=True, color='skyblue')
ax1.set_title('Stock Price', fontsize=14, y=1.02)
ax1.set_xlabel('Career Value')
ax1.set_ylabel('Asset Value')
ax1.set_zlabel('Actual Stock Price')

# --- Right：Theoretical Price ---
ax2 = fig.add_subplot(122, projection='3d')
dz2 = heatmap_theo.values.flatten()
ax2.bar3d(x_pos, y_pos, z_pos, dx, dy, dz2, shade=True, color='salmon')
ax2.set_title('Theoretical Stock Price', fontsize=14, y=1.02)
ax2.set_xlabel('Career Value')
ax2.set_ylabel('Asset Value')
ax2.set_zlabel('Theoretical Stock Price')

plt.suptitle('Fig 7: 3D Heatmaps of Actual Stock Price and Theoretical Stock Price', fontsize=16)
plt.tight_layout()
fig.text(0.01, 0.01, "Remark: The career value, asset value and theoretical stock price are calculated according to the formulas listed in the book mentioned in readme.", fontsize=10, style='italic')
plt.savefig('fig7_3d_heatmaps_of_actual_stock_price_and_theoretical_stock_price.png', dpi=300, bbox_inches='tight')
plt.show()

# ==========================   Completed    ===================================
print('Done generate graphs')

#%%   ==========================   Analysis   ==========================
# Build folder for storing the models
os.makedirs('saved_models', exist_ok=True)
summary_results_list = []

global_top_20_tickers = clean_data.groupby('ticker')['market_cap'].mean().nlargest(20).index.tolist()
print(f"🌟 Global top 20 company list: {global_top_20_tickers}\n")

top_companies_to_plot = []
industries = sorted([ind for ind in clean_data['broad_industry'].unique() if ind != 'Other/Unclassified'])

for ind in industries:
    print(f"\n\n{'='*60}")
    print(f"🚀 Building predictive model - Industry: {ind}")
    print(f"{'='*60}")
    
    print("\n" + "="*60)
    print("🔍 Detailed analysis on missing/abnormal value")
    print("="*60)

    ind_data = clean_data[clean_data['broad_industry'] == ind].copy()
    total_rows = len(ind_data)
    inf_mask = np.isinf(ind_data.select_dtypes(include=[np.number]))
    neg_inf_mask = np.isneginf(ind_data.select_dtypes(include=[np.number]))
    nan_mask = ind_data.isna()

    # Calculate percentage
    inf_pct = (inf_mask.sum() / total_rows) * 100
    neg_inf_pct = (neg_inf_mask.sum() / total_rows) * 100
    nan_pct = (nan_mask.sum() / total_rows) * 100

    # Print out top 10 problematic columns
    combined_stats = pd.DataFrame({'Inf%': inf_pct, '-Inf%': neg_inf_pct, 'NaN%': nan_pct})
    print(combined_stats[combined_stats.sum(axis=1) > 0].sort_values(by='NaN%', ascending=False).head(10))

    # Conversion and removal
    ind_data = ind_data.replace([np.inf, -np.inf], np.nan)

    # Calculate missing ratio (%) in each column
    missing_ratios = ind_data.isnull().mean() * 100
    missing_summary = missing_ratios[missing_ratios > 0].sort_values(ascending=False)
    print("\n⚠️ Missing ratio of each factor (%):")
    for feat, ratio in missing_summary.items():
        print(f" - {feat}: {ratio:.2f}%")
    threshold = 10
    cols_to_drop = missing_ratios[missing_ratios > threshold].index.tolist()
    cols_to_drop = [c for c in cols_to_drop if c not in ['ticker', 'fy', 'stock_price', 'market_cap', 'broad_industry']]
    if cols_to_drop:
        print(f"\n🗑️ Automatically dropped factors with missing ratios exceeding {threshold}%, to prevent model data distortion:")
        print(cols_to_drop)
        ind_data = ind_data.drop(columns=cols_to_drop)

    # ----------------------------------------------------
    # A. Data-preprocessing and building feature pool
    # ----------------------------------------------------
    imputer = SimpleImputer(strategy='median') 
    numeric_cols = ind_data.select_dtypes(include=['float64', 'int64']).columns 
    ind_data[numeric_cols] = imputer.fit_transform(ind_data[numeric_cols]) 

    n_companies = ind_data['ticker'].nunique()
    print(f"✅ Industry: {ind} | No. of data rows: {len(ind_data)} | No. of companies: {n_companies}")

    current_feature_pool = [
        f for f in correlation_factor 
        if f in ind_data.columns 
        and f not in cols_to_drop 
        and f not in ['stock_price', 'stock_price_unadjusted']
    ]

    corr_series = ind_data[current_feature_pool + ['stock_price']].corr(numeric_only=True)['stock_price'].drop('stock_price', errors='ignore')
    corr_series = corr_series.dropna()
    
    if len(corr_series) == 0:
        print("⚠️ No effective factor. Skipped building model.")
        continue
    
    # data slicing to time
    train_data = ind_data[ind_data['fy'] <= 2023].copy()
    test_data = ind_data[ind_data['fy'] >= 2024].copy()
    
    if len(train_data) < 5 or len(test_data) < 2:
         print(f"⚠️ [{ind}] Too few data in training set/test set. Skipped building model.")
         continue

    # ----------------------------------------------------
    # B. Iterate through different numbers of features across the 6 models to optimize respective performance
    # ----------------------------------------------------
    factor_ratios = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    
    models_template = {
        "Linear Regression": LinearRegression(),
        "Ridge Regression": Ridge(alpha=1.0),
        "Decision Tree": DecisionTreeRegressor(random_state=42),
        "Random Forest": RandomForestRegressor(n_estimators=100, random_state=42),
        "SVR": SVR(kernel='rbf', C=100),
        "XGBoost": XGBRegressor(n_estimators=100, learning_rate=0.05, random_state=42)
    }

    model_optimization_results = {}

    for name, base_model in models_template.items():
        best_m_r2 = -float('inf')
        best_m_ratio = None
        best_m_features = None
        best_m_scaler = None
        best_m_trained_model = None
        best_m_preds = None
        
        # Iterate through 'factor_ratios' to optimise R^2 score in 'best_model'
        for ratio in factor_ratios:
            top_n = max(1, int(len(corr_series) * ratio))
            selected_features = corr_series.head(top_n).index.tolist()
            
            X_train = train_data[selected_features]
            y_train = train_data['stock_price']
            X_test = test_data[selected_features]
            y_test = test_data['stock_price']
            
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Re-instantiate model to ensure clean training
            if name == "Linear Regression":
                model = LinearRegression()
            elif name == "Ridge Regression":
                model = Ridge(alpha=1.0)
            elif name == "Decision Tree":
                model = DecisionTreeRegressor(random_state=42)
            elif name == "Random Forest":
                model = RandomForestRegressor(n_estimators=100, random_state=42)
            elif name == "SVR":
                model = SVR(kernel='rbf', C=100)
            elif name == "XGBoost":
                model = XGBRegressor(n_estimators=100, learning_rate=0.05, random_state=42)
                
            model.fit(X_train_scaled, y_train)
            pred = model.predict(X_test_scaled)
            r2 = r2_score(y_test, pred)
            
            if r2 > best_m_r2:
                best_m_r2 = r2
                best_m_ratio = ratio
                best_m_features = selected_features
                best_m_scaler = scaler
                best_m_trained_model = model
                best_m_preds = pred
                
        model_optimization_results[name] = {
            'best_r2': best_m_r2,
            'best_ratio': best_m_ratio,
            'features': best_m_features,
            'scaler': best_m_scaler,
            'model': best_m_trained_model,
            'predictions': best_m_preds
        }

    # Out of the best performances of the 6 models, select the best one to predict this broad_industry
    best_model_name = max(model_optimization_results, key=lambda k: model_optimization_results[k]['best_r2'])
    best_info = model_optimization_results[best_model_name]
    
    best_model = best_info['model']
    predictions = best_info['predictions']
    selected_features = best_info['features']
    scaler = best_info['scaler']
    optimal_ratio = best_info['best_ratio']
    
    results = {name: model_optimization_results[name]['best_r2'] for name in models_template}

    print(f"🏆 Best predictive model: {best_model_name} (R^2 = {results[best_model_name]:.4f}) [Used {len(selected_features)} factors]")
    
    if best_model_name == "Linear Regression":
        coefs = best_model.coef_
        intercept = best_model.intercept_
        eq_terms = [f"({coef:.3f} * {feat})" for coef, feat in zip(coefs, selected_features)]
        equation = f"Predicted Price = {intercept:.3f} + \n    " + " + \n    ".join(eq_terms)
        print(f"\n📐 [Linear Regression Equation]\n{equation}\n")

    # ----------------------------------------------------
    # C. Visualise results
    # ----------------------------------------------------
    
    # Fig A: Comparison of R^2 score (Showing each model's best performance and its optimal factor ratio)
    fig, ax = plt.subplots(figsize=(10, 5))
    bar_colors = ['skyblue', 'salmon', 'lightgreen', 'orange', 'plum', 'khaki']
    
    model_names = list(models_template.keys())
    r2_values = [results[m] for m in model_names]
    
    bars = ax.bar(model_names, r2_values, color=bar_colors[:len(model_names)])
    ax.set_ylabel('R^2 Score')
    ax.set_title(f'[{ind}] Fig A: Model Accuracy Comparison (Model-Specific Optimal Features)')
    ax.set_ylim(min(0, min(r2_values) * 1.15), max(1.0, max(r2_values) * 1.15)) 
    
    for i, bar in enumerate(bars):
        yval = bar.get_height()
        m_name = model_names[i]
        m_ratio_pct = int(model_optimization_results[m_name]['best_ratio'] * 100)
        m_n_feat = len(model_optimization_results[m_name]['features'])
        
        # label 'Top X% factors,' before R^2 score
        label_text = f"Top {m_ratio_pct}% factors ({m_n_feat}f),\n{yval:.4f}"
        
        offset = 0.02 if yval >= 0 else -0.09
        ax.text(bar.get_x() + bar.get_width()/2, yval + offset, label_text, 
                ha='center', va='bottom' if yval >= 0 else 'top', fontsize=8, fontweight='bold')
                
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(f'{ind}_figa_model_accuracy_comparison.png', dpi=300, bbox_inches='tight')
    plt.show()

    # Fig B: Parity Plot (prediction vs actual)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(y_test, predictions, alpha=0.6, color='royalblue', edgecolor='w')
    ax.plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], 'r--', lw=2, label='Perfect Prediction')
    
    ax.set_xlabel('Actual Stock Price (2024-2025)')
    ax.set_ylabel('Predicted Stock Price')
    ax.set_title(f'[{ind}] Fig B: Actual vs Predicted (Best: {best_model_name})')
    
    ax.legend(loc='upper left')
    
    info_text = f"Model: {best_model_name}\nOptimal Features: Top {int(optimal_ratio*100)}% ({len(selected_features)}f)\nNo. of companies: {n_companies}\n$R^2$ Score: {results[best_model_name]:.4f}"
    props = dict(boxstyle='round', facecolor='white', edgecolor='lightgray', alpha=0.8)
    ax.text(0.02, 0.85, info_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=props)
    
    ax.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(f'{ind}_figb_actual_vs_predicted.png', dpi=300, bbox_inches='tight')
    plt.show()

    # Fig C: Case Study (one random company)
    random_ticker = np.random.choice(test_data['ticker'].unique())
    ticker_data = ind_data[ind_data['ticker'] == random_ticker].sort_values('fy')
    
    if len(ticker_data) > 0:
        ticker_X = ticker_data[selected_features]
        ticker_X_scaled = scaler.transform(ticker_X)
        ticker_predictions = best_model.predict(ticker_X_scaled)
        
        plt.figure(figsize=(9, 5))
        plt.plot(ticker_data['fy'], ticker_data['stock_price'], marker='o', linestyle='-', color='black', label='Actual Price', linewidth=2)
        plt.plot(ticker_data['fy'], ticker_predictions, marker='x', linestyle='--', color='orange', label='Predicted Price', linewidth=2)
        
        plt.axvline(x=2023.5, color='gray', linestyle=':', alpha=0.8)
        plt.text(2023.5, ticker_data['stock_price'].max(), ' Train | Test ', ha='center', va='top', color='gray')
        
        plt.xticks(ticker_data['fy'].astype(int))
        
        plt.title(f'[{ind}] Fig C: Case Study - Ticker {random_ticker} Stock Price Over Time')
        plt.xlabel('Fiscal Year (fy)')
        plt.ylabel('Stock Price')
        ax_c = plt.gca()
        leg = ax_c.legend(loc='upper left')
        
        info_text = f"Model: {best_model_name}\nOptimal Features: Top {int(optimal_ratio*100)}% ({len(selected_features)}f)\nNo. of companies: {n_companies}\n$R^2$ Score: {results[best_model_name]:.4f}"
        props = dict(boxstyle='round', facecolor='white', edgecolor='lightgray', alpha=0.8)
        
        plt.draw()
        bbox = leg.get_window_extent()
        y_pos = ax_c.transAxes.inverted().transform((0, bbox.ymin))[1] - 0.02 
        x_pos = ax_c.transAxes.inverted().transform((bbox.xmin, 0))[0] + 0.005
        
        plt.text(x_pos, y_pos, info_text, transform=ax_c.transAxes, fontsize=9,
                 verticalalignment='top', bbox=props)
        
        plt.grid(True, alpha=0.3)
        plt.savefig(f'{ind}_figc_case_study_ticker_{random_ticker}_stock_price_over_time.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    # Collect Top market_cap company info. Draw after industry loop ends.
    matched_top_tickers = [t for t in ind_data['ticker'].unique() if t in global_top_20_tickers]
    for ticker in matched_top_tickers:
        top_companies_to_plot.append({
            'ticker': ticker,
            'ind': ind,
            'data': ind_data[ind_data['ticker'] == ticker].sort_values('fy'),
            'model': best_model,
            'modelname': best_model_name,
            'ncompany': n_companies,
            'r2score': results[best_model_name],
            'n_features': len(selected_features),
            'optimal_ratio': optimal_ratio,
            'scaler': scaler,
            'features': selected_features
        })
    
    # ----------------------------------------------------
    # E. Model Persistence and Summary Collection
    # ----------------------------------------------------
    model_artifact = {
        'industry': ind,
        'model_name': best_model_name,
        'model': best_model,
        'scaler': scaler,
        'features': selected_features,
        'r2_score': results[best_model_name]
    }
    
    # Save as file（eg, saved_models/Technology_model.pkl）
    safe_ind_name = ind.replace('/', '_').replace(' ', '_')
    joblib.dump(model_artifact, f'saved_models/{safe_ind_name}_model.pkl')
    
    # Collect summary data
    summary_results_list.append({
        'Industry': ind,
        'Best_Model': best_model_name,
        'Optimal_Feature_Ratio': f"Top {int(optimal_ratio*100)}%",
        'No_of_Features': len(selected_features),
        'No_of_Companies': n_companies,
        'R2_Score': results[best_model_name]
    })
    
# ==============================================================================
# Fig D: Case Study (Companies with largest market_cap)
# ==============================================================================
for item in top_companies_to_plot:
    ticker = item['ticker']
    ind = item['ind']
    ticker_data = item['data']
    model = item['model']
    modelname = item['modelname']
    ncompany = item['ncompany']
    r2score = item['r2score']
    n_features = item['n_features']
    optimal_ratio = item['optimal_ratio']
    scaler = item['scaler']
    features = item['features']
    
    if len(ticker_data) > 0:
        ticker_X = ticker_data[features]
        ticker_X_scaled = scaler.transform(ticker_X)
        ticker_predictions = model.predict(ticker_X_scaled)
        
        plt.figure(figsize=(9, 5))
        plt.plot(ticker_data['fy'], ticker_data['stock_price'], marker='o', label='Actual', color='black')
        plt.plot(ticker_data['fy'], ticker_predictions, marker='x', linestyle='--', label='Pred', color='orange')
        
        plt.axvline(x=2023.5, color='gray', linestyle=':', alpha=0.8)
        plt.text(2023.5, ticker_data['stock_price'].max(), ' Train | Test ', ha='center', va='top', color='gray')
        
        plt.title(f'[Top Market Cap] Fig D: Case Study - [{ind}] Ticker {ticker} Stock Price Over Time')
        plt.xlabel('Fiscal Year (fy)')
        plt.ylabel('Stock Price')
        ax_d = plt.gca()
        
        leg = ax_d.legend(loc='upper left')
        plt.draw() 
        
        bbox = leg.get_window_extent()
        y_pos = ax_d.transAxes.inverted().transform((0, bbox.ymin))[1] - 0.02 
        x_pos = ax_d.transAxes.inverted().transform((bbox.xmin, 0))[0] + 0.005
        
        info_text = f"Model: {modelname}\nOptimal Features: Top {int(optimal_ratio*100)}% ({n_features}f)\nNo. of companies: {ncompany}\n$R^2$ Score: {r2score:.4f}"
        props = dict(boxstyle='round', facecolor='white', edgecolor='lightgray', alpha=0.8)
        
        plt.text(x_pos, y_pos, info_text, transform=ax_d.transAxes, fontsize=9,
                 verticalalignment='top', bbox=props)
        plt.grid(True, alpha=0.3)
        plt.savefig(f'top_market_cap_figd_case_study_{ind}_ticker_{ticker}_stock_price_over_time.png', dpi=300, bbox_inches='tight')
        plt.show()

# ==============================================================================
# F. Export Overall Model Performance Summary
# ==============================================================================
summary_df = pd.DataFrame(summary_results_list)
summary_df.to_csv('industry_model_summary.csv', index=False, encoding='utf-8-sig')

print("\n" + "="*60)
print("📁 Summary results successfully exported to 'industry_model_summary.csv'")
print("💾 Industry models and scalers saved to 'saved_models/' folder")
print("="*60)

# ==========================    Completed    ===================================
print('Done analysis')




