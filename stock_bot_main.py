import os
import time
import pandas as pd
import yfinance as yf
import requests
from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

@app.route("/")
def home():
    return "Taiwan Stock Analyzer & Scoring Bot is running!", 200

@app.route("/ping")
def ping():
    return "OK", 200

@app.route("/run")
def run_picker():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return jsonify({"status": "error", "message": "Telegram Bot Token or Chat ID not configured in environment variables."}), 500

    try:
        # 示範你的股票清單與分析評分邏輯
        stock_list = [
            {"symbol": "2330.TW", "name": "台積電"},
            {"symbol": "2317.TW", "name": "鴻海"},
            {"symbol": "2454.TW", "name": "聯發科"},
            {"symbol": "2308.TW", "name": "台達電"}
        ]
        
        scored_results = []
        
        for stock in stock_list:
            symbol = stock["symbol"]
            name = stock["name"]
            try:
                df = yf.download(symbol, period="30d", progress=False)
                if not df.empty:
                    # 示範計算近期技術指標與評分（例如：價格乖離、短線趨勢評分）
                    close_prices = df['Close']
                    val = close_prices.iloc[-1]
                    latest_close = float(val.iloc[0] if hasattr(val, 'iloc') else val)
                    
                    ma5 = close_prices.rolling(window=5).mean().iloc[-1]
                    ma20 = close_prices.rolling(window=20).mean().iloc[-1]
                    ma5_val = float(ma5.iloc[0] if hasattr(ma5, 'iloc') else ma5)
                    ma20_val = float(ma20.iloc[0] if hasattr(ma20, 'iloc') else ma20)
                    
                    # 簡單的評分規則示範（可依你的策略調整）
                    score = 70  
                    if latest_close > ma5_val:
                        score += 15
                    if ma5_val > ma20_val:
                        score += 15
                        
                    scored_results.append({
                        "name": name,
                        "symbol": symbol,
                        "price": latest_close,
                        "score": score
                    })
            except Exception as e:
                print(f"處理 {symbol} 時發生錯誤: {e}")

        # 依照評分由高到低排序
        scored_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)

        if scored_results:
            msg_lines = ["📊 【台股深度分析與綜合評分】\n"]
            for item in scored_results:
                msg_lines.append(
                    f"🔹 {item['name']} ({item['symbol']})\n"
                    f"   收盤價: {item['price']:.2f} | 綜合評分: ⭐️ {item['score']} 分"
                )
            msg = "\n\n".join(msg_lines)
        else:
            msg = "📊 【台股深度分析與綜合評分】\n\n今日無符合條件的股票。"

        telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(telegram_api_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
        
        if resp.status_code != 200:
            return jsonify({"status": "error", "message": resp.text}), 500

        return jsonify({"status": "success", "message": "Analysis and scoring executed successfully."}), 200

    except Exception as e:
        error_msg = f"分析執行過程發生錯誤: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)