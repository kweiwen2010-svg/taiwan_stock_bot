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
# 直接將正確的 Chat ID 寫死，徹底解決抓不到對話或環境變數讀取失敗的問題
TELEGRAM_CHAT_ID = "8791940051"

@app.route("/")
def home():
    return "Taiwan Stock Daily Picker Bot is running!", 200

@app.route("/ping")
def ping():
    return "OK", 200

@app.route("/run")
def run_picker():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"status": "error", "message": "Telegram Bot Token not configured."}), 500

    try:
        stock_list = ["2330.TW", "2317.TW", "2454.TW", "2308.TW"]
        selected_results = []
        
        for symbol in stock_list:
            try:
                df = yf.download(symbol, period="5d", progress=False)
                if not df.empty:
                    val = df['Close'].iloc[-1]
                    latest_close = float(val.iloc[0] if hasattr(val, 'iloc') else val)
                    selected_results.append(f"股票 {symbol} | 最新收盤價: {latest_close:.2f}")
            except Exception as e:
                print(f"處理 {symbol} 時發生錯誤: {e}")

        if selected_results:
            msg = "📊 【今日台股選股清單】\n\n" + "\n".join(selected_results)
        else:
            msg = "📊 【今日台股選股清單】\n\n今日無符合條件的股票。"

        # 使用 requests 直接發送 Telegram 訊息給指定的 Chat ID
        telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(telegram_api_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
        
        if resp.status_code != 200:
            return jsonify({"status": "error", "message": resp.text}), 500

        return jsonify({"status": "success", "message": "Picker executed and notification sent successfully."}), 200

    except Exception as e:
        error_msg = f"選股執行過程發生錯誤: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)