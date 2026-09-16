import os
import datetime
import pandas as pd
import yfinance as yf
import requests
from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 設定路徑（如果在雲端有掛載 Persistent Disk，可將這裡指向該路徑）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

HISTORY_PATH = os.path.join(DATA_DIR, "signal_history.csv")
VIRTUAL_PORTFOLIO_PATH = os.path.join(DATA_DIR, "virtual_portfolio.csv")

@app.route("/")
def home():
    return "Taiwan Stock Bot with Tracker is running!", 200

@app.route("/run")
def run_picker():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return jsonify({"status": "error", "message": "Telegram Token not configured."}), 500

    try:
        list_file_path = "stock_list.txt"
        raw_stock_list = []
        if os.path.exists(list_file_path):
            with open(list_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    code = line.strip()
                    if code and code.isdigit():
                        raw_stock_list.append(code)
        
        if not raw_stock_list:
            raw_stock_list = ["2454", "3017", "2357"]

        scored_results = []
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        for code in raw_stock_list:
            symbol = f"{code}.TW"
            try:
                df = yf.download(symbol, period="60d", progress=False)
                if not df.empty and len(df) >= 20:
                    close_prices = df['Close']
                    val = close_prices.iloc[-1]
                    latest_close = float(val.iloc[0] if hasattr(val, 'iloc') else val)
                    
                    ma5 = close_prices.rolling(window=5).mean().iloc[-1]
                    ma20 = close_prices.rolling(window=20).mean().iloc[-1]
                    ma5_val = float(ma5.iloc[0] if hasattr(ma5, 'iloc') else ma5)
                    ma20_val = float(ma20.iloc[0] if hasattr(ma20, 'iloc') else ma20)
                    
                    score = 70  
                    if latest_close > ma5_val:
                        score += 15
                    if ma5_val > ma20_val:
                        score += 15
                        
                    # 判斷是否符合買進標準 (例如分數 >= 85)
                    signal_text = "符合買進標準" if score >= 85 else "區間觀望"

                    scored_results.append({
                        "股票代號": code,
                        "symbol": symbol,
                        "最新收盤價": latest_close,
                        "綜合評分": score,
                        "量化訊號": signal_text
                    })
            except Exception as e:
                print(f"處理 {symbol} 錯誤: {e}")

        df_results = pd.DataFrame(scored_results)
        if df_results.empty:
            return jsonify({"status": "success", "message": "無資料可分析"}), 200

        # 篩選符合買進標準的股票
        buy_signals = df_results[df_results["量化訊號"].str.contains("符合買進標準", na=False)].copy()

        # 1. 寫入歷史戰績庫
        if not buy_signals.empty:
            history_records = buy_signals.copy()
            history_records.insert(0, "進場日期", today_str)

            if os.path.exists(HISTORY_PATH):
                history_df = pd.read_csv(HISTORY_PATH, encoding="utf-8-sig")
                combined_history = pd.concat([history_df, history_records]).drop_duplicates(subset=["進場日期", "股票代號"], keep="last")
            else:
                combined_history = history_records
            combined_history.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

            # 2. 自動同步至虛擬風控艙
            virtual_entries = pd.DataFrame({
                "股票代號": buy_signals["股票代號"],
                "買進日期": today_str,
                "買進成本": buy_signals["最新收盤價"]
            })
            if os.path.exists(VIRTUAL_PORTFOLIO_PATH):
                portfolio_df = pd.read_csv(VIRTUAL_PORTFOLIO_PATH, encoding="utf-8-sig")
                existing_tickers = portfolio_df["股票代號"].astype(str).tolist()
                new_to_add = virtual_entries[~virtual_entries["股票代號"].astype(str).isin(existing_tickers)]
                if not new_to_add.empty:
                    combined_portfolio = pd.concat([portfolio_df, new_to_add], ignore_index=True)
                    combined_portfolio.to_csv(VIRTUAL_PORTFOLIO_PATH, index=False, encoding="utf-8-sig")
            else:
                virtual_entries.to_csv(VIRTUAL_PORTFOLIO_PATH, index=False, encoding="utf-8-sig")

        # 整理 Telegram 訊息
        msg_lines = ["📊 【台股自選股綜合評分與追蹤清單】\n"]
        for _, item in df_results.iterrows():
            msg_lines.append(
                f"🔹 代號: {item['symbol']}\n"
                f"   收盤價: {item['最新收盤價']:.2f} | 評分: ⭐️ {item['綜合評分']}分\n"
                f"   狀態: {item['量化訊號']}"
            )
        msg = "\n\n".join(msg_lines)

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

        return jsonify({"status": "success", "message": "分析完成，歷史與虛擬倉已同步。"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)