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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

HISTORY_PATH = os.path.join(DATA_DIR, "signal_history.csv")
VIRTUAL_PORTFOLIO_PATH = os.path.join(DATA_DIR, "virtual_portfolio.csv")

@app.route("/")
def home():
    return "Taiwan Stock Bot with Clean Portfolio Tracking is running!", 200

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

        buy_signals = df_results[df_results["量化訊號"].str.contains("符合買進標準", na=False)].copy()

        # 1. 寫入歷史戰績庫 & 自動加入追蹤艙
        new_added_tickers = []
        if not buy_signals.empty:
            history_records = buy_signals.copy()
            history_records.insert(0, "進場日期", today_str)

            if os.path.exists(HISTORY_PATH):
                history_df = pd.read_csv(HISTORY_PATH, encoding="utf-8-sig")
                combined_history = pd.concat([history_df, history_records]).drop_duplicates(subset=["進場日期", "股票代號"], keep="last")
            else:
                combined_history = history_records
            combined_history.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

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
                    new_added_tickers = new_to_add["股票代號"].astype(str).tolist()
                    combined_portfolio = pd.concat([portfolio_df, new_to_add], ignore_index=True)
                    combined_portfolio.to_csv(VIRTUAL_PORTFOLIO_PATH, index=False, encoding="utf-8-sig")
            else:
                new_added_tickers = virtual_entries["股票代號"].astype(str).tolist()
                virtual_entries.to_csv(VIRTUAL_PORTFOLIO_PATH, index=False, encoding="utf-8-sig")

        # 2. 組合 Telegram 訊息
        msg_lines = ["📊 【台股自選股綜合評分與追蹤清單】\n"]
        for _, item in df_results.iterrows():
            is_new = " 🆕【新加入追蹤】" if str(item['股票代號']) in new_added_tickers else ""
            msg_lines.append(
                f"🔹 代號: {item['symbol']}{is_new}\n"
                f"   收盤價: {item['最新收盤價']:.2f} | 評分: ⭐️ {item['綜合評分']}分\n"
                f"   狀態: {item['量化訊號']}"
            )
        
        # 3. 計算即時績效與整體損益
        if os.path.exists(VIRTUAL_PORTFOLIO_PATH):
            portfolio_df = pd.read_csv(VIRTUAL_PORTFOLIO_PATH, encoding="utf-8-sig")
            if not portfolio_df.empty:
                portfolio_lines = ["\n-----------------------------------"]
                portfolio_lines.append("📈 【投資組合整體風控艙表現】")
                
                total_cost = 0.0
                total_market_value = 0.0
                item_count = 0
                win_count = 0

                for _, row in portfolio_df.iterrows():
                    code = str(row["股票代號"])
                    buy_date = row["買進日期"]
                    buy_cost = float(row["買進成本"])
                    
                    try:
                        temp_df = yf.download(f"{code}.TW", period="5d", progress=False)
                        if not temp_df.empty:
                            latest_val = temp_df['Close'].iloc[-1]
                            current_price = float(latest_val.iloc[0] if hasattr(latest_val, 'iloc') else latest_val)
                            
                            roi = ((current_price - buy_cost) / buy_cost) * 100
                            sign = "+" if roi >= 0 else ""
                            
                            total_cost += buy_cost * 1000
                            total_market_value += current_price * 1000
                            item_count += 1
                            if roi > 0:
                                win_count += 1
                            
                            portfolio_lines.append(
                                f"▪️ {code}.TW | 買:{buy_date} ({buy_cost:.1f}) ➡️ 現:{current_price:.1f}\n"
                                f"   損益: {sign}{roi:.2f}%"
                            )
                    except Exception as e:
                        print(f"計算追蹤標的 {code} 損益失敗: {e}")

                if total_cost > 0:
                    total_pnl = total_market_value - total_cost
                    total_roi = (total_pnl / total_cost) * 100
                    total_sign = "+" if total_pnl >= 0 else ""
                    win_rate = (win_count / item_count) * 100 if item_count > 0 else 0.0
                    
                    summary_header = (
                        f"🌐 ［整體總結］：追蹤中，共 {item_count} 檔 | 勝率：{win_rate:.1f}% ({win_count}/{item_count})\n"
                        f"📊 ［組合平均報酬率］：{total_sign}{total_roi:.2f}%\n"
                        f"💰 ［總估計損益金額］：{total_sign}{total_pnl:,.1f} 元\n"
                        f"-----------------------------------"
                    )
                    portfolio_lines.insert(1, summary_header)

                msg_lines.extend(portfolio_lines)

        full_msg = "\n".join(msg_lines)

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": full_msg})

        return jsonify({"status": "success", "message": "分析完成，整體損益已同步更新。"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)