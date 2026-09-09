import os
import time
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify
from telegram import Bot
from dotenv import load_dotenv

# 載入環境變數 (本地開發用，Render 上會讀取系統環境變數)
load_dotenv()

app = Flask(__name__)

# 讀取 Telegram 設定
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

@app.route("/")
def home():
    return "Taiwan Stock Daily Picker Bot is running!", 200

# 專門用來每 5 分鐘「保持清醒」的輕量路由（不會發送任何 Telegram 通知）
@app.route("/ping")
def ping():
    return "OK", 200

@app.route("/run")
def run_picker():
    if not bot or not TELEGRAM_CHAT_ID:
        return jsonify({"status": "error", "message": "Telegram Bot Token or Chat ID not configured."}), 500

    try:
        # ==========================================
        # 這裡放入你的選股邏輯與清單
        # ==========================================
        stock_list = ["2330.TW", "2317.TW", "2454.TW", "2308.TW"]
        
        selected_results = []
        
        for symbol in stock_list:
            try:
                # 抓取近期資料進行簡單分析或篩選
                df = yf.download(symbol, period="5d", progress=False)
                if not df.empty:
                    latest_close = float(df['Close'].iloc[-1])
                    selected_results.append(f"股票 {symbol} | 最新收盤價: {latest_close:.2f}")
            except Exception as e:
                print(f"處理 {symbol} 時發生錯誤: {e}")

        # 組裝發送給 Telegram 的訊息內容
        if selected_results:
            msg = "📊 【今日台股選股清單】\n\n" + "\n".join(selected_results)
        else:
            msg = "📊 【今日台股選股清單】\n\n今日無符合條件的股票。"

        # 推送到 Telegram
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

        return jsonify({"status": "success", "message": "Picker executed and notification sent."}), 200

    except Exception as e:
        error_msg = f"選股執行過程發生錯誤: {str(e)}"
        print(error_msg)
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=error_msg)
        except:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)