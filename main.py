#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🔥 Super‑fast Twilio ⇆ Telegram bot (Bengali)
✅ Threaded API calls, Termux Ready, Spoofed HTTP
✅ Fast OTP Auto-fetching + Secure + Bengali
"""

import re, random, threading, time
from datetime import datetime, timedelta
import requests
import telebot
from telebot import types
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient

# ───── Spoofed Twilio Client ─────
class SpoofedHttpClient(TwilioHttpClient):
    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_2 like Mac OS X)",
                "Mozilla/5.0 (Linux; Android 11)"
            ])
        })

BOT_TOKEN = "7630288391:AAFNCjLfeihTwIjd6aFghMhI92mzvB0HoMY"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
GROUP_ID = -1002762500349
user_session: dict[int, dict] = {}

CANADA_CODES = [
    "204", "236", "249", "250", "289", "306", "343", "365", "387", "403", "416", "418",
    "431", "437", "438", "450", "506", "514", "519", "548", "579", "581", "587", "604",
    "613", "639", "647", "672", "705", "709", "742", "778", "780", "782", "807", "819",
    "825", "867", "873", "902", "905"
]

def run_async(fn):
    def wrap(*a, **k): threading.Thread(target=fn, args=a, kwargs=k, daemon=True).start()
    return wrap

def logged(uid): return uid in user_session and "twilio_client" in user_session[uid]

def extract_otp(text):
    m = re.search(r"\b(\d{3}-\d{3}|\d{6})\b", text)
    return m.group(1) if m else "N/A"

def forward_to_group(html):
    try: bot.send_message(GROUP_ID, html)
    except Exception as e: print("Group forward error:", e)

def _stop_sms_listener(sess):
    ev = sess.get("sms_stop_evt")
    if ev: ev.set()
    for k in ("sms_thread","sms_stop_evt","last_msg_sid"): sess.pop(k, None)

def _start_sms_listener(uid, chat_id):
    sess = user_session[uid]
    _stop_sms_listener(sess)
    stop_evt = threading.Event()
    sess["sms_stop_evt"] = stop_evt
    sess["last_msg_sid"] = None

    def poll():
        client = sess["twilio_client"]
        num = sess["purchased_number"]
        while not stop_evt.is_set():
            try:
                msgs = client.messages.list(to=num, limit=1)
                if msgs and sess.get("last_msg_sid") != msgs[0].sid:
                    sess["last_msg_sid"] = msgs[0].sid
                    _send_formatted_sms(chat_id, msgs[0], num)
            except Exception as e:
                print("SMS Poll Error:", e)
            stop_evt.wait(10 + random.uniform(0.5, 2.0))

    threading.Thread(target=poll, daemon=True).start()

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m,
        "🧾 Twilio SID ও Token এইভাবে পাঠান:\nACxxxxxxxx tokenxxxxxxxx\n\n"
        "🔐 উদাহরণ:\nAC123… token123…"
    )

@bot.message_handler(commands=["login"])
def login_cmd(m):
    bot.reply_to(m, "🔐 Twilio SID এবং Token পাঠান:\nACxxxx tokenxxxx")

@bot.message_handler(commands=["logout"])
@run_async
def logout(m):
    uid = m.from_user.id
    if not logged(uid):
        bot.reply_to(m, "❗️ আপনি লগইন করেননি।")
        return
    sess = user_session[uid]
    client = sess["twilio_client"]
    old = sess.get("purchased_number")
    _stop_sms_listener(sess)
    try:
        if old:
            for n in client.incoming_phone_numbers.list():
                if n.phone_number == old:
                    client.incoming_phone_numbers(n.sid).delete()
                    break
    except: pass
    user_session.pop(uid, None)
    bot.send_message(m.chat.id, "✅ লগআউট সফল হয়েছে।")

@bot.message_handler(commands=["buy"])
def buy(m):
    if not logged(m.from_user.id):
        bot.reply_to(m, "🔐 আগে /login করুন।")
        return
    bot.send_message(m.chat.id, "📟 ৩ সংখ্যার এরিয়া কোড দিন (যেমন 825):")

@bot.message_handler(commands=["random"])
def random_ac(m):
    if not logged(m.from_user.id):
        bot.reply_to(m, "🔐 আগে /login করুন।")
        return
    ac = random.choice(CANADA_CODES)
    bot.send_message(m.chat.id, f"🎲 এলোমেলো এরিয়া কোড: {ac}")
    _send_area_code_numbers(m.from_user.id, m.chat.id, ac)

@bot.message_handler(commands=["returnsms"])
@run_async
def returnsms(m):
    uid = m.from_user.id
    if not logged(uid):
        bot.reply_to(m, "🔐 আগে /login করুন।")
        return
    sess = user_session[uid]
    client = sess["twilio_client"]
    num = sess.get("purchased_number")
    if not num:
        bot.reply_to(m, "❗️ আপনি কোনো নাম্বার কিনেননি।")
        return
    since = datetime.utcnow() - timedelta(hours=1)
    try:
        msgs = client.messages.list(to=num, date_sent_after=since)
        _send_formatted_sms(m.chat.id, msgs[0], num) if msgs else bot.send_message(m.chat.id, "📭 কোনো মেসেজ নেই।")
    except: bot.send_message(m.chat.id, "⚠️ মেসেজ আনতে সমস্যা।")

# ─── Login Catcher ───
cred_re = re.compile(r"^(AC[a-zA-Z0-9]{32})\s+([a-zA-Z0-9]{32,})$")
@bot.message_handler(func=lambda m: cred_re.match(m.text or ""))
@run_async
def handle_login(m):
    try:
        sid, token = m.text.strip().split()
        client = Client(sid, token, http_client=SpoofedHttpClient())
        client.api.accounts(sid).fetch()
        user_session[m.from_user.id] = {
            "twilio_client": client,
            "sid": sid,
            "token": token,
            "purchased_number": None
        }
        bot.send_message(m.chat.id, "✅ লগইন সফল। এখন এরিয়া কোড দিন বা /buy লিখুন।")
    except:
        bot.send_message(m.chat.id, "❌ লগইন ব্যর্থ। SID বা Token ভুল অথবা ব্লক করা হয়েছে।")

@bot.message_handler(func=lambda m: re.fullmatch(r"\d{3}", m.text or ""))
def handle_ac(m):
    if not logged(m.from_user.id):
        bot.reply_to(m, "🔐 আগে /login করুন।")
        return
    _send_area_code_numbers(m.from_user.id, m.chat.id, m.text.strip())

@bot.message_handler(func=lambda m: re.fullmatch(r"\+1\d{10}", m.text or ""))
@run_async
def auto_buy(m):
    if not logged(m.from_user.id):
        bot.reply_to(m, "🔐 আগে /login করুন।")
        return
    uid, chat, num = m.from_user.id, m.chat.id, m.text.strip()
    sess = user_session[uid]
    client = sess["twilio_client"]
    _stop_sms_listener(sess)
    old = sess.get("purchased_number")
    try:
        if old:
            for n in client.incoming_phone_numbers.list():
                if n.phone_number == old:
                    client.incoming_phone_numbers(n.sid).delete()
                    break
    except: pass
    try:
        client.incoming_phone_numbers.create(phone_number=num)
        sess["purchased_number"] = num
        _start_sms_listener(uid, chat)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📥 View SMS", callback_data="viewsms"))
        bot.send_message(chat, f"✅ নাম্বার কিনেছেন: {num}", reply_markup=kb)
    except Exception as e:
        txt = str(e).lower()
        if "not available" in txt:
            bot.send_message(chat, f"❌ নাম্বার কেনা যায়নি: {num} available না।")
        else:
            bot.send_message(chat, f"❌ নাম্বার কেনা যায়নি।\n{e}")

@bot.callback_query_handler(func=lambda c: c.data == "viewsms")
@run_async
def view_sms(call):
    if not logged(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ লগইন নেই।")
        return
    sess = user_session[call.from_user.id]
    client = sess["twilio_client"]
    num = sess.get("purchased_number")
    try:
        msgs = client.messages.list(to=num, limit=1)
        _send_formatted_sms(call.message.chat.id, msgs[0], num) if msgs else bot.send_message(call.message.chat.id, "📭 কোনো মেসেজ নেই।")
    except:
        bot.send_message(call.message.chat.id, "⚠️ মেসেজ আনতে সমস্যা।")

@run_async
def _send_area_code_numbers(uid, chat, ac):
    sess = user_session[uid]
    client = sess["twilio_client"]
    try:
        nums = client.available_phone_numbers("CA").local.list(area_code=ac, limit=30)
        if not nums:
            bot.send_message(chat, f"❗️ এরিয়া কোড {ac}-এ কোনো নাম্বার নেই।")
            return
        bot.send_message(chat, f"📞 ৩০টি নাম্বার ({ac}):")
        for n in nums:
            bot.send_message(chat, n.phone_number)
        bot.send_message(chat, "✅ যেকোনো নাম্বার কপি করে পাঠান।")
    except Exception as e:
        bot.send_message(chat, f"⚠️ নাম্বার আনতে সমস্যা:\n{e}")

def _send_formatted_sms(chat, msg, number):
    otp = extract_otp(msg.body)
    html = (
        f"🕰️ Time: {msg.date_sent}\n📞 Number: {number}\n🌍 Country: 🇨🇦 Canada\n"
        f"🔑 OTP: <code>{otp}</code>\n📬 Message:\n<blockquote>{msg.body}</blockquote>\n\n"
        "👑 BOT OWNER: @ShrabonAhmed"
    )
    bot.send_message(chat, html)
    forward_to_group(html)

@bot.message_handler(func=lambda *_: True)
def fallback(m):
    bot.reply_to(m, "⚠️ আমি বুঝতে পারিনি। Twilio SID/Token, এরিয়া কোড, বা নাম্বার দিন।")

print("🤖 Bot running…")
if __name__ == "__main__":
    bot.infinity_polling(none_stop=True, timeout=0, skip_pending=True)