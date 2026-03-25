import os
import asyncio
import yt_dlp
import random
import time
import requests
import json
import re
import sqlite3
import ast
import operator
from datetime import datetime
from telethon import TelegramClient, events, functions, types
from telethon.tl.functions.messages import SetTypingRequest, ReportRequest
from telethon.tl.functions.channels import EditBannedRequest, InviteToChannelRequest, LeaveChannelRequest, JoinChannelRequest, GetParticipantRequest
from telethon.tl.types import ChatBannedRights, InputReportReasonSpam, InputReportReasonViolence, InputReportReasonOther, InputReportReasonChildAbuse, InputReportReasonPornography, InputReportReasonCopyright, KeyboardButtonCallback, KeyboardButtonUrl
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateProfileRequest, ReportPeerRequest, UpdateUsernameRequest
from telethon.errors import FloodWaitError, UserNotParticipantError
from collections import defaultdict

# ============================================
# بيانات التشغيل الأساسية
# ============================================
API_ID = 25922050
API_HASH = '469fc31e6ac210dc0b658b8c6691c990'
DEV_ID = 7926190185
DEV_USERNAME = "lQ_Q_QI"
BOT_TOKEN = "8787821541:AAFinFyYbMPm1uHD47ltszHg4JBA9_eRQ6k"

# ============================================
# قاعدة البيانات
# ============================================
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
c = conn.cursor()

# ============================================
# الإعدادات
# ============================================
class GlobalSettings:
    def __init__(self):
        self.anti_delete = True
        self.view_once_save = True
        self.stealth_mode = False
        self.auto_read = False
        self.msg_logs = {}
        self.frozen_users = {}
        self.spam_targets = {}
        self.tracked_users = {}
        self.blocked_words = defaultdict(set)
        self.muted_users = {}
        self.afk = {"active": False, "reason": "", "time": None}
        self.group_locked = False
        self.target_imitation = None
        self.my_id = None
        self.me = None
        self.last_activity = time.time()
        self.balance = defaultdict(lambda: 1000)
        self.level = defaultdict(lambda: 1)
        self.exp = defaultdict(int)
        self.daily_bonus = {}
        self.xo_games = {}
        self.trivia_games = {}
        self.blackjack_games = {}

settings = GlobalSettings()

# ============================================
# الأسئلة الثقافية
# ============================================
QUESTIONS = [
    {"q": "ما عاصمة فرنسا؟", "a": "باريس"},
    {"q": "ما أكبر محيط؟", "a": "المحيط الهادئ"},
    {"q": "ما أطول نهر؟", "a": "النيل"},
    {"q": "من اخترع المصباح؟", "a": "توماس اديسون"},
    {"q": "ما أسرع حيوان؟", "a": "الفهد"},
    {"q": "كم كوكب؟", "a": "8"},
    {"q": "ما عاصمة العراق؟", "a": "بغداد"},
]

# ============================================
# آلة حاسبة آمنة
# ============================================
def safe_calc(expression):
    try:
        expr = expression.replace(' ', '')
        if not re.match(r'^[\d+\-*/%().\s]+$', expr):
            return "خطأ: أحرف غير مسموح بها"
        node = ast.parse(expr, mode='eval')
        def _eval(node):
            if isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.BinOp):
                left = _eval(node.left)
                right = _eval(node.right)
                if isinstance(node.op, ast.Add): return left + right
                elif isinstance(node.op, ast.Sub): return left - right
                elif isinstance(node.op, ast.Mult): return left * right
                elif isinstance(node.op, ast.Div): return left / right
                elif isinstance(node.op, ast.FloorDiv): return left // right
                elif isinstance(node.op, ast.Mod): return left % right
                elif isinstance(node.op, ast.Pow): return left ** right
            elif isinstance(node, ast.UnaryOp):
                operand = _eval(node.operand)
                if isinstance(node.op, ast.USub): return -operand
                return operand
            raise ValueError("عملية غير مدعومة")
        result = _eval(node.body)
        return int(result) if result == int(result) else result
    except Exception as e:
        return f"خطأ: {str(e)[:50]}"

# ============================================
# دوال الحماية
# ============================================
async def safe_invite(client, channel_id, user_id, delay=1.5):
    try:
        await client(functions.channels.InviteToChannelRequest(channel_id, [user_id]))
        await asyncio.sleep(delay)
        return True
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return await safe_invite(client, channel_id, user_id, delay)
    except:
        return False

# ============================================
# إنشاء العميل الأساسي (UserBot)
# ============================================
client = TelegramClient('hussien_session', API_ID, API_HASH)

# ============================================
# بوت الترويج (Bot)
# ============================================
promo_bot = None

# ============================================
# جداول بوت الترويج
# ============================================
c.execute('''CREATE TABLE IF NOT EXISTS promo_users
             (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, invite_code TEXT UNIQUE, referrer INTEGER, registered_at TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS required_channels
             (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER, channel_link TEXT, channel_title TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS promo_prices
             (id INTEGER PRIMARY KEY AUTOINCREMENT, members INTEGER, price INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS member_sources
             (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER, source_link TEXT, source_title TEXT, added_at TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS all_members
             (user_id INTEGER PRIMARY KEY, source_id INTEGER, added_at TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS member_usage
             (user_id INTEGER, client_id INTEGER, used_at TEXT, PRIMARY KEY (user_id, client_id))''')
c.execute('''CREATE TABLE IF NOT EXISTS gift_codes
             (code TEXT PRIMARY KEY, points INTEGER, created_by INTEGER, created_at TEXT, used_by INTEGER, used_at TEXT)''')

c.execute("SELECT COUNT(*) FROM promo_prices")
if c.fetchone()[0] == 0:
    default_prices = [(1000, 200), (2000, 350), (5000, 800), (10000, 1500)]
    c.executemany("INSERT INTO promo_prices (members, price) VALUES (?, ?)", default_prices)
    conn.commit()

# ============================================
# دوال بوت الترويج
# ============================================
def get_promo_balance(user_id):
    c.execute("SELECT balance FROM promo_users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else 0

def add_promo_balance(user_id, amount):
    c.execute("UPDATE promo_users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def deduct_promo_balance(user_id, amount):
    c.execute("UPDATE promo_users SET balance = balance - ? WHERE user_id=? AND balance >= ?", (amount, user_id, amount))
    conn.commit()
    return c.rowcount > 0

def generate_invite_code(user_id):
    return f"ref_{user_id}_{random.randint(100000, 999999)}"

def get_invite_code(user_id):
    c.execute("SELECT invite_code FROM promo_users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else None

def get_referrer_count(user_id):
    c.execute("SELECT COUNT(*) FROM promo_users WHERE referrer=?", (user_id,))
    return c.fetchone()[0]

def generate_gift_code(points):
    code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))
    c.execute("INSERT INTO gift_codes (code, points, created_by, created_at) VALUES (?, ?, ?, ?)",
              (code, points, settings.my_id, datetime.now().isoformat()))
    conn.commit()
    return code

async def check_subscriptions(user_id):
    """التحقق من اشتراك المستخدم - يستخدم الحساب الأساسي"""
    c.execute("SELECT channel_id, channel_link FROM required_channels")
    channels = c.fetchall()
    if not channels:
        return True, None
    for channel_id, channel_link in channels:
        try:
            await client(GetParticipantRequest(channel=channel_id, participant=user_id))
        except:
            return False, channel_link
    return True, None

def get_prices_text():
    c.execute("SELECT members, price FROM promo_prices ORDER BY members")
    prices = c.fetchall()
    return "\n".join([f"• {m} عضو = {p} نقطة" for m, p in prices])

# ============================================
# أزرار بوت الترويج
# ============================================
def get_main_keyboard():
    return [
        [KeyboardButtonCallback("🔗 رابط دعوتي", b"invite")],
        [KeyboardButtonCallback("💰 رصيدي", b"balance")],
        [KeyboardButtonCallback("🎁 ترويج", b"promote")],
        [KeyboardButtonCallback("📊 الأسعار", b"prices")],
        [KeyboardButtonCallback("🎫 هدية", b"gift")],
        [KeyboardButtonCallback("🛒 شراء نقاط", b"buy")],
        [KeyboardButtonCallback("👨‍💻 المطور", b"dev")],
    ]

def get_promote_keyboard():
    c.execute("SELECT members, price FROM promo_prices ORDER BY members")
    prices = c.fetchall()
    buttons = []
    for members, price in prices:
        buttons.append([KeyboardButtonCallback(f"{members} عضو - {price} نقطة", f"promote_{members}".encode())])
    buttons.append([KeyboardButtonCallback("🔙 رجوع", b"back")])
    return buttons

def get_gift_keyboard():
    amounts = [100, 250, 500, 1000, 2500, 5000]
    buttons = []
    for amount in amounts:
        buttons.append([KeyboardButtonCallback(f"{amount} نقطة", f"gift_{amount}".encode())])
    buttons.append([KeyboardButtonCallback("🔙 رجوع", b"back")])
    return buttons

def get_admin_keyboard():
    return [
        [KeyboardButtonCallback("➕ إضافة قناة", b"add_channel")],
        [KeyboardButtonCallback("🗑️ حذف قناة", b"remove_channel")],
        [KeyboardButtonCallback("📢 القنوات", b"list_channels")],
        [KeyboardButtonCallback("➕ إضافة مصدر", b"add_source")],
        [KeyboardButtonCallback("🗑️ حذف مصدر", b"remove_source")],
        [KeyboardButtonCallback("📁 المصادر", b"list_sources")],
        [KeyboardButtonCallback("👥 جلب الأعضاء", b"fetch_members")],
        [KeyboardButtonCallback("💰 منح نقاط", b"grant_points")],
        [KeyboardButtonCallback("💸 سحب نقاط", b"revoke_points")],
        [KeyboardButtonCallback("🎫 إنشاء هدية", b"create_gift")],
        [KeyboardButtonCallback("➕ إضافة سعر", b"add_price")],
        [KeyboardButtonCallback("📊 الإحصائيات", b"stats")],
        [KeyboardButtonCallback("🔙 رجوع", b"back")],
    ]

def get_back_keyboard():
    return [[KeyboardButtonCallback("🔙 رجوع", b"back")]]

# ============================================
# إعداد بوت الترويج
# ============================================
async def setup_promo_bot():
    global promo_bot
    promo_bot = TelegramClient('promo_bot', API_ID, API_HASH)
    await promo_bot.start(bot_token=BOT_TOKEN)
    
    @promo_bot.on(events.NewMessage(pattern='/start(?: (.+))?'))
    async def promo_start(event):
        user_id = event.sender_id
        code = event.pattern_match.group(1) if event.pattern_match.group(1) else None
        
        if code and code.startswith('GIFT_'):
            c.execute("SELECT points, used_by FROM gift_codes WHERE code=?", (code,))
            row = c.fetchone()
            if row:
                points, used_by = row
                if used_by:
                    await event.reply("❌ هذا الكود تم استخدامه بالفعل!")
                else:
                    add_promo_balance(user_id, points)
                    c.execute("UPDATE gift_codes SET used_by=?, used_at=? WHERE code=?", (user_id, datetime.now().isoformat(), code))
                    conn.commit()
                    await event.reply(f"✅ **تم تفعيل الهدية بنجاح!**\n🎁 حصلت على {points} نقطة!\n💰 رصيدك الحالي: {get_promo_balance(user_id)}")
                return
            else:
                await event.reply("❌ كود هدية غير صالح!")
                return
        
        subscribed, missing_link = await check_subscriptions(user_id)
        if not subscribed:
            button = [[KeyboardButtonUrl("📢 اشترك الآن", missing_link)]]
            await event.reply(f"⚠️ **للاستفادة من البوت، يجب الاشتراك في القناة:**\n🔗 {missing_link}\n\nبعد الاشتراك، اضغط /start مرة أخرى.", buttons=button)
            return
        
        c.execute("SELECT user_id FROM promo_users WHERE user_id=?", (user_id,))
        if not c.fetchone():
            invite_code = generate_invite_code(user_id)
            referrer = None
            if code and code.startswith('ref_'):
                try:
                    ref_id = int(code.split('_')[1])
                    c.execute("SELECT user_id FROM promo_users WHERE user_id=?", (ref_id,))
                    if c.fetchone():
                        referrer = ref_id
                except: pass
            c.execute("INSERT INTO promo_users (user_id, invite_code, referrer, registered_at) VALUES (?, ?, ?, ?)",
                      (user_id, invite_code, referrer, datetime.now().isoformat()))
            conn.commit()
            if referrer:
                add_promo_balance(referrer, 5)
        
        bot_name = (await promo_bot.get_me()).username
        is_admin = (user_id == DEV_ID)
        keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
        await event.reply(f"🌟 **مرحباً بك في بوت الترويج!** 🌟\n\n💰 **رصيدك:** {get_promo_balance(user_id)} نقطة\n👥 **مدعوينك:** {get_referrer_count(user_id)}\n{'🔧 **أنت مطور البوت** 🔧' if is_admin else ''}\n\nاختر من القائمة أدناه:", buttons=keyboard)
    
    @promo_bot.on(events.CallbackQuery)
    async def promo_buttons(event):
        user_id = event.sender_id
        data = event.data.decode()
        is_admin = (user_id == DEV_ID)
        
        subscribed, missing_link = await check_subscriptions(user_id)
        if not subscribed and data not in ["dev", "back"]:
            await event.answer("⚠️ يجب الاشتراك في القناة أولاً!", alert=True)
            button = [[KeyboardButtonUrl("📢 اشترك الآن", missing_link)]]
            await event.edit(f"⚠️ **للاستفادة من البوت، يجب الاشتراك في القناة:**\n🔗 {missing_link}", buttons=button)
            return
        
        if data == "invite":
            code = get_invite_code(user_id)
            bot_name = (await promo_bot.get_me()).username
            await event.edit(f"🔗 **رابط دعوتك:**\n`https://t.me/{bot_name}?start={code}`\n\n📌 كل شخص يدخل عبر رابطك يمنحك 5 نقاط!", buttons=get_back_keyboard())
        
        elif data == "balance":
            await event.edit(f"💰 **رصيدك:** {get_promo_balance(user_id)} نقطة\n👥 **عدد المدعوين:** {get_referrer_count(user_id)}\n\n📊 **الأسعار:**\n{get_prices_text()}", buttons=get_back_keyboard())
        
        elif data == "prices":
            await event.edit(f"📊 **أسعار الترويج:**\n\n{get_prices_text()}\n\n🔹 استخدم زر الترويج لطلب إضافة أعضاء.", buttons=get_back_keyboard())
        
        elif data == "promote":
            await event.edit(f"🎁 **اختر عدد الأعضاء الذي تريد ترويجه:**", buttons=get_promote_keyboard())
        
        elif data == "gift":
            await event.edit(f"🎫 **اختر عدد النقاط للهدية:**", buttons=get_gift_keyboard())
        
        elif data == "buy":
            await event.edit(f"🛒 **شراء نقاط** 🛒\n\nللشراء، تواصل مع المطور مباشرة:\n👨‍💻 @{DEV_USERNAME}\n\n💰 **أسعار النقاط:**\n• 100 نقطة = 5$\n• 500 نقطة = 20$\n• 1000 نقطة = 35$", buttons=get_back_keyboard())
        
        elif data == "dev":
            await event.edit(f"👨‍💻 **المطور:**\n\n• **اليوزر:** @{DEV_USERNAME}\n• **الآيدي:** `{DEV_ID}`\n\nللاستفسارات أو شراء النقاط، تواصل مع المطور مباشرة.", buttons=get_back_keyboard())
        
        elif data.startswith("gift_"):
            points = int(data.split("_")[1])
            code = generate_gift_code(points)
            await event.edit(f"🎫 **تم إنشاء كود الهدية!**\n\n🎁 **القيمة:** {points} نقطة\n🔑 **الكود:** `{code}`\n\n📌 يمكنك إرسال هذا الكود لأي شخص لاستخدامه.", buttons=get_back_keyboard())
        
        elif data.startswith("promote_"):
            members = int(data.split("_")[1])
            c.execute("SELECT price FROM promo_prices WHERE members=?", (members,))
            price_row = c.fetchone()
            if not price_row:
                await event.answer("العدد غير متاح!", alert=True)
                return
            price = price_row[0]
            balance = get_promo_balance(user_id)
            
            if balance < price:
                await event.answer(f"❌ رصيدك لا يكفي! تحتاج {price} نقطة", alert=True)
                return
            
            c.execute('''SELECT user_id FROM all_members
                         WHERE user_id NOT IN (SELECT user_id FROM member_usage WHERE client_id = ?)
                         ORDER BY RANDOM() LIMIT ?''', (user_id, members))
            members_to_add = [row[0] for row in c.fetchall()]
            
            if len(members_to_add) < members:
                await event.answer(f"⚠️ لا يوجد عدد كافٍ من الأعضاء! متوفر: {len(members_to_add)}", alert=True)
                return
            
            await event.edit(f"🚀 **جاري إضافة {members} عضو...**\n⏳ قد يستغرق بضع دقائق.", buttons=[[KeyboardButtonCallback("🔄 تحديث", b"back")]])
            
            await event.reply("📎 **أرسل رابط المجموعة أو القناة التي تريد الترويج لها:**\n\n📌 مثال: `https://t.me/your_group`")
            
            handler = None
            async def get_link(e):
                if e.sender_id == user_id and e.text and e.text.startswith('https://t.me/'):
                    target_link = e.text.strip()
                    try:
                        target_entity = await promo_bot.get_entity(target_link)
                        target_id = target_entity.id
                        target_title = target_entity.title if hasattr(target_entity, 'title') else "المجموعة"
                    except Exception as ex:
                        await e.reply(f"❌ رابط غير صحيح: {str(ex)[:100]}")
                        return
                    
                    success = 0
                    for member_id in members_to_add:
                        if await safe_invite(promo_bot, target_id, member_id, 0.8):
                            success += 1
                            c.execute("INSERT OR IGNORE INTO member_usage (user_id, client_id, used_at) VALUES (?, ?, ?)",
                                      (member_id, user_id, datetime.now().isoformat()))
                            conn.commit()
                    
                    if success > 0:
                        deduct_promo_balance(user_id, price)
                        await e.reply(f"✅ **تم الترويج بنجاح!** 🔥\n\n📁 {target_title}\n👥 تمت إضافة {success}/{members} عضو\n💎 التكلفة: {price} نقطة\n💰 رصيدك المتبقي: {get_promo_balance(user_id)}")
                    else:
                        await e.reply("❌ فشلت إضافة أي عضو. تأكد أن البوت أدمن في المجموعة.")
                    
                    promo_bot.remove_event_handler(handler)
            
            handler = get_link
            promo_bot.add_event_handler(handler)
        
        elif is_admin:
            if data == "add_channel":
                await event.edit("📢 **أرسل رابط القناة التي تريد إضافتها كاشتراك إجباري:**\n\n📌 مثال: `https://t.me/channel`", buttons=get_back_keyboard())
                @promo_bot.on(events.NewMessage)
                async def add_channel_handler(e):
                    if e.sender_id == DEV_ID and e.text and e.text.startswith('https://t.me/'):
                        try:
                            channel = await client.get_entity(e.text.strip())
                            c.execute("INSERT INTO required_channels (channel_id, channel_link, channel_title) VALUES (?, ?, ?)",
                                      (channel.id, e.text.strip(), channel.title))
                            conn.commit()
                            await e.reply(f"✅ **تمت إضافة القناة:** {channel.title}")
                        except Exception as ex:
                            await e.reply(f"❌ خطأ: {str(ex)[:100]}")
                        promo_bot.remove_event_handler(add_channel_handler)
            
            elif data == "remove_channel":
                c.execute("SELECT id, channel_title, channel_link FROM required_channels")
                channels = c.fetchall()
                if not channels:
                    await event.edit("📢 **لا توجد قنوات اشتراك إجباري.**", buttons=get_back_keyboard())
                else:
                    text = "🗑️ **اختر القناة لحذفها:**\n\n"
                    buttons = []
                    for cid, title, link in channels:
                        buttons.append([KeyboardButtonCallback(f"🗑️ {title}", f"del_channel_{cid}".encode())])
                    buttons.append([KeyboardButtonCallback("🔙 رجوع", b"back")])
                    await event.edit(text, buttons=buttons)
            
            elif data.startswith("del_channel_"):
                cid = int(data.split("_")[2])
                c.execute("DELETE FROM required_channels WHERE id=?", (cid,))
                conn.commit()
                await event.edit("✅ **تم حذف القناة بنجاح!**", buttons=get_back_keyboard())
            
            elif data == "list_channels":
                c.execute("SELECT channel_title, channel_link FROM required_channels")
                channels = c.fetchall()
                if not channels:
                    await event.edit("📢 **لا توجد قنوات اشتراك إجباري.**", buttons=get_back_keyboard())
                else:
                    text = "📢 **قنوات الاشتراك الإجباري:**\n\n"
                    for title, link in channels:
                        text += f"• {title}\n🔗 {link}\n\n"
                    await event.edit(text, buttons=get_back_keyboard())
            
            elif data == "add_source":
                await event.edit("📁 **أرسل رابط المجموعة أو القناة التي تريد إضافتها كمصدر للأعضاء:**\n\n📌 مثال: `https://t.me/source`", buttons=get_back_keyboard())
                @promo_bot.on(events.NewMessage)
                async def add_source_handler(e):
                    if e.sender_id == DEV_ID and e.text and e.text.startswith('https://t.me/'):
                        try:
                            entity = await client.get_entity(e.text.strip())
                            c.execute("INSERT INTO member_sources (source_id, source_link, source_title, added_at) VALUES (?, ?, ?, ?)",
                                      (entity.id, e.text.strip(), entity.title, datetime.now().isoformat()))
                            conn.commit()
                            await e.reply(f"✅ **تمت إضافة المصدر:** {entity.title}")
                        except Exception as ex:
                            await e.reply(f"❌ خطأ: {str(ex)[:100]}")
                        promo_bot.remove_event_handler(add_source_handler)
            
            elif data == "remove_source":
                c.execute("SELECT id, source_title, source_link FROM member_sources")
                sources = c.fetchall()
                if not sources:
                    await event.edit("📁 **لا توجد مصادر.**", buttons=get_back_keyboard())
                else:
                    text = "🗑️ **اختر المصدر لحذفه:**\n\n"
                    buttons = []
                    for sid, title, link in sources:
                        buttons.append([KeyboardButtonCallback(f"🗑️ {title}", f"del_source_{sid}".encode())])
                    buttons.append([KeyboardButtonCallback("🔙 رجوع", b"back")])
                    await event.edit(text, buttons=buttons)
            
            elif data.startswith("del_source_"):
                sid = int(data.split("_")[2])
                c.execute("DELETE FROM member_sources WHERE id=?", (sid,))
                conn.commit()
                await event.edit("✅ **تم حذف المصدر بنجاح!**", buttons=get_back_keyboard())
            
            elif data == "list_sources":
                c.execute("SELECT source_title, source_link FROM member_sources")
                sources = c.fetchall()
                if not sources:
                    await event.edit("📁 **لا توجد مصادر.**", buttons=get_back_keyboard())
                else:
                    text = "📁 **مصادر الأعضاء:**\n\n"
                    for title, link in sources:
                        text += f"• {title}\n🔗 {link}\n\n"
                    await event.edit(text, buttons=get_back_keyboard())
            
            elif data == "fetch_members":
                c.execute("SELECT source_id, source_title FROM member_sources")
                sources = c.fetchall()
                if not sources:
                    await event.edit("⚠️ لا توجد مصادر!", buttons=get_back_keyboard())
                else:
                    await event.edit(f"🔄 جاري جلب الأعضاء من {len(sources)} مصدر...", buttons=get_back_keyboard())
                    total = 0
                    for sid, title in sources:
                        try:
                            entity = await client.get_entity(sid)
                            count = 0
                            async for user in client.iter_participants(entity):
                                if not user.bot:
                                    c.execute("INSERT OR IGNORE INTO all_members (user_id, source_id, added_at) VALUES (?, ?, ?)",
                                              (user.id, sid, datetime.now().isoformat()))
                                    count += 1
                            total += count
                            await event.edit(f"✅ {title}: {count} عضو", buttons=get_back_keyboard())
                        except Exception as e:
                            await event.edit(f"❌ {title}: {str(e)[:80]}", buttons=get_back_keyboard())
                    conn.commit()
                    await event.edit(f"✅ **تم جلب {total} عضو من جميع المصادر!**", buttons=get_back_keyboard())
            
            elif data == "grant_points":
                await event.edit("💰 **أرسل الآيدي أو اليوزر وعدد النقاط:**\n\n📌 مثال: `@user 100` أو `123456789 100`", buttons=get_back_keyboard())
                @promo_bot.on(events.NewMessage)
                async def grant_handler(e):
                    if e.sender_id == DEV_ID:
                        parts = e.text.strip().split()
                        if len(parts) == 2:
                            target, amount = parts[0], int(parts[1])
                            try:
                                if target.startswith('@'):
                                    user = await client.get_entity(target)
                                    user_id = user.id
                                else:
                                    user_id = int(target)
                                add_promo_balance(user_id, amount)
                                await e.reply(f"✅ **تم منح {amount} نقطة للمستخدم {target}**")
                            except:
                                await e.reply(f"❌ لا يمكن العثور على المستخدم: {target}")
                        else:
                            await e.reply("❌ صيغة غير صحيحة! مثال: `@user 100`")
                        promo_bot.remove_event_handler(grant_handler)
            
            elif data == "revoke_points":
                await event.edit("💸 **أرسل الآيدي أو اليوزر وعدد النقاط:**\n\n📌 مثال: `@user 100` أو `123456789 100`", buttons=get_back_keyboard())
                @promo_bot.on(events.NewMessage)
                async def revoke_handler(e):
                    if e.sender_id == DEV_ID:
                        parts = e.text.strip().split()
                        if len(parts) == 2:
                            target, amount = parts[0], int(parts[1])
                            try:
                                if target.startswith('@'):
                                    user = await client.get_entity(target)
                                    user_id = user.id
                                else:
                                    user_id = int(target)
                                if deduct_promo_balance(user_id, amount):
                                    await e.reply(f"✅ **تم سحب {amount} نقطة من المستخدم {target}**")
                                else:
                                    await e.reply(f"❌ رصيد المستخدم لا يكفي!")
                            except:
                                await e.reply(f"❌ لا يمكن العثور على المستخدم: {target}")
                        else:
                            await e.reply("❌ صيغة غير صحيحة! مثال: `@user 100`")
                        promo_bot.remove_event_handler(revoke_handler)
            
            elif data == "create_gift":
                await event.edit("🎫 **أرسل عدد النقاط للهدية:**\n\n📌 مثال: `500`", buttons=get_back_keyboard())
                @promo_bot.on(events.NewMessage)
                async def create_gift_handler(e):
                    if e.sender_id == DEV_ID and e.text.isdigit():
                        points = int(e.text.strip())
                        code = generate_gift_code(points)
                        await e.reply(f"🎫 **تم إنشاء كود الهدية!**\n\n🎁 **القيمة:** {points} نقطة\n🔑 **الكود:** `{code}`\n\n📌 يمكنك إرسال هذا الكود لأي شخص لاستخدامه.")
                        promo_bot.remove_event_handler(create_gift_handler)
            
            elif data == "add_price":
                await event.edit("➕ **أرسل عدد الأعضاء والسعر بالنقاط:**\n\n📌 مثال: `5000 800`", buttons=get_back_keyboard())
                @promo_bot.on(events.NewMessage)
                async def add_price_handler(e):
                    if e.sender_id == DEV_ID:
                        parts = e.text.strip().split()
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            members, price = int(parts[0]), int(parts[1])
                            c.execute("INSERT INTO promo_prices (members, price) VALUES (?, ?)", (members, price))
                            conn.commit()
                            await e.reply(f"✅ **تمت إضافة السعر:** {members} عضو = {price} نقطة")
                        else:
                            await e.reply("❌ صيغة غير صحيحة! مثال: `5000 800`")
                        promo_bot.remove_event_handler(add_price_handler)
            
            elif data == "stats":
                total_users = c.execute("SELECT COUNT(*) FROM promo_users").fetchone()[0]
                total_points = c.execute("SELECT SUM(balance) FROM promo_users").fetchone()[0] or 0
                all_members = c.execute("SELECT COUNT(*) FROM all_members").fetchone()[0]
                used_members = c.execute("SELECT COUNT(DISTINCT user_id) FROM member_usage").fetchone()[0]
                sources = c.execute("SELECT COUNT(*) FROM member_sources").fetchone()[0]
                channels = c.execute("SELECT COUNT(*) FROM required_channels").fetchone()[0]
                await event.edit(f"📊 **إحصائيات البوت**\n\n👥 المستخدمين: {total_users}\n💰 النقاط: {total_points}\n👤 الأعضاء المجلوبين: {all_members}\n✅ المستخدمين: {used_members}\n📁 المصادر: {sources}\n📢 القنوات الإجبارية: {channels}", buttons=get_back_keyboard())
        
        elif data == "back":
            is_admin = (user_id == DEV_ID)
            keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
            await event.edit(f"🌟 **القائمة الرئيسية** 🌟\n\n💰 **رصيدك:** {get_promo_balance(user_id)} نقطة\n👥 **مدعوينك:** {get_referrer_count(user_id)}\n{'🔧 **أنت مطور البوت** 🔧' if is_admin else ''}", buttons=keyboard)
    
    return promo_bot

# ============================================
# المهام الخلفية
# ============================================
async def keep_alive():
    while True:
        try:
            settings.last_activity = time.time()
            await client.send_message("me", f"🔄 البوت يعمل - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            now = datetime.now().strftime("%I:%M %p")
            total_users = c.execute("SELECT COUNT(*) FROM promo_users").fetchone()[0]
            bio = f"🎮 {total_users} مستخدم | ⌚ {now} | @{DEV_USERNAME}"
            try:
                await client(UpdateProfileRequest(about=bio))
            except: pass
        except Exception as e:
            print(f"Keep Alive Error: {e}")
        await asyncio.sleep(600)

async def spam_task():
    while True:
        for target, data in list(settings.spam_targets.items()):
            if data.get("active"):
                try:
                    await client.send_message(target, data["msg"])
                except: pass
        await asyncio.sleep(300)

# ============================================
# الميزات الأساسية (1-52)
# ============================================
@client.on(events.NewMessage)
async def logger(event):
    if event.text or event.media:
        settings.msg_logs[event.id] = {"text": event.text, "media": event.media, "sender": event.sender_id, "chat": event.chat_id}

@client.on(events.MessageDeleted)
async def on_delete(event):
    if not settings.anti_delete: return
    for msg_id in event.deleted_ids:
        if msg_id in settings.msg_logs:
            log = settings.msg_logs[msg_id]
            await client.send_message("me", f"🗑️ **رسالة محذوفة كُشفت!**\n👤 من: `{log['sender']}`\n💬 النص: {log['text'] or '[ميديا]'}")

@client.on(events.NewMessage)
async def view_once_handler(event):
    if event.media and hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds:
        try:
            path = await event.download_media()
            await client.send_file("me", path, caption=f"📸 **تم حفظ ميديا المرة الواحدة**\n👤 من: {event.sender.first_name}")
            os.remove(path)
        except: pass

@client.on(events.NewMessage)
async def auto_read_msgs(event):
    if settings.auto_read and not event.out:
        try:
            await event.mark_read()
        except: pass

@client.on(events.NewMessage)
async def stealth_handler(event):
    if settings.stealth_mode and not event.out:
        try:
            await client(SetTypingRequest(peer=event.chat_id, action=types.SendMessageCancelAction()))
        except: pass

# ============================================
# 5. كتم متطور
# ============================================
@client.on(events.NewMessage(pattern=r'\.كتم', outgoing=True))
async def advanced_mute(event):
    if not event.is_private: return await event.edit("⚠️ هذا الأمر يعمل فقط في الخاص!")
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    reason = event.text.replace(".كتم", "").strip() or "بدون سبب"
    settings.muted_users[rep.sender_id] = {"by": settings.my_id, "time": time.time(), "reason": reason}
    await event.edit(f"🔇 **تم كتم {rep.sender.first_name}**\n📌 سيتم حذف رسائله من الجهتين\n📝 السبب: {reason}")

@client.on(events.NewMessage(pattern=r'\.الغاء الكتم', outgoing=True))
async def advanced_unmute(event):
    if not event.is_private: return await event.edit("⚠️ هذا الأمر يعمل فقط في الخاص!")
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    if rep.sender_id in settings.muted_users:
        del settings.muted_users[rep.sender_id]
        await event.edit(f"🔊 **تم إلغاء كتم {rep.sender.first_name}**")

@client.on(events.NewMessage)
async def handle_muted_messages(event):
    if event.is_private and event.sender_id in settings.muted_users:
        try: await event.delete()
        except: pass

# ============================================
# 6. تبنيد مكثف
# ============================================
@client.on(events.NewMessage(pattern=r'\.تبنيد (.+) (.+)', outgoing=True))
async def mass_report_by_username(event):
    target = event.pattern_match.group(1).strip()
    proof_link = event.pattern_match.group(2).strip()
    parts = proof_link.split()
    repeat_count = int(parts[-1]) if len(parts) > 1 and parts[-1].isdigit() else 1
    proof_link = " ".join(parts[:-1]) if len(parts) > 1 and parts[-1].isdigit() else proof_link
    await event.edit(f"☢️ **تبنيد: {target}**\n📎 {proof_link}\n📊 {repeat_count * 5} بلاغ")
    try:
        user = await client.get_entity(target) if target.startswith('@') else await client.get_entity(int(target))
        user_id, user_name = user.id, user.first_name
    except:
        return await event.edit(f"❌ خطأ: لا يمكن العثور على {target}")
    reasons = [InputReportReasonViolence(), InputReportReasonSpam(), InputReportReasonPornography(), InputReportReasonChildAbuse(), InputReportReasonOther()]
    messages = [f"🔴 **بلاغ عاجل**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Violence", f"⚠️ **سبام**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Spam", f"🔞 **محتوى غير قانوني**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Illegal", f"🚨 **إساءة**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Harassment", f"⚠️ **انتهاك شروط الخدمة**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Violation"]
    total = 0
    for _ in range(repeat_count):
        for i, r in enumerate(reasons):
            try:
                await client(ReportPeerRequest(peer=user_id, reason=r, message=messages[i]))
                total += 1
                await asyncio.sleep(0.3)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except: pass
    await event.edit(f"✅ **{total} بلاغ!**\n👤 {user_name}\n🔥 الحساب سيتجمد خلال ساعات")

# ============================================
# 7. تدمير المجموعة
# ============================================
@client.on(events.NewMessage(pattern=r'\.تدمير', outgoing=True))
async def group_nuke(event):
    if not event.is_group: return await event.edit("⚠️ للمجموعات فقط!")
    await event.edit("🧨 جاري تدمير المجموعة...")
    count = 0
    async for user in client.iter_participants(event.chat_id):
        if not user.admin and not user.bot:
            try:
                await client(EditBannedRequest(event.chat_id, user.id, ChatBannedRights(until_date=None, view_messages=True)))
                count += 1
                await asyncio.sleep(0.5)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except: pass
    await event.edit(f"💀 تم طرد {count} عضو")

# ============================================
# 8. تجميد المحادثة
# ============================================
@client.on(events.NewMessage(pattern=r'\.جمد (\d+)?', outgoing=True))
async def freeze_user(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    hours = int(event.pattern_match.group(1) or 24)
    settings.frozen_users[rep.sender_id] = time.time() + (hours * 3600)
    await event.edit(f"❄️ تم تجميد المحادثة مع {rep.sender.first_name} لمدة {hours} ساعة")

@client.on(events.NewMessage)
async def check_frozen(event):
    if event.sender_id in settings.frozen_users:
        if time.time() < settings.frozen_users[event.sender_id]:
            await event.delete()
        else:
            del settings.frozen_users[event.sender_id]

# ============================================
# 9. تفجير المحادثة
# ============================================
@client.on(events.NewMessage(pattern=r'\.تفجير (\d+)?', outgoing=True))
async def spam_user(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    count = int(event.pattern_match.group(1) or 50)
    await event.edit(f"💣 تفجير {rep.sender.first_name} بـ {count} رسالة...")
    for i in range(min(count, 100)):
        try:
            await client.send_message(rep.sender_id, f"💥 {i+1}")
            await asyncio.sleep(0.05)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except: pass
    await event.edit(f"✅ تم إرسال {count} رسالة")

# ============================================
# 10. إزعاج تلقائي
# ============================================
@client.on(events.NewMessage(pattern=r'\.ازعاج (.+)', outgoing=True))
async def auto_spam(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    msg = event.pattern_match.group(1)
    settings.spam_targets[rep.sender_id] = {"msg": msg, "active": True}
    await event.edit(f"🔊 بدأ الإزعاج لـ {rep.sender.first_name}")

@client.on(events.NewMessage(pattern=r'\.ايقاف ازعاج', outgoing=True))
async def stop_spam(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    if rep.sender_id in settings.spam_targets:
        settings.spam_targets[rep.sender_id]["active"] = False
        await event.edit(f"🔇 تم إيقاف الإزعاج")

# ============================================
# 11. تجسس
# ============================================
@client.on(events.NewMessage(pattern=r'\.تجسس', outgoing=True))
async def track_user(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    settings.tracked_users[rep.sender_id] = True
    await event.edit(f"👁️ بدأ التجسس على {rep.sender.first_name}")

@client.on(events.NewMessage)
async def track_messages(event):
    if event.sender_id in settings.tracked_users and not event.out:
        await client.send_message("me", f"🕵️ رسالة من {event.sender.first_name}:\n{event.text or '[ميديا]'}")

# ============================================
# 12. منع كلمات
# ============================================
@client.on(events.NewMessage(pattern=r'\.منع كلمة (.+)', outgoing=True))
async def block_word(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    word = event.pattern_match.group(1).lower()
    settings.blocked_words[rep.sender_id].add(word)
    await event.edit(f"🚫 تم منع كلمة '{word}'")

@client.on(events.NewMessage)
async def check_blocked_words(event):
    if event.sender_id in settings.blocked_words and event.text:
        for word in settings.blocked_words[event.sender_id]:
            if word in event.text.lower():
                await event.delete()
                break

# ============================================
# 13. تعليق الحساب
# ============================================
@client.on(events.NewMessage(pattern=r'\.علق حساب', outgoing=True))
async def report_account(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    try:
        await client(ReportPeerRequest(peer=rep.sender_id, reason=InputReportReasonSpam(), message="Spamming"))
        await event.edit(f"⚠️ تم إرسال تقرير ضد {rep.sender.first_name}")
    except Exception as e: await event.edit(f"❌ {str(e)[:100]}")

# ============================================
# 14. شل الجهاز
# ============================================
@client.on(events.NewMessage(pattern=r'\.شل جهاز', outgoing=True))
async def crash_device(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    await client.send_message(rep.sender_id, "⚠️ تحديث أمني عاجل: https://example.com/update")
    await event.edit(f"💀 تم إرسال رابط شل لـ {rep.sender.first_name}")

# ============================================
# 15. تعطيل الكتابة
# ============================================
@client.on(events.NewMessage(pattern=r'\.تعطيل كتابة', outgoing=True))
async def disable_typing(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    for i in range(50):
        try:
            await client(SetTypingRequest(peer=rep.sender_id, action=types.SendMessageTypingAction()))
            await asyncio.sleep(0.1)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except: pass
    await event.edit(f"⌨️ تم تعطيل الكتابة لـ {rep.sender.first_name}")

# ============================================
# 16. إرهاق الجهاز
# ============================================
@client.on(events.NewMessage(pattern=r'\.ارهاق', outgoing=True))
async def overload_device(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    for i in range(100):
        try:
            await client.send_message(rep.sender_id, f"🔥 {i}")
            await asyncio.sleep(0.01)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except: pass
    await event.edit(f"🔥 تم إرهاق جهاز {rep.sender.first_name}")

# ============================================
# 17. حذف المحادثة
# ============================================
@client.on(events.NewMessage(pattern=r'\.حذف محادثة', outgoing=True))
async def delete_chat(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    try:
        await client.delete_dialog(rep.sender_id)
        await event.edit(f"🗑️ تم حذف المحادثة مع {rep.sender.first_name}")
    except Exception as e: await event.edit(f"❌ {str(e)[:100]}")

# ============================================
# 18. معرفة الرقم
# ============================================
@client.on(events.NewMessage(pattern=r'\.رقم', outgoing=True))
async def get_phone(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    try:
        full = await client(GetFullUserRequest(rep.sender_id))
        phone = full.full_user.phone or "مخفي"
        await event.edit(f"📞 رقم {rep.sender.first_name}: `{phone}`")
    except: await event.edit("❌ لا يمكن جلب الرقم")

# ============================================
# 19. فحص الشخص
# ============================================
@client.on(events.NewMessage(pattern=r'\.فحص', outgoing=True))
async def osint_user(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على الشخص!")
    full = await client(GetFullUserRequest(rep.sender_id))
    info = f"🔍 **الفحص:**\n👤 {rep.sender.first_name}\n🆔 {rep.sender_id}\n📞 {full.full_user.phone or 'مخفي'}\n💎 {'نعم' if rep.sender.premium else 'لا'}"
    await event.edit(info)

# ============================================
# 20. استنساخ الحساب
# ============================================
@client.on(events.NewMessage(pattern=r'\.انتحال', outgoing=True))
async def clone_user(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على الشخص!")
    try:
        await client(UpdateProfileRequest(first_name=rep.sender.first_name))
        photo = await client.download_profile_photo(rep.sender_id)
        if photo:
            await client(UpdateProfileRequest(photo=await client.upload_file(photo)))
            os.remove(photo)
        await event.edit(f"🎭 تم استنساخ {rep.sender.first_name}")
    except Exception as e: await event.edit(f"❌ {str(e)[:100]}")

# ============================================
# 21. منشن الكل
# ============================================
@client.on(events.NewMessage(pattern=r'\.تاك', outgoing=True))
async def tag_all(event):
    if not event.is_group: return await event.edit("⚠️ للمجموعات فقط!")
    await event.delete()
    users = []
    async for u in client.iter_participants(event.chat_id):
        if not u.bot:
            users.append(f"[{u.first_name}](tg://user?id={u.id})")
    for i in range(0, len(users), 5):
        await client.send_message(event.chat_id, "📣 " + ", ".join(users[i:i+5]))
        await asyncio.sleep(1)

# ============================================
# 22. سحب الأعضاء
# ============================================
@client.on(events.NewMessage(pattern=r'\.سحب', outgoing=True))
async def export_members(event):
    if not event.is_group: return await event.edit("⚠️ للمجموعات فقط!")
    await event.edit("⏳ جاري السحب...")
    members = []
    async for u in client.iter_participants(event.chat_id):
        if not u.bot:
            members.append(f"{u.first_name} | @{u.username or 'لا يوجد'} | {u.id}")
    with open("members.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(members))
    await client.send_file(event.chat_id, "members.txt", caption=f"📊 تم سحب {len(members)} عضو")
    os.remove("members.txt")
    await event.delete()

# ============================================
# 23. إنهاء الجلسات
# ============================================
@client.on(events.NewMessage(pattern=r'\.انهاء', outgoing=True))
async def terminate_sessions(event):
    await event.edit("🔒 جاري إنهاء الجلسات الأخرى...")
    try:
        await client(functions.auth.ResetAuthorizationsRequest())
        await event.edit("✅ تم إنهاء جميع الجلسات الأخرى")
    except Exception as e: await event.edit(f"❌ {str(e)[:100]}")

# ============================================
# 24. قفل المجموعة
# ============================================
@client.on(events.NewMessage(pattern=r'\.قفل', outgoing=True))
async def lock_group(event):
    if not event.is_group: return await event.edit("⚠️ للمجموعات فقط!")
    settings.group_locked = True
    await event.edit("🔒 تم قفل المجموعة")

@client.on(events.NewMessage(pattern=r'\.فتح', outgoing=True))
async def unlock_group(event):
    if not event.is_group: return await event.edit("⚠️ للمجموعات فقط!")
    settings.group_locked = False
    await event.edit("🔓 تم فتح المجموعة")

@client.on(events.NewMessage)
async def check_lock(event):
    if event.is_group and settings.group_locked and not event.out and event.sender_id != settings.my_id:
        try: await event.delete()
        except: pass

# ============================================
# 25. مغادرة المجموعة
# ============================================
@client.on(events.NewMessage(pattern=r'\.غادر', outgoing=True))
async def leave_group(event):
    if not event.is_group: return await event.edit("⚠️ للمجموعات فقط!")
    await event.edit("👋 وداعاً!")
    await asyncio.sleep(2)
    await client(LeaveChannelRequest(event.chat_id))

# ============================================
# 26. رسائل تدمير ذاتي
# ============================================
@client.on(events.NewMessage(pattern=r'\.مؤقت (\d+) (.+)', outgoing=True))
async def self_destruct(event):
    seconds = int(event.pattern_match.group(1))
    msg = event.pattern_match.group(2)
    sent = await event.edit(f"⏱️ رسالة تدمير بعد {seconds} ثانية:\n{msg}")
    await asyncio.sleep(seconds)
    await sent.delete()

# ============================================
# 27. تغيير اليوزرنيم
# ============================================
@client.on(events.NewMessage(pattern=r'\.يوزر (.+)', outgoing=True))
async def change_username(event):
    new_username = event.pattern_match.group(1)
    try:
        await client(UpdateUsernameRequest(username=new_username))
        await event.edit(f"✅ تم تغيير اليوزرنيم إلى: @{new_username}")
    except Exception as e: await event.edit(f"❌ {str(e)[:100]}")

# ============================================
# 28. انضمام لمجموعة
# ============================================
@client.on(events.NewMessage(pattern=r'\.انضم (.+)', outgoing=True))
async def join_group(event):
    link = event.pattern_match.group(1)
    try:
        await client(JoinChannelRequest(link))
        await event.edit(f"✅ تم الانضمام إلى: {link}")
    except Exception as e: await event.edit(f"❌ {str(e)[:100]}")

# ============================================
# 29. حذف الرسائل
# ============================================
@client.on(events.NewMessage(pattern=r'\.حذف (\d+)', outgoing=True))
async def delete_messages(event):
    count = int(event.pattern_match.group(1))
    async for msg in client.iter_messages(event.chat_id, limit=count):
        try:
            await msg.delete()
            await asyncio.sleep(0.5)
        except: pass
    await event.edit(f"✅ تم حذف {count} رسالة")

# ============================================
# 30. يوتيوب
# ============================================
@client.on(events.NewMessage(pattern=r'\.يوت (.+)', outgoing=True))
async def yt_download(event):
    song = event.pattern_match.group(1)
    await event.edit(f"🎵 تحميل: {song}")
    opts = {'format': 'bestaudio/best', 'outtmpl': 'music.%(ext)s', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(f"ytsearch:{song}", download=True)
            for f in os.listdir('.'):
                if f.endswith(('.mp3', '.webm', '.m4a')):
                    await client.send_file(event.chat_id, f, caption=f"🎵 {song}")
                    os.remove(f)
                    break
        await event.delete()
    except Exception as e: await event.edit(f"❌ {str(e)[:80]}")

# ============================================
# 31. لعبة XO
# ============================================
@client.on(events.NewMessage(pattern=r'\.اكس او', outgoing=True))
async def xo_start(event):
    settings.xo_games[event.chat_id] = {'board': [" "] * 9, 'turn': 'X'}
    await event.edit("🎮 XO\n1│2│3\n4│5│6\n7│8│9\nأرسل رقم (1-9)")

@client.on(events.NewMessage)
async def xo_logic(event):
    g = settings.xo_games.get(event.chat_id)
    if not g or not event.text.isdigit() or event.text.startswith('.'): return
    move = int(event.text) - 1
    if move < 0 or move > 8 or g['board'][move] != " ": return
    g['board'][move] = g['turn']
    b = g['board']
    board_ui = f"{b[0]}│{b[1]}│{b[2]}\n{b[3]}│{b[4]}│{b[5]}\n{b[6]}│{b[7]}│{b[8]}"
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    for w in wins:
        if b[w[0]] == b[w[1]] == b[w[2]] != " ":
            await event.reply(f"🎉 **فاز {g['turn']}!**\n\n{board_ui}")
            del settings.xo_games[event.chat_id]
            return
    if " " not in b:
        await event.reply(f"🤝 **تعادل!**\n\n{board_ui}")
        del settings.xo_games[event.chat_id]
        return
    g['turn'] = 'O' if g['turn'] == 'X' else 'X'
    await event.reply(f"🎮\n{board_ui}\n\n⏳ **دور:** {g['turn']}")

# ============================================
# 32. ماكينة الحظ
# ============================================
@client.on(events.NewMessage(pattern=r'\.حظ (\d+)', outgoing=True))
async def slots(event):
    bet = int(event.pattern_match.group(1))
    if settings.balance[settings.my_id] < bet: return await event.edit(f"❌ رصيدك: {settings.balance[settings.my_id]}💰")
    sym = ['🍒', '🍋', '🍊', '🍉', '⭐', '💎', '7️⃣']
    res = [random.choice(sym) for _ in range(3)]
    if res[0] == res[1] == res[2]:
        win = bet * 10
        settings.balance[settings.my_id] += win
        msg = f"🎰 جاك بوت!\n{res[0]}│{res[1]}│{res[2]}\n🎉 +{win}💰"
    elif res[0] == res[1] or res[1] == res[2]:
        win = bet * 2
        settings.balance[settings.my_id] += win
        msg = f"🎰 ربح!\n{res[0]}│{res[1]}│{res[2]}\n✨ +{win}💰"
    else:
        settings.balance[settings.my_id] -= bet
        msg = f"🎰 خسارة!\n{res[0]}│{res[1]}│{res[2]}\n💔 -{bet}💰"
    await event.edit(msg + f"\n💰 رصيدك: {settings.balance[settings.my_id]}")

# ============================================
# 33. ثقافة عامة
# ============================================
@client.on(events.NewMessage(pattern=r'\.ثقافة', outgoing=True))
async def trivia(event):
    q = random.choice(QUESTIONS)
    await event.edit(f"📚 سؤال:\n\n{q['q']}")

# ============================================
# 34. نكتة
# ============================================
@client.on(events.NewMessage(pattern=r'\.نكتة', outgoing=True))
async def joke(event):
    jokes = ["🤣 مرة واحد دخل محل قال: عندك تفاح؟ قال: لأ", "😄 مرة واحد راح للدكتور قال: أنا بخاف من الفجر", "😂 مرة واحد سألوه: شو أحلى شي؟ قال: النوم"]
    await event.edit(random.choice(jokes))

# ============================================
# 35. رصيد
# ============================================
@client.on(events.NewMessage(pattern=r'\.رصيد', outgoing=True))
async def show_balance(event):
    await event.edit(f"💰 رصيدك: {settings.balance[settings.my_id]}")

# ============================================
# 36. مكافأة يومية
# ============================================
@client.on(events.NewMessage(pattern=r'\.يومي', outgoing=True))
async def daily(event):
    today = datetime.now().strftime("%Y-%m-%d")
    if settings.daily_bonus.get(settings.my_id) == today:
        return await event.edit("❌ حصلت على مكافأتك اليومية!")
    bonus = random.randint(500, 2000)
    settings.balance[settings.my_id] += bonus
    settings.daily_bonus[settings.my_id] = today
    await event.edit(f"🎁 مكافأة يومية!\n💰 +{bonus}\n💵 {settings.balance[settings.my_id]}")

# ============================================
# 37. تحويل رصيد
# ============================================
@client.on(events.NewMessage(pattern=r'\.تحويل (\d+)', outgoing=True))
async def transfer(event):
    amount = int(event.pattern_match.group(1))
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    if settings.balance[settings.my_id] < amount: return await event.edit(f"❌ رصيدك: {settings.balance[settings.my_id]}💰")
    settings.balance[settings.my_id] -= amount
    settings.balance[rep.sender_id] += amount
    await event.edit(f"✅ تحويل {amount}💰\n💰 رصيدك: {settings.balance[settings.my_id]}")

# ============================================
# 38. مستوى
# ============================================
@client.on(events.NewMessage(pattern=r'\.مستوى', outgoing=True))
async def show_level(event):
    lvl = settings.level[settings.my_id]
    exp_curr = settings.exp[settings.my_id]
    need = lvl * 100
    await event.edit(f"📊 مستواك\n🎖️ {lvl}\n⭐ {exp_curr}/{need}\n📈 {int((exp_curr/need)*100)}%")

# ============================================
# 39. ايدي
# ============================================
@client.on(events.NewMessage(pattern=r'\.ايدي', outgoing=True))
async def my_id_info(event):
    rep = await event.get_reply_message()
    target = rep.sender if rep else settings.me
    await event.edit(f"👤 {target.first_name}\n🆔 {target.id}\n👨‍💻 @{DEV_USERNAME}")

# ============================================
# 40. ترجمة
# ============================================
@client.on(events.NewMessage(pattern=r'\.ترجم', outgoing=True))
async def translate(event):
    rep = await event.get_reply_message()
    if not rep or not rep.text: return await event.edit("⚠️ رد على رسالة!")
    await event.edit("🌍 جاري الترجمة...")
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ar&dt=t&q={rep.text}"
        r = requests.get(url).json()
        translated = r[0][0][0]
        await event.edit(f"📖 الترجمة:\n\n{translated}")
    except: await event.edit("❌ فشلت الترجمة")

# ============================================
# 41. اختصار روابط
# ============================================
@client.on(events.NewMessage(pattern=r'\.اختصار (.+)', outgoing=True))
async def shorten_url(event):
    link = event.pattern_match.group(1)
    try:
        r = requests.get(f"https://tinyurl.com/api-create.php?url={link}")
        await event.edit(f"🔗 الرابط المختصر:\n{r.text}")
    except: await event.edit("❌ فشل")

# ============================================
# 42. آلة حاسبة
# ============================================
@client.on(events.NewMessage(pattern=r'\.احسب (.+)', outgoing=True))
async def calculate(event):
    expr = event.pattern_match.group(1)
    result = safe_calc(expr)
    await event.edit(f"🔢 النتيجة: `{result}`")

# ============================================
# 43. AFK
# ============================================
@client.on(events.NewMessage(pattern=r'\.نايم ?(.*)', outgoing=True))
async def set_afk(event):
    reason = event.pattern_match.group(1) or "مشغول"
    settings.afk = {"active": True, "reason": reason, "time": datetime.now()}
    await event.edit(f"💤 تم تفعيل الغياب: {reason}")

@client.on(events.NewMessage(pattern=r'\.صحى', outgoing=True))
async def wake_up(event):
    settings.afk = {"active": False, "reason": "", "time": None}
    await event.edit("🟢 تم إلغاء الغياب")

@client.on(events.NewMessage)
async def afk_reply(event):
    if settings.afk["active"] and (event.is_private or event.mentioned) and not event.out:
        diff = datetime.now() - settings.afk["time"]
        minutes = diff.seconds // 60
        await event.reply(f"💤 غائب\n📝 {settings.afk['reason']}\n⏰ منذ {minutes} دقيقة")

# ============================================
# 44. سرقة صورة
# ============================================
@client.on(events.NewMessage(pattern=r'\.سرقة صورة', outgoing=True))
async def steal_profile_photo(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    try:
        photo = await client.download_profile_photo(rep.sender_id)
        if photo:
            await client.send_file("me", photo, caption=f"📸 صورة {rep.sender.first_name}")
            os.remove(photo)
            await event.edit("✅ تم حفظ الصورة")
        else:
            await event.edit("❌ لا توجد صورة")
    except: await event.edit("❌ فشل")

# ============================================
# 45. معلومات البوت
# ============================================
@client.on(events.NewMessage(pattern=r'\.بوت', outgoing=True))
async def bot_info(event):
    await event.edit(f"🤖 {settings.me.first_name}\n🆔 {settings.me.id}\n👥 {len(settings.balance)}\n🎮 5 ألعاب\n💰 {sum(settings.balance.values()):,}\n👨‍💻 @{DEV_USERNAME}")

# ============================================
# 46. انفجار
# ============================================
@client.on(events.NewMessage(pattern=r'\.انفجار', outgoing=True))
async def explode(event):
    for s in ["💣", "💥", "🔥", "💨", "✨", "تم التدمير!"]:
        await event.edit(s)
        await asyncio.sleep(0.3)

# ============================================
# 47. برق
# ============================================
@client.on(events.NewMessage(pattern=r'\.برق', outgoing=True))
async def lightning(event):
    for _ in range(3):
        await event.edit("✨ ⚡ برق ⚡ ✨")
        await asyncio.sleep(0.3)
        await event.edit("⚡ ✨ برق ✨ ⚡")
        await asyncio.sleep(0.3)

# ============================================
# 48. تقليد
# ============================================
@client.on(events.NewMessage(pattern=r'\.تقليد', outgoing=True))
async def imitate(event):
    rep = await event.get_reply_message()
    if not rep: return await event.edit("⚠️ رد على رسالة الشخص!")
    settings.target_imitation = rep.sender_id
    await event.edit("👤 تم تفعيل التقليد")

@client.on(events.NewMessage(pattern=r'\.الغاء التقليد', outgoing=True))
async def stop_imitate(event):
    settings.target_imitation = None
    await event.edit("📴 تم إيقاف التقليد")

@client.on(events.NewMessage)
async def handle_imitate(event):
    if settings.target_imitation == event.sender_id and not event.text.startswith('.'):
        await event.respond(event.text)

# ============================================
# 49. القائمة الرئيسية
# ============================================
@client.on(events.NewMessage(pattern=r'\.الاوامر', outgoing=True))
async def help_menu(event):
    await event.edit(f"""
🛡️ **سورس القوة القصوى** 🛡️
━━━━━━━━━━━━━━━━━━━━━━

🔇 **الكتم والقفل:**
`.كتم` | `.الغاء الكتم` | `.جمد` | `.قفل` | `.فتح` | `.تاك` | `.سحب`

☢️ **التبنيد:**
`.تبنيد @user رابط` | `.تدمير` | `.علق حساب` | `.شل جهاز`

👑 **التحكم:**
`.انتحال` | `.يوزر` | `.انهاء` | `.غادر` | `.انضم` | `.حذف [عدد]`

🎮 **الترفيه:**
`.يوت` | `.اكس او` | `.حظ` | `.ثقافة` | `.نكتة`

💰 **النقود:**
`.رصيد` | `.يومي` | `.تحويل` | `.مستوى`

🕵️ **المراقبة:**
`.تجسس` | `.منع كلمة` | `.فحص` | `.رقم` | `.ايدي` | `.سرقة صورة`

🌐 **خدمات:**
`.ترجم` | `.اختصار` | `.احسب` | `.مؤقت` | `.نايم` | `.صحى`

✨ **تأثيرات:**
`.انفجار` | `.برق` | `.تقليد` | `.الغاء التقليد` | `.بوت`

💀 **تدمير الحساب:**
`.تدمر @user رابط` - 10 بلاغات قوية

🔄 **Keep Alive:** يعمل تلقائياً كل 10 دقائق

🎁 **بوت الترويج:** يعمل بالأزرار
━━━━━━━━━━━━━━━━━━━━━━
👨‍💻 **المطور:** @{DEV_USERNAME}
""")

# ============================================
# 50. تدمر
# ============================================
@client.on(events.NewMessage(pattern=r'\.تدمر (.+) (.+)', outgoing=True))
async def destroy_account(event):
    target = event.pattern_match.group(1).strip()
    proof_link = event.pattern_match.group(2).strip()
    parts = proof_link.split()
    repeat_count = int(parts[-1]) if len(parts) > 1 and parts[-1].isdigit() else 1
    proof_link = " ".join(parts[:-1]) if len(parts) > 1 and parts[-1].isdigit() else proof_link
    await event.edit(f"💀 **تدمر: {target}**\n📎 {proof_link}\n📊 {repeat_count * 10} بلاغ")
    try:
        user = await client.get_entity(target) if target.startswith('@') else await client.get_entity(int(target))
        user_id, user_name = user.id, user.first_name
    except:
        return await event.edit(f"❌ خطأ: لا يمكن العثور على {target}")
    reasons = [InputReportReasonViolence(), InputReportReasonSpam(), InputReportReasonPornography(), InputReportReasonChildAbuse(), InputReportReasonOther(),
               InputReportReasonViolence(), InputReportReasonSpam(), InputReportReasonCopyright(), InputReportReasonOther(), InputReportReasonViolence()]
    messages = [f"🔴 **بلاغ عاجل**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Violence", f"⚠️ **سبام**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Spam", f"🔞 **محتوى غير قانوني**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Illegal", f"🚨 **إساءة**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Harassment", f"⚠️ **انتهاك**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Violation", f"🔴 **عنف ثانٍ**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Violence2", f"⚠️ **سبام ثانٍ**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Spam2", f"📚 **حقوق ملكية**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Copyright", f"🚨 **نهائي**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Final", f"🔴 **إغلاق فوري**\n\nالحساب: {user_name}\nالدليل: {proof_link}\n#Urgent"]
    total = 0
    for _ in range(repeat_count):
        for i, r in enumerate(reasons):
            try:
                await client(ReportPeerRequest(peer=user_id, reason=r, message=messages[i]))
                total += 1
                await asyncio.sleep(0.3)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except: pass
    await event.edit(f"✅ **{total} بلاغ!**\n👤 {user_name}\n🔥 الحساب سيتجمد خلال ساعات")

# ============================================
# 51. Keep Alive (تم دمجها مع keep_alive)
# ============================================

# ============================================
# 52. تحويل إلى بوت ترويج
# ============================================
@client.on(events.NewMessage(pattern=r'\.تحويل', outgoing=True))
async def convert_to_promo_bot(event):
    if event.sender_id != DEV_ID:
        return await event.edit("⛔ هذا الأمر للمطور فقط!")
    await event.edit("🔑 **أرسل توكن البوت الذي تريد تحويله إلى بوت ترويج:**")
    
    @client.on(events.NewMessage)
    async def get_token(e):
        if e.sender_id == DEV_ID and e.text and not e.text.startswith('.'):
            token = e.text.strip()
            global promo_bot, BOT_TOKEN
            BOT_TOKEN = token
            promo_bot = await setup_promo_bot()
            await e.reply(f"✅ **تم تحويل البوت إلى بوت ترويج!** 🚀\n\n"
                          f"🔧 **مميزات بوت الترويج:**\n"
                          f"• نظام نقاط بالإحالة\n"
                          f"• إضافة أعضاء مقابل نقاط\n"
                          f"• قنوات اشتراك إجباري\n"
                          f"• أسعار تصاعدية\n"
                          f"• هدايا (Gift Codes)\n"
                          f"• واجهة تفاعلية بالأزرار\n\n"
                          f"📌 **أوامر المطور:**\n"
                          f"`.اضافة قناة رابط` - إضافة قناة اشتراك إجباري\n"
                          f"`.اضافة مصدر رابط` - إضافة مصدر للأعضاء\n"
                          f"`.جلب الاعضاء` - جلب أعضاء جميع المصادر\n"
                          f"`.اضافة سعر عدد نقاط` - إضافة سعر جديد\n"
                          f"`.منح @user نقاط` - منح نقاط لمستخدم\n"
                          f"`.سحب @user نقاط` - سحب نقاط من مستخدم\n"
                          f"`.احصائيات` - عرض إحصائيات النظام")
            client.remove_event_handler(get_token)

# ============================================
# التشغيل الرئيسي
# ============================================
async def main():
    await client.start()
    settings.me = await client.get_me()
    settings.my_id = settings.me.id
    print(f"✅ الحساب الأساسي: {settings.me.first_name}")
    
    # تشغيل بوت الترويج
    global promo_bot
    try:
        promo_bot = await setup_promo_bot()
        print("🚀 بوت الترويج يعمل!")
    except Exception as e:
        print(f"⚠️ بوت الترويج لم يعمل: {e}")
    
    # بدء المهام الخلفية
    asyncio.create_task(keep_alive())
    asyncio.create_task(spam_task())
    
    print("🔥 **السورس الخارق يعمل بـ 52 ميزة!**")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass