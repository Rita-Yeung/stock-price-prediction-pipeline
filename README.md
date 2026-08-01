# Stock Price Prediction Pipeline (股票價格預測與特徵優化管道)

An end-to-end machine learning pipeline built with Python for cross-industry stock price prediction using fundamental financial data.  
一個使用 Python 建立的端到端機器學習管道，利用基本面財務資料進行跨行業的股票價格預測。

---

## 📌 Project Overview (專案概述)

This project implements a complete, structured data science pipeline designed to process fundamental financial data from the SEC (U.S. Securities and Exchange Commission) EDGAR system (Electronic Data Gathering, Analysis, and Retrieval system), train and evaluate multiple machine learning models, and generate analytical insights and visualizations for stock market trends.

This project is inspired by the published book *How to Find "10-Bagger" Stocks from a 3-Minute Rapid Reading of Financial Statements, Taught by a Salaryman Investor Who Built 360 Million Yen in Assets* (ISBN: 9786267321430). Since the SEC provides a vast public database for company fundamental information, this Python pipeline was built to verify whether the theoretical stock price formulas presented in the book can effectively predict actual stock prices.

本專案實作了一個完整且結構化的資料科學管道，專門用於處理來自美國證券交易委員會 (SEC) EDGAR 系統（電子數據收集、分析與檢索系統）的基本面財務資料、訓練與評估多個機器學習模型，並為股市趨勢產生分析見解與視覺化圖表。

本專案靈感源自暢銷書《3分鐘看懂財務報表找出潛力飆股：上班族投資人3.6億日圓資產滾出術》（ISBN：9786267321430）。由於 SEC 提供龐大的公開資料庫供大眾存取公司基本面資訊，因此建構此 Python 管道以驗證書中所述之理論股價公式是否能有效預測實際股價。

---

### 🔍 Scope & Data Selection Rationale (資料範圍與選定邏輯)
To ensure data integrity, the pipeline operates under the following explicit data boundaries:
* **Annual vs. Quarterly Data:** The pipeline focuses exclusively on **annual financial reports**. Quarterly data was excluded due to widespread missing values and inconsistent reporting formats across companies. Annual statements provide a sufficiently complete and standardized dataset for robust fundamental analysis.
* **Time Horizon (2019 Onwards):** Data collection is scoped to **2019 and later**. An investigation during development revealed that many critical financial metrics and structured reporting tags were either not legally mandated or sparsely populated on EDGAR prior to this period. Limiting the scope to 2019+ ensures high data reliability and a sufficient sample size to complete the study.
* **Fundamental Valuation Focus:** Despite the title "Stock Price Prediction Pipeline," this project evaluates long-term **fundamental financial valuation** rather than short-term technical price movements or daily trading volatility.

為確保資料品質，本管道採取了以下的資料範圍設定：
* **年度資料 vs. 季度資料：** 本專案專注於**年度財務報表（Annual Data）**。由於季度資料常有大量缺失值及申報不一致的情況，年度資料相對完整且標準化，足以支撐整體基本面分析。
* **時間範圍（2019 年起）：** 資料收集範圍設定在 **2019 年及以後**。在開發過程中發現，2019 年之前的許多關鍵財務資訊在 SEC EDGAR 系統中並未全面強制申報或結構化，早期資料缺失嚴重。設定此時間門檻可確保數據品質與足夠的樣本量。
* **基本面價值導向：** 儘管專案名稱為「Stock Price Prediction Pipeline」，其本質是利用**基本面財務數據**進行公司價值的評估與模型預測，而非短期的每日股價走勢或高頻技術分析預測。

---

## 🗂️ Repository Structure (倉庫結構)

- **ETL script.py**: 1st step - Extracts, transforms, and loads financial data from EDGAR and yfinance.
- **Recovery Script.py**: 2nd step - Handles and recovers failed cases/errors from the PostgreSQL database log.
- **Cleanup Script.py**: 3rd step - Cleans raw data, handles missing or infinite values, recovers critical metrics (shares and EPS), and segments datasets.
- **Analysis and Visualisation Script.py**: 4th (final) step - Generates evaluation charts, runs 6 machine learning models to select the optimum model, and predicts test data across all industry groups.
- **analysis_and_visualisation_output/**: Contains generated output files, including trained model artifacts (`.pkl`), summarized performance data (`.csv`), and evaluation charts/graphs (包含產出的模型檔案 `.pkl`、總結效能資料 `.csv` 以及評估圖表).
- **.env.example**: Template file for environment variable configurations (環境變數設定範本檔).
- **LICENSE.txt**: Project licensing information (專案授權條款).

---

## ⚙️ Script Details: Inputs & Outputs (腳本詳細說明：輸入與輸出)

### 1. `ETL script.py`
- **(i)** Extracts company financial data from EDGAR using REST APIs and stock price history using the `yfinance` library.
- **(ii)** Transforms raw data into tidy, ready-to-use data.
- **(iii)** Loads data into PostgreSQL and calculates financial parameters, ratios, and theoretical prices (formula based on personal understanding of the reference book).
- **Input (輸入)**: Raw financial data sources / REST APIs.
- **Output (輸出)**:
  - **(i)** Database tables in PostgreSQL (`us_stock`): `annual_financials_full`, `annual_financials_full_log`.
  - **(ii)** Backup/log files stored on the desktop: `{database_table_name}_{now}.csv`, `run_log_df_{time_of_run_end}.csv`, `console_output_{time_of_run_start}.txt`.

### 2. `Recovery Script.py`
- An enhanced script targeted at fixing specific errors (`line 1 column 1 (char 0)`, `cannot access local variable 'used_tag' where it is not associated with a value`, `'NoneType' object has no attribute 'empty'`, `division by zero`, `cannot reindex on an axis with duplicate labels`) listed in the database table `annual_financials_full_log` to recover more data into the database.
- **Input (輸入)**: Database tables after running the ETL script (`annual_financials_full`, `annual_financials_full_log`).
- **Output (輸出)**: `annual_financials_full` with recovered data added, `annual_financials_full_log` updated with recovery records, and updated backup/log files.

### 3. `Cleanup Script.py`
- Cleans raw data, handles missing or infinite values, recovers important information (number of shares and EPS), and segments datasets.
- **Input (輸入)**: Database tables after running the Recovery script (`annual_financials_full`, `annual_financials_full_log`).
- **Output (輸出)**: Database tables (`damaged_data` containing datasets missing `net_income`, `company_less_data` storing datasets without cost, expense_general/admin, current assets, current liabilities; `annual_financials_clean` storing thoroughly cleaned and structured datasets; `annual_financials_full_log` updated with cleanup records), and backup/log files.

### 4. `Analysis and Visualisation Script.py`
- Generates presentation-format graphs based on clean data. Runs 6 models to select the optimum model for predicting test data across all industry groups using the optimum number of features.
- **Input (輸入)**: Database table (`clean_data`).
- **Output (輸出)**: Trained model artifacts (`.pkl`), summarized performance data (`.csv`), and evaluation charts/graphs (包含產出的模型檔案 `.pkl`、總結效能資料 `.csv` 以及評估圖表).

---

## 📊 Main Findings & Results (主要發現與分析結果)

The pipeline successfully processes data and generates predictive models as well as visual insights. Below are some highlight graphs showcasing key findings:

本管道成功處理了資料並產出了預測模型與視覺化見解。以下展示部分突顯主要發現的核心圖表：

<img width="2982" height="2370" alt="fig1a_overall_correlation_with_stock_price" src="https://github.com/user-attachments/assets/7adbbf06-d9fb-40c0-97f6-f9a8fea195c5" />
<img width="6587" height="4915" alt="fig1b_factor_correlation_with_stock_price_by_broad_industry" src="https://github.com/user-attachments/assets/65ca1cb1-d8b2-4299-8715-75e2f6043deb" />
<img width="5969" height="5310" alt="fig2_relationship_of_financial_ratios_to_stock_price_in_each_broad_industry_over_time" src="https://github.com/user-attachments/assets/cf70a2ac-8ca9-49de-85c3-30ed2ff2389c" />


- **Figs 0–4: Data Correlation to Stock Price**
  - For Figs 1a and 1b, using logarithmic transformation can effectively elevate correlation coefficient values with stock prices to a more significant level.
  - In Fig 1b, factor correlation distributions among different industry groups vary significantly. Therefore, training predictive models on each individual group maximizes model predictive accuracy.
  - In Fig 2, green dotted lines indicate financial ratios that theoretically benefit a company when increased, while red dotted lines indicate the reverse. The effects of changes in financial ratios are not easily observed directly, showing both beneficial and adverse effects across industry groups. Consequently, the consequences of financial ratio changes cannot be easily interpreted as a direct one-size-fits-all rule.

<img width="5970" height="4925" alt="fig6_model_error_over_study_period" src="https://github.com/user-attachments/assets/21be1f1f-9898-4352-bad2-793299c3951c" />


- **Figs 5–7: Stock Price Prediction via Reference Book Formula**
  - The accuracy level of theoretical stock prices using the reference book formula is relatively low, which may stem from structural differences between the Japanese and U.S. stock markets.

<img width="2970" height="1472" alt="Retail Trade_figa_model_accuracy_comparison" src="https://github.com/user-attachments/assets/8609c7ce-3e60-4d54-b2ea-0c6131c3b218" />
<img width="1883" height="1407" alt="Retail Trade_figb_actual_vs_predicted" src="https://github.com/user-attachments/assets/f1df2691-4df9-49f2-aecd-6f0a9b3d98e3" />
<img width="2321" height="1407" alt="Retail Trade_figc_case_study_ticker_NSIT_stock_price_over_time" src="https://github.com/user-attachments/assets/57659ea2-19c3-4877-9f33-fdf964acad2c" />
<img width="2969" height="1472" alt="Manufacturing_figa_model_accuracy_comparison" src="https://github.com/user-attachments/assets/bf343fbb-abfc-4dda-9a3a-67f1d670ab6e" />
<img width="1937" height="1407" alt="Manufacturing_figb_actual_vs_predicted" src="https://github.com/user-attachments/assets/d81d7d29-e220-4a06-aed8-47e78d1fc8d2" />
<img width="2321" height="1407" alt="Manufacturing_figc_case_study_ticker_DCO_stock_price_over_time" src="https://github.com/user-attachments/assets/860be7ff-3100-4639-b97c-efd4571d7708" />


- **Industry Group Analysis (Figs a–c) and Top Market Cap Companies (Fig d)**
  - Model accuracy, parity plots, and case studies (Figs a–d) show that some industry groups (e.g., Wholesale Trade, Retail Trade) achieve high accuracy in predicting test data, whereas others (e.g., Manufacturing, Finance, Insurance, and Real Estate) exhibit lower accuracy.
  - The lower accuracy in high-volatility industries is probably because stock prices in these sectors are constrained by factors outside pure fundamentals (e.g., raw material quotes, central bank interest rate policies, geopolitical news). The model represents pure "financial statement fundamental value"; the gap between actual stock prices and predicted values can serve as an indicator to measure market sentiment, panic, or external disturbances.

- **Other Result Files (其他結果檔案)**: All trained models (saved as `.pkl` files), detailed aggregated metrics (`.csv` files), and complete evaluation graphs are stored in the `analysis_and_visualisation_output/` directory.

---

## 🚀 Getting Started (快速開始)

Follow these steps to set up and run the pipeline locally:

請依照以下步驟在本地端設定並執行此管道：

### 1. Prerequisites (先決條件)
- Python 3.9+
- PostgreSQL installed and running locally on port 5432

### 2. Clone the Repository (複製倉庫)
```bash
git clone https://github.com/Rita-Yeung/stock-price-prediction-pipeline.git
cd stock-price-prediction-pipeline
```

### 3. Install Dependencies (安裝依賴套件)
Install the required Python packages using pip:
```bash
pip install requests pandas yfinance sqlalchemy psycopg2-binary python-dotenv
```

### 4. Configure Environment (設定環境變數)
Create a PostgreSQL database named `us_stock`:
```sql
CREATE DATABASE us_stock;
```

Copy `.env.example` to `.env` and configure your database password and email for SEC EDGAR API headers:
```env
DB_PASSWORD=your_postgres_password
```
*(Note: Remember to update your email address in the scripts' headers dictionary for SEC EDGAR API compliance.)*

### 5. Run the Pipeline (執行管道)
Execute the scripts sequentially according to your workflow:
```bash
python "ETL script.py"
python "Recovery Script.py"
python "Cleanup Script.py"
python "Analysis and Visualisation Script.py"
```

---

## 📄 License (授權條款)

This project is licensed under the terms specified in the LICENSE.txt file.

本專案採用 LICENSE.txt 檔案中所指定的條款授權。
