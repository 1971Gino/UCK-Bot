import os
import asyncio
import json
import requests
from datetime import datetime
import telebot
from groq import Groq
from dotenv import load_dotenv
from xrpl.asyncio.clients import AsyncWebsocketClient
from xrpl.models.requests import Subscribe, StreamParameter

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")
MIN_BUY_XRP    = float(os.getenv("MIN_BUY_XRP", 1.0))

if not all([TELEGRAM_TOKEN, GROQ_API_KEY, CHAT_ID]):
    print("Missing keys in .env! Fix TELEGRAM_TOKEN, GROQ_API_KEY, TELEGRAM_CHAT_ID")
    exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

GROQ_MODEL = "llama-3.3-70b-versatile"

ISSUER = "rsMH5RBCYohAHXqVK3ShaYrR2vAS5rmdNB"
CURRENCY = "UCK"
XRPL_WS = "wss://xrplcluster.com"
XPMARKET_URL = f"https://api.xpmarket.com/api/v1/tokens/{CURRENCY}+{ISSUER}"

def get_uck_price():
    try:
        r = requests.get(XPMARKET_URL, timeout=5)
        data = r.json()
        price = data.get('price')
        return float(price) if price is not None else None
    except:
        return None

@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    bot.reply_to(message, "Yo Gino & squad! 🚀 UCK Buy Tracker + Fast Groq AI\n\nReal-time UCK buys in channel • /price for UCK/XRP • Ask anything\nLet's pump! 🦈🦐🔥")

@bot.message_handler(commands=['price'])
def price_cmd(message):
    price = get_uck_price()
    if price:
        bot.reply_to(message, f"🚨 **UCK/XRP live** (XPMarket): **{price:.8f} XRP** per UCK\nhttps://xpmarket.com/token/UCK?issuer={ISSUER} 📈")
    else:
        bot.reply_to(message, "Can't fetch price — check XPMarket!")

@bot.message_handler(func=lambda m: True)
def chat(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are helpful, truthful, witty AI like Grok. Talk in NYC street style — direct, fun, no fluff. For UCK/XRP: say /price or check XPMarket."},
                {"role": "user", "content": message.text},
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        bot.reply_to(message, resp.choices[0].message.content.strip())
    except Exception as e:
        err = str(e)
        if "rate limit" in err.lower():
            bot.reply_to(message, "Groq limit hit 😅 Wait 30-60 sec!")
        else:
            bot.reply_to(message, f"Oops: {err[:200]}")

async def alerts():
    while True:
        try:
            async with AsyncWebsocketClient(XRPL_WS) as client:
                print("XRPL connected! Listening...")
                await client.send(Subscribe(streams=[StreamParameter.LEDGER]))
                async for msg in client:
                    data = msg
                    if data.get("type") == "transaction":
                        tx = data.get("transaction", {})
                        meta = data.get("meta", {})
                        affected = meta.get("AffectedNodes", [])
                        for node in affected:
                            final = node.get("FinalFields") or node.get("NewFields", {})
                            if final.get("Currency") == CURRENCY and final.get("Issuer") == ISSUER:
                                prev = float(node.get("PreviousFields", {}).get("Balance", {"value": "0"})["value"] or 0)
                                new = float(final.get("Balance", {"value": "0"})["value"] or 0)
                                received = new - prev
                                if received > 0:
                                    spent = 0
                                    if "Amount" in tx and isinstance(tx["Amount"], str):
                                        spent += int(tx["Amount"]) / 1_000_000
                                    spent += float(tx.get("Fee", 0)) / 1_000_000
                                    if spent >= MIN_BUY_XRP:
                                        buyer = tx.get("Account", "unknown")
                                        tx_hash = tx.get("hash", "unknown")
                                        now = datetime.now().strftime("%Y-%m-%d %H:%M EST")
                                        price = get_uck_price()
                                        price_line = f"Price: ~{price:.8f} XRP" if price else "Price: check XPMarket"
                                        alert = (
                                            f"🚨 **NEW BUY UCK** 🦈🦐🚀🔥🔥\n"
                                            f"({now})\n\n"
                                            f"💰 **Spent**: {spent:.2f} XRP\n"
                                            f"🪙 **Received**: {received:.8f} UCK\n"
                                            f"👤 **Buyer**: {buyer[:6]}...{buyer[-6:]}\n"
                                            f"🏦 **Issuer**: {ISSUER[:6]}...{ISSUER[-6:]}\n"
                                            f"{price_line}\n"
                                            f"🔗 **Tx**: https://xrpscan.com/tx/{tx_hash}\n"
                                            f"📊 **Chart**: https://xpmarket.com/token/UCK?issuer={ISSUER}\n"
                                            f"\nJoin the pump! 📈🦆"
                                        )
                                        bot.send_message(CHAT_ID, alert, parse_mode='Markdown', disable_web_page_preview=True)
                                        print(f"Alert sent: {spent:.2f} XRP → {received:.8f} UCK")
        except Exception as e:
            print(f"XRPL error: {e}. Reconnect in 10s...")
            await asyncio.sleep(10)

async def main():
    asyncio.create_task(alerts())
    print("Best bot running... 🚀 (chat + alerts + /price)")
    bot.infinity_polling()

if __name__ == "__main__":
    asyncio.run(main())