import os
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import pandas as pd
import yfinance as yf
from telegram import Bot
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import asyncio

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("STOCK_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
TAIPEI_TZ = timezone(timedelta(hours=8))

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def fetch_real_market_data(stock_id):
    """Sarah 3.2 Pro 核心數據抓取 (還原股價)"""
    try:
        ticker = yf.Ticker(f"{stock_id}.TW")
        df = ticker.history(period="1y", auto_adjust=True)
        if df.empty or len(df) < 60:
            return None, None
        df = df.dropna(subset=['Close', 'Volume'])
        
        roe_val = 0.0
        try:
            info = ticker.info
            if info and 'returnOnEquity' in info and info['returnOnEquity'] is not None:
                roe_val = float(info['returnOnEquity']) * 100
        except:
            pass
        return df, roe_val
    except Exception as e:
        return None, None

def run_stock_analysis():
    """執行完整選股並回傳格式化字串與代號"""
    list_path = 'list.txt'
    if not os.path.exists(list_path):
        return "❌ 找不到 list.txt 清單檔案！", ""
        
    with open(list_path, 'r', encoding='utf-8') as f:
        stock_list = [line.strip() for line in f.readlines() if line.strip()]

    today_str = datetime.now(TAIPEI_TZ).strftime('%Y-%m-%d')
    report_lines = [f"📊 **【台股每日選股機器人】** ({today_str})\n"]
    selected_codes = []

    for stock_id in stock_list:
        df_k, roe_val = fetch_real_market_data(stock_id)
        if df_k is None:
            continue
            
        # ROE Gate 攔截
        if 0 < roe_val < 12.0:
            continue
            
        # 技術指標與計分
        df_k['5_MA'] = df_k['Close'].rolling(window=5).mean()
        df_k['20_MA'] = df_k['Close'].rolling(window=20).mean()
        df_k['60_MA'] = df_k['Close'].rolling(window=60).mean()
        
        latest_close = float(df_k['Close'].iloc[-1])
        current_5ma = float(df_k['5_MA'].iloc[-1])
        current_20ma = float(df_k['20_MA'].iloc[-1])
        current_60ma = float(df_k['60_MA'].iloc[-1])
        
        high_250 = float(df_k['Close'].max())
        low_250 = float(df_k['Close'].min())
        position_pct = ((latest_close - low_250) / (high_250 - low_250)) * 100 if (high_250 - low_250) != 0 else 50
        
        ma_score = 15 if (latest_close >= current_5ma >= current_20ma >= current_60ma) else (10 if latest_close >= current_5ma else 3)
        ma_desc = "強勢多頭排列" if ma_score == 15 else ("站穩 5MA" if ma_score == 10 else "破線弱勢")
        
        position_score = 25 if position_pct < 40.0 else (25 if (position_pct > 80.0 and latest_close >= current_5ma) else (0 if position_pct > 80.0 else 20))
        position_desc = "🛡️ 低檔安全區" if position_pct < 40.0 else ("🚀 強勢創新高" if position_score == 25 else "正常位階")
        
        total_score = (20 if roe_val >= 12.0 else 10) + ma_score + position_score + 10
        
        if total_score >= 62:
            rating = "★★★★★ (法人多頭強勢股)"
        elif 52 <= total_score < 62:
            rating = "★★★★☆ (多頭趨勢觀察)"
        else:
            continue
            
        report_lines.append(f"• **{stock_id}** | 總分: {total_score} | {rating}\n  - {ma_desc} + {position_desc} | ROE: {roe_val:.2f}%\n")
        selected_codes.append(stock_id)

    code_str = ", ".join(selected_codes) if selected_codes else "今日無符合條件股票"
    report_lines.append(f"\n📋 **一鍵複製代號**：\n`{code_str}`")
    return "\n".join(report_lines), code_str

class StockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/run":
            report_text, _ = run_stock_analysis()
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            asyncio.run(bot.send_message(chat_id=ALLOWED_USER_ID, text=report_text, parse_mode="Markdown"))
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Stock analysis triggered and sent!")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Stock Bot is running independently!")
    def log_message(self, format, *args):
        return

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), StockHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("台股每日選股機器人伺服器已啟動...")
    import time
    while True:
        time.sleep(3600)