from flask import Flask, request, jsonify, render_template_string, redirect
import logging
import sqlite3
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import threading
import time
import os
from dotenv import load_dotenv
import json,os
import asyncio
from flask import request
from flask_cors import CORS
import re
import tempfile


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
module_dir = os.path.abspath(os.path.dirname(__file__))

load_dotenv()

# بيانات التطبيق
KEY = os.getenv("KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
LEADERBOARD_FILE = module_dir+os.sep+"leaderboard.json"
WITHDRAW_LOG = module_dir+os.sep+"withdrawals.log"
PARTNERSHIP_LOG = module_dir+os.sep+"partnerships.log"
TASKS_FILE = module_dir+os.sep+"tasks.json"
GAME_LOGS_FILE = module_dir+os.sep+"game_logs.json"  # ✅ ملف جديد لتسجيل نتائج الألعاب

# قراءة الإعدادات من ملف settings.json
with open(module_dir + os.sep + 'settings.json', encoding='utf-8') as f:
    SETTINGS = json.load(f)

_file_lock = threading.Lock()

# تهيئة Flask
app = Flask(__name__)
CORS(app)  # تمكين CORS

def write_json_atomic(path, data):
    """اكتب JSON بطريقة أتمتة آمنة (كتابة إلى ملف مؤقت ثم استبدال)."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir='.', prefix='tmp_', text=True)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

def notify_admin(text):
    """أرسل رسالة للأدمن عبر Telegram API إن كان BOT_TOKEN معرفًا، وإلا سجلها في لوج."""
    payload = {
        "chat_id": ADMIN_ID,
        "text": text
    }
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        # لو فشل الإرسال، سجله
        with _file_lock:
            with open("admin_notify_fail.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | notify_admin failed: {e}\n{text}\n\n")

def send_message_to_user(user_id, text, parse_mode=None):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": user_id, "text": text}

        if parse_mode:  # لو المستخدم مرر قيمة
            payload["parse_mode"] = parse_mode

        resp = requests.post(url, json=payload, timeout=8)
        if resp.ok:
            logger.info(f"Message sent successfully to user {user_id}")
            return True
        else:
            error_msg = (
                f"Failed to send message to user {user_id}. "
                f"Status: {resp.status_code}, Response: {resp.text}"
            )
            logger.error(error_msg)
            # تسجيل الخطأ في ملف منفصل لسهولة الوصول
            with _file_lock:
                with open("send_message_fail.log", "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now().isoformat()} | {error_msg}\n")
            return False
    except Exception as e:
        error_msg = f"Exception while sending message to user {user_id}: {e}"
        logger.error(error_msg)
        with _file_lock:
            with open("send_message_fail.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | {error_msg}\n")
        return False

def send_message_to_user_with_reply_markup(user_id, text, reply_markup):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": user_id,
            "text": text,
            "reply_markup": reply_markup.to_dict()
        }
        resp = requests.post(url, json=payload, timeout=8)
        if resp.ok:
            logger.info(f"Message with button sent successfully to user {user_id}")
            return True
        else:
            error_msg = f"Failed to send message with button to user {user_id}. Status: {resp.status_code}, Response: {resp.text}"
            logger.error(error_msg)
            return False
    except Exception as e:
        error_msg = f"Exception while sending message with button to user {user_id}: {e}"
        logger.error(error_msg)
        return False

# قاعدة البيانات
def init_db():
    conn = sqlite3.connect(module_dir+os.sep+'bot.db', check_same_thread=False)
    cursor = conn.cursor()
com # جدول المستخدمين
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        balance REAL DEFAULT 0,
        invites INTEGER DEFAULT 0,
        ads_watched_today INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        points INTEGER DEFAULT 0,
        is_admin BOOLEAN DEFAULT FALSE,
        banned BOOLEAN DEFAULT FALSE,
        last_ad_watch DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # جدول الإحالات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        reward_claimed BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (referrer_id) REFERENCES users (id),
        FOREIGN KEY (referred_id) REFERENCES users (id)
    )
    ''')

    # جدول عمليات السحب
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        method TEXT,
        address TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # جدول طلبات الشراكة
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS partnership_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        channel_name TEXT,
        channel_link TEXT,
        channel_description TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # إضافة مستخدم مسؤول إذا لم يكن موجودًا
    cursor.execute("SELECT * FROM users WHERE id = 6434711549")
    admin = cursor.fetchone()
    if not admin:
        cursor.execute(
            "INSERT INTO users (id, username, first_name, balance, is_admin) VALUES (?, ?, ?, ?, ?)",
            (6434711549, "admin", "Admin", 1000, True)
        )

    conn.commit()
    conn.close()

init_db()

# وظائف قاعدة البيانات
def get_db_connection():
    conn = sqlite3.connect(module_dir+os.sep+'bot.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def update_user(user_id, **kwargs):
    conn = get_db_connection()
    cursor = conn.cursor()

    set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values())
    values.append(user_id)

    cursor.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, last_name=None, invitor=None):
    with open(module_dir+os.sep+'temp_users.json',encoding='utf-8') as f :
        temp_users = json.loads(f.read())

    try:
        temp_users.pop(str(user_id))
    except:None

    with open(module_dir+os.sep+'temp_users.json','w',encoding='utf-8') as f :
        f.write( json.dumps(temp_users,ensure_ascii=False) )

    # ✅ تسجيل الإحالة في referrals.json إذا وجد داعٍ
    if invitor:
        invitor = int(invitor)
        referrer = get_user(invitor)
        if referrer and referrer['id'] != user_id:  # ✅ تصحيح الشرط هنا
            # منح المكافأة
            new_balance = referrer['balance'] + 3
            new_invites = referrer['invites'] + 1
            update_user(invitor, balance=new_balance, invites=new_invites)

            # ✅ تسجيل الإحالة في referrals.json
            referrals_file = module_dir + os.sep + 'referrals.json'
            referrals_data = {}
            if os.path.exists(referrals_file):
                with open(referrals_file, 'r', encoding='utf-8') as f:
                    referrals_data = json.load(f)

            # إضافة ID المستخدم الجديد إلى قائمة المدعوين للداعي
            if str(invitor) not in referrals_data:
                referrals_data[str(invitor)] = []
            referrals_data[str(invitor)].append(user_id)

            # حفظ الملف
            with open(referrals_file, 'w', encoding='utf-8') as f:
                json.dump(referrals_data, f, ensure_ascii=False, indent=2)

            # إخطار الأدمن
            notify_admin(f"Referral applied: referrer={invitor} got +3 CMD (new_balance={new_balance})")

    conn = get_db_connection()
    cursor = conn.cursor()

    # التحقق إذا كان المستخدم موجودًا بالفعل
    existing_user = cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not existing_user:
        cursor.execute(
            "INSERT INTO users (id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, last_name)
        )
        conn.commit()

    conn.close()

def add_user_temp(user_id, username, first_name, last_name=None, invitor=None):
    with open(module_dir+os.sep+'temp_users.json',encoding='utf-8') as f :
        temp_users = json.loads(f.read())
    temp_users[str(user_id)] = [username, first_name, last_name, invitor]
    with open(module_dir+os.sep+'temp_users.json','w',encoding='utf-8') as f :
        f.write( json.dumps(temp_users,ensure_ascii=False) )

with open(module_dir+os.sep+'index.html', encoding='utf-8') as f:
    index_html = f.read()
with open(module_dir+os.sep+'admin.html', encoding='utf-8') as f:
    admin_html = f.read()
with open(module_dir+os.sep+'style.css', encoding='utf-8') as f:
    style_file = f.read()
with open(module_dir+os.sep+'script.js', encoding='utf-8') as f:
    script_file = f.read()

@app.route('/', methods=['GET'])
def index ():
    return index_html

@app.route('/style.css')
def style():
    return style_file, 200, {'Content-Type': 'text/css; charset=utf-8'}

# ملف JavaScript
@app.route('/script.js')
def script():
    return script_file, 200, {'Content-Type': 'application/javascript; charset=utf-8'}

# ملف JSON
@app.route('/settings')
def data():
    with open(module_dir+os.sep+'settings.json', encoding='utf-8') as f:
        settings_file = f.read()
    return settings_file, 200, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/admin/panel', methods=['GET'])
def admin ():
    if request.args.get('key') != KEY:
        return '',404
    return admin_html

def query_db(query, args=(), one=False):
    con = sqlite3.connect(module_dir+os.sep+"bot.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    con.commit()
    con.close()
    return (rv[0] if rv else None) if one else rv

@app.route("/admin/users")
def show_table():
    if request.args.get('key') != KEY:
        return '',404

    name='users'
    rows = query_db(f"SELECT * FROM {name}")
    return render_template_string("""
    <h2>جدول: {{name}}</h2>
    <table border="1" cellpadding="5">
      <tr>
        {% for col in rows[0].keys() %}
          <th>{{col}}</th>
        {% endfor %}
      </tr>
      {% for row in rows %}
        <tr>
          {% for col in row.keys() %}
            <td>{{row[col]}}</td>
          {% endfor %}
        </tr>
      {% endfor %}
    </table>
    """, name=name, rows=rows)

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """
    نقطة النهاية التي يستدعيها Telegram عند وصول تحديث (update).
    تضمن:
      - تسجيل المستخدم إذا كان جديداً (add_user)
      - إذا جديد وكان /start مع ref... تمنح مكافأة للداعي (بدون تخزين referral)
      - إرسال رد موحّد للمستخدم
    """
    update = request.get_json(force=True)
    if not update:
        return '', 200

    # نأخذ الرسالة (قد تكون message أو edited_message)
    msg = update.get('message') or update.get('edited_message')
    if not msg:
        return '', 200

    if msg.get('text', '') == 'debug_bot' :
        chat_id = request.json.get("message", {}).get("chat", {}).get("id") or request.json.get("message", {}).get("from", {}).get("id")
        send_message_to_user(int(chat_id), str(update))
        return '',200

    user = msg.get('from')
    if not user:
        return '', 200

    user_id = int(user['id'])
    username = user.get('username')
    first_name = user.get('first_name')
    last_name = user.get('last_name')
    text = msg.get('text', '') or ''

    '''if not(is_user_in_required_channels(user_id)):
        reply_text = (
            "الرجاء الإشتراك في القنوات التالية لأستخدام البوت :\n\n"
            "https://t.me/COMMANDO_CRYPTO\n"
            "https://t.me/Commandotr\n"
            "https://t.me/Commandoforex\n"
            "https://t.me/Commando_chat\n"
        )
        send_message_to_user(user_id, reply_text)
        return '',200'''

    # هل المستخدم مسجل أصلاً؟
    existing = get_user(user_id)  # يجب أن ترجع None إذا غير موجود

    # إذا غير موجود نسجّله (مرة واحدة)
    is_new_user = False
    if not existing:
        is_new_user = True
        invitor = None
        # حالات ممكنة: "/start", "/start ref123", "/startref123" (نأخذ الاحتمال الأول)
        if is_new_user and text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith('ref'):
                try:
                    referral_id = int(parts[1][3:])
                    invitor = int(referral_id)
                except ValueError:
                    pass  # باراميتر الإحالة لم يكن رقماً صالحاً — نتجاهل
        add_user_temp(user_id, username, first_name, last_name=last_name, invitor=invitor)

    if (text == '/admin') and (user_id == ADMIN_ID):
        reply_text = f"لوحة التحكم :\nhttps://cmd-pearl.vercel.app/admin/panel?key={KEY}\nقاعدة البيانات :\nhttps://cmd-pearl.vercel.app/admin/users?key={KEY}"
        send_message_to_user(user_id, reply_text)
    else:
        # ✅ إرسال زر Web App للمستخدم دائمًا
        web_app_url = "https://cmd-pearl.vercel.app"  # استبدل برابطك
        keyboard = [
            [
                InlineKeyboardButton(
                    text="🚀 افتح التطبيق",
                    web_app=WebAppInfo(url=web_app_url)
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        reply_text = (
            "مرحباً بك في COMMANDO! ✨\n"
            "الرجاء الاشتراك في القنوات أدناه لتفعيل حسابك والبدء في الربح.\n"
            "اضغط على الزر لفتح التطبيق:"
        )
        send_message_to_user_with_reply_markup(user_id, reply_text, reply_markup)
        return '', 200

    return '', 200

@app.route('/api/get_referrals', methods=['GET', 'POST', 'OPTIONS'])
def api_get_referrals():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        # ✅ دعم كلا الطريقتين: GET و POST مع معالجة البيانات بشكل مرن
        if request.method == 'POST':
            if request.is_json:
                data = request.get_json()
            else:
                # حاول قراءة البيانات كـ form data أو حتى من query string
                data = request.form.to_dict() or {}
                if not data:
                    # إذا فشل كل شيء، اقرأ من query string
                    data = {'userId': request.args.get('user_id') or request.args.get('userId')}
        else:  # GET
            data = {'userId': request.args.get('user_id') or request.args.get('userId')}

        user_id = data.get('userId')
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID is required'})

        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        # ✅ قراءة ملف referrals.json
        referrals_file = module_dir + os.sep + 'referrals.json'
        if not os.path.exists(referrals_file):
            return jsonify({'success': True, 'referrals': []})

        with open(referrals_file, 'r', encoding='utf-8') as f:
            referrals_data = json.load(f)

        # ✅ جلب قائمة IDs للمدعوين بواسطة هذا المستخدم
        referred_ids = referrals_data.get(str(user_id), [])

        if not referred_ids:
            return jsonify({'success': True, 'referrals': []})

        # ✅ جلب بيانات المستخدمين من قاعدة البيانات
        conn = get_db_connection()
        placeholders = ','.join('?' * len(referred_ids))
        query = f'SELECT id, username, first_name FROM users WHERE id IN ({placeholders})'
        referred_users = conn.execute(query, referred_ids).fetchall()
        conn.close()

        # ✅ إنشاء القائمة النهائية
        referrals_list = []
        for ref in referred_users:
            referrals_list.append({
                'id': ref['id'],
                'username': ref['username'] or '---'
            })

        return jsonify({
            'success': True,
            'referrals': referrals_list
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/user-data', methods=['POST', 'OPTIONS'])
def api_user_data():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        user_id = data.get('userId')

        if not user_id:
            return jsonify({'success': False, 'error': 'User ID is required'})

        user = get_user(user_id)
        if not user:
            with open(module_dir+os.sep+'temp_users.json',encoding='utf-8') as f :
                temp_users = json.loads(f.read())
            if str(user_id) in temp_users:
                add_user(int(user_id), temp_users[str(user_id)][0], temp_users[str(user_id)][1], last_name=temp_users[str(user_id)][2], invitor=temp_users[str(user_id)][3])
                user = get_user(user_id)
            else:
                return jsonify({'success': False, 'error': 'User not found'})

        # ✅ التحقق من الاشتراك في القنوات الإجبارية
        is_subscribed = is_user_in_required_channels(str(user_id))

        # ✅ إضافة الحقل في الرد
        user_data = {
            'id': user['id'],
            'username': user['username'],
            'first_name': user['first_name'],
            'balance': user['balance'],
            'invites': user['invites'],
            'adsWatchedToday': user['ads_watched_today'],
            'level': user['level'],
            'points': user['points'],
            'isAdmin': bool(user['is_admin']),
            'isSubscribed': is_subscribed  # ✅ هذا الحقل الجديد
        }

        return jsonify({
            'success': True,
            'user': user_data,
            'min_withdrawal': SETTINGS['MIN_WITHDRAWAL']  # ✅ تم الإضافة
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/process-referral', methods=['POST', 'OPTIONS'])
def api_process_referral():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        user_id = data.get('userId')
        referral_id = data.get('referralId')

        if not user_id or not referral_id:
            return jsonify({'success': False, 'error': 'User ID and Referral ID are required'})

        # فقط نمنح مكافأة للداعي (إذا وجد)
        referrer = get_user(referral_id)
        if referrer:
            new_balance = referrer['balance'] + 3
            new_invites = referrer['invites'] + 1
            update_user(referral_id, balance=new_balance, invites=new_invites)
            # نُعلِم الأدمن (اختياري)
            notify_admin(f"Referral processed (no DB record): referrer={referral_id} got +3 CMD (new_balance={new_balance})")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Referrer not found'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
        
        @app.route('/watch_ad', methods=['POST'])
def watch_ad():
    if not request.headers.get("X-Telegram-Bot-Token") == os.getenv("BOT_TOKEN"):
        return jsonify({"error": "غير مصرح لك باستخدام هذه الخدمة"}), 403

@app.route('/api/watch-ad', strict_slashes=False, methods=['GET'])
@app.route('/api/watch-ad/', strict_slashes=False, methods=['GET'])
def api_watch_ad():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        user_id = request.args.get('telegram_id')

        if not user_id:
            return '',200

        user = get_user(user_id)
        if not user:
            return '',200
            
            requests.post("https://commandobot.pythonanywhere.com/watch_ad", headers={"X-Telegram-Bot-Token": BOT_TOKEN})

        # تحديث بيانات المستخدم - فقط 0.20 نقطة لكل إعلان
        new_balance = user['balance'] + 0.05
        new_ads_today = user['ads_watched_today'] + 1
        new_points = user['points'] + 1

        # التحقق من الترقية في المستوى (كل 100 نقطة)
        new_level = user['level']
        if new_points >= new_level * 100:
            new_level += 1

if user_ads_today >= 50:
    return jsonify({"error": "تجاوزت الحد اليومي للإعلانات"})

        update_user(
            user_id,
            balance=new_balance,
            ads_watched_today=new_ads_today,
            points=new_points,
            level=new_level,
            last_ad_watch=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

        return '',200

    except Exception as e:
        return '',400

@app.route('/api/leaderboard', methods=['GET', 'OPTIONS'])
def api_leaderboard():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        if not os.path.exists(LEADERBOARD_FILE):
            return jsonify({'success': True, 'leaderboard': []})  # أو رسالة تفيد بعدم وجود بيانات

        with _file_lock:
            with open(LEADERBOARD_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

        return jsonify({'success': True, 'leaderboard': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-subscription', methods=['POST', 'OPTIONS'])
def api_verify_subscription():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        user_id = data.get('userId')
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID is required'})

        # التحقق من الاشتراك في القنوات
        is_subscribed = is_user_in_required_channels(str(user_id))

        if is_subscribed:
            return jsonify({'success': True, 'message': 'Subscription verified'})
        else:
            return jsonify({'success': False, 'error': 'User is not subscribed to all required channels'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/withdraw_accept', methods=['GET','POST', 'OPTIONS'])
def api_withdraw_accept():
    try:
        user_id = request.args.get('userId')
        amount = int(request.args.get('amount'))

        if not all([user_id,amount]):
            return '<h2>Missing required fields</h2>'

        user = get_user(user_id)
        if not user:
            return '<h2>User not found</h2>'

        if user['balance'] < amount:
            return f"<h2>الرصيد اقل من المطلوب سحبه</h2><br><p>الرصيد : {user['balance']}</p>"

        # ✅ الخصم الفوري من رصيد المستخدم
        new_balance = abs(int(user['balance'] - amount))
        update_user(user_id, balance=new_balance)

        return f"<h2>Done , New Balance : {new_balance}</h>"
    except Exception as e:
        return '<h2>' + str(e) + '</h2>'

@app.route('/api/withdraw', methods=['POST', 'OPTIONS'])
def api_withdraw():
    if request.method == 'OPTIONS':
        return '', 200

    #return jsonify({'success': False, 'error': 'السحب متوقف اليوم'})
    try:
        data = request.get_json()
        user_id = data.get('userId')
        amount = data.get('amount')
        method = data.get('method')
        address = data.get('address')

        if not all([user_id, amount, method, address]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        amount = float(amount)  # ✅ تحويل إلى رقم مرة واحدة لاستخدامه لاحقًا

        if user['balance'] < amount:
            return jsonify({'success': False, 'error': 'Insufficient balance'})

        if amount < SETTINGS.get('MIN_WITHDRAWAL'):
            return jsonify({'success': False, 'error': f'Minimum withdrawal is {SETTINGS.get("MIN_WITHDRAWAL")} CMD'})

        # ✅ الخصم الفوري من رصيد المستخدم
        new_balance = user['balance']
        # new_balance = user['balance'] - amount
        # update_user(user_id, balance=new_balance)

        # سجّل السحب في ملف نصي كسطر واحد
        line = f"{datetime.now().isoformat()} | user_id {user_id} withdraw {amount} CMD ({method}) to {address}\n"
        with _file_lock:
            with open(WITHDRAW_LOG, "a", encoding='utf-8') as f:
                f.write(line)

        # أرسل إشعارًا للأدمن مع كل التفاصيل
        send_message_to_user(-1002979951308, f"Withdrawal request:\nUser: <a href=\"tg://user?id={user_id}\">{user_id}</a> ({user['username']})\nAmount: {amount} CMD\nMethod: {method}\nAddress: {address}\nTime: {datetime.now().isoformat()}\nNew Balance: {new_balance} CMD\nAccept : https://commandomaney.pythonanywhere.com/api/withdraw_accept?userId={user_id}&amount={int(amount)}", parse_mode="HTML")

        return jsonify({
            'success': True,
            'message': 'تم السحب تواصل مع الادمن لاتمام العملية , سيتم خصم المبلغ من حسابك لاحقا',
            'new_balance': new_balance  # ✅ إرجاع الرصيد الجديد للمستخدم
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def generate_leaderboard_json(limit=10):
    """اجمع المتصدرين من DB واكتبهم في ملف JSON (LEADERBOARD_FILE)."""
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT id, username, first_name, balance FROM users WHERE banned = 0 ORDER BY balance DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()

    lb = []
    for u in rows:
        lb.append({
            'id': u['id'],
            'username': u['username'],
            'first_name': u['first_name'],
            'balance': u['balance']
        })

    with _file_lock:
        write_json_atomic(LEADERBOARD_FILE, lb)

@app.route('/api/admin/generate-leaderboard', methods=['POST', 'OPTIONS'])
def api_admin_generate_leaderboard():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json() or {}
        admin_id = data.get('admin_id')
        if not admin_id:
            return jsonify({'success': False, 'error': 'Admin ID is required'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        # شغّل التجميع في thread حتى لا يوقف الطلب
        threading.Thread(target=generate_leaderboard_json, daemon=True).start()
        return jsonify({'success': True, 'message': 'Leaderboard generation started'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# APIs خاصة بالإدارة
@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
def api_admin_users():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        admin_id = request.args.get('admin_id')
        if not admin_id:
            return jsonify({'success': False, 'error': 'Admin ID is required'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        conn = get_db_connection()
        users = conn.execute('SELECT * FROM users').fetchall()

        users_data = []
        for user in users:
            users_data.append({
                'id': user['id'],
                'username': user['username'],
                'first_name': user['first_name'],
                'balance': user['balance'],
                'invites': user['invites'],
                'level': user['level'],
                'points': user['points'],
                'is_admin': bool(user['is_admin']),
                'banned': bool(user['banned']),
                'created_at': user['created_at']
            })

        conn.close()
        return jsonify({'success': True, 'users': users_data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/user-info', methods=['POST', 'OPTIONS'])
def api_admin_user_info():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        user_id = data.get('user_id')

        if not all([admin_id, user_id]):
            return jsonify({'success': False, 'error': 'Admin ID and User ID are required'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        user_info = {
            'id': user['id'],
            'username': user['username'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'balance': user['balance'],
            'invites': user['invites'],
            'ads_watched_today': user['ads_watched_today'],
            'level': user['level'],
            'points': user['points'],
            'is_admin': bool(user['is_admin']),
            'banned': bool(user['banned']),
            'last_ad_watch': user['last_ad_watch'],
            'created_at': user['created_at']
        }

        return jsonify({'success': True, 'user': user_info})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/update-user', methods=['POST', 'OPTIONS'])
def api_admin_update_user():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        user_id = data.get('user_id')
        field = data.get('field')
        value = data.get('value')

        if admin_id is None or user_id is None or field is None or value is None:
            return jsonify({'success': False, 'error': 'Missing required fields'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        # تحديث حقل المستخدم
        update_user(user_id, **{field: value})

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/send-broadcast', methods=['POST', 'OPTIONS'])
def api_admin_send_broadcast():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        message = data.get('message')

        if not all([admin_id, message]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        # احصل على كل المستخدمين
        conn = get_db_connection()
        users = conn.execute('SELECT id FROM users').fetchall()
        conn.close()

        user_ids = [u['id'] for u in users]

        def send_broadcast(ids, text):
            success = 0
            failed = 0
            for uid in ids:
                try:
                    ok = send_message_to_user(uid, text)
                    if ok:
                        success += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            # بعد الانتهاء أُعلِم الأدمن بالنتيجة
            notify_admin(f"Broadcast finished: success={success}, failed={failed}, total={len(ids)}")

        threading.Thread(target=send_broadcast, args=(user_ids, message), daemon=True).start()

        return jsonify({'success': True, 'message': 'Broadcast started'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
def api_admin_stats():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        admin_id = request.args.get('admin_id')
        if not admin_id:
            return jsonify({'success': False, 'error': 'Admin ID is required'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        conn = get_db_connection()

        # إحصائيات المستخدمين
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        active_today = conn.execute('SELECT COUNT(*) FROM users WHERE last_ad_watch >= date("now")').fetchone()[0]
        total_invites = conn.execute('SELECT SUM(invites) FROM users').fetchone()[0] or 0
        total_withdrawals = conn.execute('SELECT SUM(amount) FROM withdrawals WHERE status = "completed"').fetchone()[0] or 0

        # الإحصائيات اليومية
        today_start = datetime.now().strftime('%Y-%m-%d 00:00:00')
        today_ads = conn.execute('SELECT SUM(ads_watched_today) FROM users').fetchone()[0] or 0
        today_signups = conn.execute('SELECT COUNT(*) FROM users WHERE created_at >= ?', (today_start,)).fetchone()[0]

        # الإحصائيات المالية
        total_balance = conn.execute('SELECT SUM(balance) FROM users').fetchone()[0] or 0

        conn.close()

        stats = {
            'total_users': total_users,
            'active_today': active_today,
            'total_invites': total_invites,
            'total_withdrawals': total_withdrawals,
            'today_ads': today_ads,
            'today_signups': today_signups,
            'total_balance': total_balance
        }

        return jsonify({'success': True, 'stats': stats})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/partnership-request', methods=['POST', 'OPTIONS'])
def api_partnership_request():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        channel_name = data.get('channel_name')
        channel_link = data.get('channel_link')
        channel_description = data.get('channel_description')

        if not all([user_id, channel_name, channel_link]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        # سجل في ملف لوق كسطر واحد
        line = f"{datetime.now().isoformat()} | partnership_request by {user_id} | {channel_name} | {channel_link} | {channel_description}\n"
        with _file_lock:
            with open(PARTNERSHIP_LOG, "a", encoding='utf-8') as f:
                f.write(line)

        # أرسل للأدمن
        notify_admin(f"New partnership request:\nUser: {user_id}\nChannel: {channel_name}\nLink: {channel_link}\nDesc: {channel_description}")

        return jsonify({'success': True, 'message': 'Partnership request sent to admin (no DB record).'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/partnership-requests', methods=['GET', 'OPTIONS'])
def api_admin_partnership_requests():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        admin_id = request.args.get('admin_id')
        if not admin_id:
            return jsonify({'success': False, 'error': 'Admin ID is required'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        conn = get_db_connection()
        requests = conn.execute(
            'SELECT pr.*, u.username, u.first_name FROM partnership_requests pr JOIN users u ON pr.user_id = u.id ORDER BY pr.created_at DESC'
        ).fetchall()

        requests_data = []
        for req in requests:
            requests_data.append({
                'id': req['id'],
                'user_id': req['user_id'],
                'username': req['username'],
                'first_name': req['first_name'],
                'channel_name': req['channel_name'],
                'channel_link': req['channel_link'],
                'channel_description': req['channel_description'],
                'status': req['status'],
                'created_at': req['created_at']
            })

        conn.close()
        return jsonify({'success': True, 'requests': requests_data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/update-partnership', methods=['POST', 'OPTIONS'])
def api_admin_update_partnership():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        request_id = data.get('request_id')
        status = data.get('status')

        if not all([admin_id, request_id, status]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        if status not in ['approved', 'rejected']:
            return jsonify({'success': False, 'error': 'Invalid status'})

        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        conn = get_db_connection()

        # تحديث حالة طلب الشراكة
        conn.execute(
            'UPDATE partnership_requests SET status = ? WHERE id = ?',
            (status, request_id)
        )

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': f'Partnership request {status}'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def load_tasks():
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

# حفظ المهام في الملف
def save_tasks(tasks):
    with _file_lock:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

# API: جلب المهام التي لم ينجزها المستخدم
@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "user_id is required"}), 400

    try:
        user_id = int(user_id)  # تحويل إلى عدد صحيح للمقارنة
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id format"}), 400

    tasks = load_tasks()
    # فلترة المهام بحيث يرجع فقط اللي المستخدم ما خلصها
    not_done = [t for t in tasks if user_id not in t.get("completed_by", [])]

    # ✅ حذف حقل completed_by من كل مهمة قبل الإرسال (لحماية الخصوصية)
    for task in not_done:
        if "completed_by" in task:
            del task["completed_by"]

    return jsonify({"success": True, "tasks": not_done})

def is_user_in_channel(user_id: str, channel_url: str) -> bool:
    """
    يتحقق إذا المستخدم عضو في قناة/جروب تليجرام.
    - إذا الرابط بوت → تمر المهمة بدون تحقق.
    - إذا الرابط خارجي → تمر المهمة بدون تحقق.
    - إذا الرابط قناة/جروب → يستخدم getChatMember للتحقق.
    - إذا فشل التحقق بسبب عدم صلاحية البوت → نعتبر المستخدم مشتركًا (لأننا لا نستطيع التحقق).
    """
    if not channel_url.startswith("https://t.me/"):
        return True  # ليس رابط تليجرام

    # ✅ استخراج اسم المستخدم بدون بارامترات
    username = channel_url.split("/")[-1].split('?')[0].strip()

    # إذا الرابط بوت
    if username.lower().endswith("_bot"):
        return True

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        resp = requests.get(url, params={"chat_id": f"@{username}", "user_id": user_id}, timeout=10)
        data = resp.json()

        if data.get("ok"):
            status = data["result"]["status"]
            return status in ["member", "administrator", "creator"]
        else:
            # ✅ إذا فشل التحقق (مثلاً: البوت ليس مشرفًا) → نعتبر المستخدم مشتركًا
            # لأننا لا نستطيع التحقق، والأفضل السماح له بالمرور
            logger.warning(f"Could not verify membership in {username}: {data.get('description', 'Unknown error')}")
            return True

    except Exception as e:
        # ✅ أي خطأ في الشبكة أو التحقق → نعتبر المستخدم مشتركًا
        logger.error(f"Error verifying membership in {username}: {e}")
        return True

def is_user_in_required_channels(user_id: str) -> bool:
    """
    يتحقق إذا كان المستخدم مشتركًا في جميع القنوات/المجموعات الإجبارية من settings.json.
    """
    required_channels = SETTINGS.get("REQUIRED_CHANNELS", [])
    for channel in required_channels:
        channel_url = channel.get("url", "")
        if not is_user_in_channel(user_id, channel_url):
            return False
    return True

import json
import os
from datetime import datetime

def audit_referrals_and_penalize():
    send_message_to_user(-1002894165549,"Referral Audit Penalty Started")
    """
    تفحص جميع المستخدمين المسجلين كمدعوين.
    إذا كان مستخدم غير مشترك في القنوات الإجبارية ولم يتم معاقبة الداعي بسببه من قبل،
    يتم معاقبة الداعي بخصم 1 من invites و 3 من balance.
    """
    logger.info("Starting referral audit and penalty process...")
    referrals_file = module_dir + os.sep + 'referrals.json'
    penalties_log_file = module_dir + os.sep + 'penalties_log.json'  # ✅ ملف السجل الجديد

    # تحميل سجل العقوبات الحالي (إن وجد)
    penalties_log = {}
    if os.path.exists(penalties_log_file):
        try:
            with open(penalties_log_file, 'r', encoding='utf-8') as f:
                penalties_log = json.load(f)
        except json.JSONDecodeError:
            penalties_log = {}

    if not os.path.exists(referrals_file):
        logger.info("No referrals found. Audit completed.")
        return

    with open(referrals_file, 'r', encoding='utf-8') as f:
        referrals_data = json.load(f)

    penalties_to_apply = []

    for referrer_id_str, referred_ids in referrals_data.items():
        referrer_id = int(referrer_id_str)
        for referred_id in referred_ids:
            # ✅ التحقق: هل تم تطبيق عقوبة على هذا الزوج (referrer, referred) من قبل؟
            penalty_key = f"{referrer_id}_{referred_id}"
            if penalty_key in penalties_log:
                logger.info(f"Penalty already applied for referrer {referrer_id} due to referred {referred_id}. Skipping.")
                continue

            # تحقق من اشتراك المدعو
            if not is_user_in_required_channels(str(referred_id)):
                logger.info(f"User {referred_id} is NOT subscribed to required channels. Penalizing referrer {referrer_id}.")
                penalties_to_apply.append((referrer_id, referred_id, penalty_key))

    # تطبيق العقوبات وتسجيلها
    for referrer_id, referred_id, penalty_key in penalties_to_apply:
        referrer = get_user(referrer_id)
        if referrer:
            new_invites = max(0, referrer['invites'] - 1)
            new_balance = max(0, referrer['balance'] - 3)
            update_user(referrer_id, invites=new_invites, balance=new_balance)
            logger.info(f"Penalty applied: referrer {referrer_id} -> invites: {new_invites}, balance: {new_balance}")

            # ✅ تسجيل العقوبة في السجل لمنع التكرار
            penalties_log[penalty_key] = {
                'referrer_id': referrer_id,
                'referred_id': referred_id,
                'penalty_applied_at': datetime.now().isoformat(),
                'action': 'deducted 1 invite and 3 CMD'
            }

            # إرسال إشعار للأدمن
            send_message_to_user(-1002894165549,f"Referral Audit Penalty:\nReferrer: {referrer_id} ({referrer['username']})\nReferred User (Not Subscribed): {referred_id}\nAction: -1 invite, -3 CMD\nNew Balance: {new_balance} CMD")
            try:
                ddd = get_user(referred_id)
                if not(ddd['username'] in [None,'None']):
                    send_message_to_user(int(referrer_id), f"لقد تم حذف 3 نقاط بسبب خروج {ddd['username']} من قنوات الاشتراك الاجباري 💔.")
                else:
                    send_message_to_user(int(referrer_id), f"لقد تم حذف 3 نقاط بسبب خروج {referred_id} من قنوات الاشتراك الاجباري 💔.")
            except:None
            time.sleep(1.5)

    # ✅ حفظ سجل العقوبات المحدث
    with open(penalties_log_file, 'w', encoding='utf-8') as f:
        json.dump(penalties_log, f, ensure_ascii=False, indent=2)

    logger.info("Referral audit and penalty process completed.")
    send_message_to_user(-1002894165549,"Referral Audit Penalty Ended")

@app.route('/api/verify-channel', methods=['POST', 'OPTIONS'])
def api_verify_channel():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        # ✅ التعامل مع JSON بشكل آمن
        if request.is_json:
            data = request.get_json()
        else:
            # إذا لم يكن JSON، نحاول من form أو query string
            data = request.form.to_dict() or request.args.to_dict()

        user_id = data.get('userId') or data.get('user_id')
        channel_url = data.get('channelUrl') or data.get('channel_url')

        if not user_id or not channel_url:
            return jsonify({'success': False, 'error': 'User ID and Channel URL are required'})

        is_subscribed = is_user_in_channel(str(user_id), channel_url)

        if is_subscribed:
            return jsonify({'success': True, 'message': 'Subscription verified'})
        else:
            return jsonify({'success': False, 'error': 'User is not subscribed to this channel'})

    except Exception as e:
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'})

# API: تأكيد إكمال مهمة
@app.route("/api/tasks/complete", methods=["POST"])
def complete_task():
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    task_id = data.get("task_id")

    if not all([user_id, task_id]):
        return jsonify({"success": False, "error": "user_id and task_id are required"}), 400

    tasks = load_tasks()
    task = next((t for t in tasks if str(t["id"]) == str(task_id)), None)
    if not task:
        return jsonify({"success": False, "error": "Task not found"}), 404

    if user_id in task.get("completed_by", []):
        return jsonify({"success": False, "error": "Task already completed"}), 400

    channel_url = task["channel"]

    # ✅ التحقق: هل الرابط هو قناة/جروب تليجرام حقيقي (ليس بوت ولا رابط خارجي)؟
    if channel_url.startswith("https://t.me/"):
        username = channel_url.split("/")[-1].split('?')[0]

        # ✅ إذا كان اسم المستخدم ينتهي بـ "_bot" → فهو بوت → لا نتحقق
        if username.lower().endswith("bot"):
            pass  # تجاوز التحقق
        else:
            # ✅ إذا لم يكن بوتًا → نتحقق من الاشتراك
            if not is_user_in_channel(user_id, channel_url):
                return jsonify({"success": False, "error": "User is not a member of the required channel"}), 400
    else:
        # ✅ إذا لم يكن رابط تليجرام أصلاً (مثلاً: موقع خارجي) → تجاوز التحقق
        pass

    # سجل إنجاز المهمة
    task.setdefault("completed_by", []).append(user_id)
    save_tasks(tasks)

    # ✅ منح المكافأة للمستخدم في قاعدة البيانات
    user = get_user(user_id)
    if user:
        new_balance = user['balance'] + task["reward"]
        update_user(user_id, balance=new_balance)

    return jsonify({
        "success": True,
        "message": "Task completed successfully",
        "reward": task["reward"]
    })

# مثال: إنشاء مهمة جديدة (للاستخدام اليدوي أو من لوحة أدمن)
@app.route("/api/tasks/create", methods=["POST"])
def create_task():
    data = request.get_json(force=True)
    title = data.get("title")
    description = data.get("description")
    reward = data.get("reward")
    channel = data.get("channel")

    if not all([title, description, reward, channel]):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    tasks = load_tasks()
    new_id = max([t["id"] for t in tasks], default=0) + 1
    new_task = {
        "id": new_id,
        "title": title,
        "description": description,
        "reward": reward,
        "channel": channel,
        "completed_by": []
    }
    tasks.append(new_task)
    save_tasks(tasks)

    return jsonify({"success": True, "task": new_task})

@app.route('/api/admin/update-settings', methods=['POST', 'OPTIONS'])
def api_admin_update_settings():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        if not admin_id:
            return jsonify({'success': False, 'error': 'Admin ID is required'})
        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        # ✅ التحقق من القنوات الإجبارية
        required_channels = data.get('REQUIRED_CHANNELS', [])
        if not isinstance(required_channels, list) or len(required_channels) == 0:
            return jsonify({'success': False, 'error': 'Invalid REQUIRED_CHANNELS'})

        # ✅ التحقق من كل قناة
        for channel in required_channels:
            if not all(key in channel for key in ['url', 'title']):
                return jsonify({'success': False, 'error': 'Each channel must have url and title'})

        # التحقق من البيانات الأخرى (كما كانت)
        min_withdrawal = data.get('MIN_WITHDRAWAL')
        payment_methods = data.get('PAYMENT_METHODS', [])
        if min_withdrawal is None or min_withdrawal <= 0:
            return jsonify({'success': False, 'error': 'Invalid MIN_WITHDRAWAL value'})
        if not isinstance(payment_methods, list) or len(payment_methods) == 0:
            return jsonify({'success': False, 'error': 'Invalid PAYMENT_METHODS'})
        for method in payment_methods:
            if not all(key in method for key in ['id', 'name', 'icon', 'category']):
                return jsonify({'success': False, 'error': 'Each payment method must have id, name, icon, and category'})

        # بناء كائن الإعدادات الجديد
        new_settings = {
            'MIN_WITHDRAWAL': min_withdrawal,
            'REQUIRED_CHANNELS': required_channels,  # ✅ تم الإضافة
            'PAYMENT_METHODS': payment_methods
        }

        # حفظ الإعدادات في ملف settings.json
        settings_file = module_dir + os.sep + 'settings.json'
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(new_settings, f, ensure_ascii=False, indent=2)

        # تحديث المتغير العام SETTINGS
        global SETTINGS
        SETTINGS = new_settings

        # إشعار الأدمن
        notify_admin(f"Admin {admin_id} updated system settings.")
        return jsonify({'success': True, 'message': 'Settings updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/delete-task', methods=['POST', 'OPTIONS'])
def api_admin_delete_task():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        task_id = data.get('task_id')
        if not admin_id or not task_id:
            return jsonify({'success': False, 'error': 'Admin ID and Task ID are required'})
        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})
        # تحميل المهام الحالية
        tasks = load_tasks()
        # البحث عن المهمة المراد حذفها
        task_to_delete = None
        for task in tasks:
            if task.get('id') == task_id:
                task_to_delete = task
                break
        if not task_to_delete:
            return jsonify({'success': False, 'error': 'Task not found'})
        # حذف المهمة من القائمة
        tasks = [task for task in tasks if task.get('id') != task_id]
        # حفظ القائمة المعدلة
        save_tasks(tasks)
        # إشعار الأدمن
        notify_admin(f"Admin {admin_id} deleted task ID {task_id}.")
        return jsonify({'success': True, 'message': f'Task {task_id} deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/trigger-audit', methods=['POST', 'OPTIONS'])
def api_admin_trigger_audit():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json() or {}
        admin_id = data.get('admin_id')
        if not admin_id:
            return jsonify({'success': False, 'error': 'Admin ID is required'})
        admin = get_user(admin_id)
        if not admin or not admin['is_admin']:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        # شغّل عملية التدقيق في thread حتى لا يوقف الطلب
        threading.Thread(target=audit_referrals_and_penalize, daemon=True).start()
        return jsonify({'success': True, 'message': 'Audit process started successfully. Check admin notifications for results.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ✅ وظائف جديدة للألعاب
def load_game_logs():
    """تحميل سجل نتائج الألعاب من ملف JSON."""
    if not os.path.exists(GAME_LOGS_FILE):
        return {}
    with _file_lock:
        with open(GAME_LOGS_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}

def save_game_logs(game_logs):
    """حفظ سجل نتائج الألعاب إلى ملف JSON."""
    with _file_lock:
        with open(GAME_LOGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(game_logs, f, ensure_ascii=False, indent=2)

# ✅ API جديد لتحديث نتيجة اللعبة
# ✅ API جديد لتحديث نتيجة اللعبة مع حفظ الرصيد
@app.route('/api/game/update-score', methods=['POST', 'OPTIONS'])
def api_game_update_score():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        user_id = data.get('userId')
        game_type = data.get('gameType')  # 'combo' أو غيرها
        score = data.get('score')
        reward = data.get('reward', 0)  # المكافأة الافتراضية 0

        if not all([user_id, game_type, score is not None]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        # ✅ تحديث رصيد المستخدم إذا كان هناك مكافأة
        if reward > 0:
            new_balance = user['balance'] + reward
            update_user(user_id, balance=new_balance)

        # ✅ تسجيل نتيجة اللعبة في ملف game_logs.json
        game_logs = load_game_logs()

        user_key = str(user_id)
        if user_key not in game_logs:
            game_logs[user_key] = {}

        game_logs[user_key][game_type] = {
            'last_play': datetime.now().isoformat(),
            'score': score,
            'reward': reward
        }

        save_game_logs(game_logs)

        return jsonify({
            'success': True,
            'message': 'Game score updated successfully',
            'new_balance': new_balance if reward > 0 else user['balance']
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ✅ API للتحقق من إمكانية اللعب
@app.route('/api/game/can-play', methods=['POST', 'OPTIONS'])
def api_game_can_play():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        user_id = data.get('userId')
        game_type = data.get('gameType')

        if not all([user_id, game_type]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        # تحميل سجل الألعاب
        game_logs = load_game_logs()
        user_key = str(user_id)

        if user_key not in game_logs or game_type not in game_logs[user_key]:
            return jsonify({'success': True, 'canPlay': True, 'timeLeft': 0})

        last_play_str = game_logs[user_key][game_type]['last_play']
        last_play = datetime.fromisoformat(last_play_str)
        now = datetime.now()
        time_since_last_play = now - last_play

        # يمكن اللعب مرة كل 24 ساعة
        can_play = time_since_last_play >= timedelta(hours=24)
        time_left = 0 if can_play else (24 * 3600) - time_since_last_play.total_seconds()

        return jsonify({
            'success': True,
            'canPlay': can_play,
            'timeLeft': time_left
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ✅ API للحصول على أفضل النتائج
@app.route('/api/game/leaderboard', methods=['GET', 'OPTIONS'])
def api_game_leaderboard():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        game_type = request.args.get('gameType', 'combo')  # النوع الافتراضي 'combo'
        limit = int(request.args.get('limit', 10))  # الحد الافتراضي 10

        game_logs = load_game_logs()
        leaderboard = []

        for user_id, games in game_logs.items():
            if game_type in games:
                game_data = games[game_type]
                user = get_user(int(user_id))
                if user:
                    leaderboard.append({
                        'user_id': user_id,
                        'username': user['username'] or 'Unknown',
                        'first_name': user['first_name'],
                        'score': game_data['score'],
                        'last_play': game_data['last_play']
                    })

        # ترتيب النتائج من الأعلى إلى الأقل
        leaderboard.sort(key=lambda x: x['score'], reverse=True)
        leaderboard = leaderboard[:limit]  # تقليل النتائج حسب الحد المطلوب

        return jsonify({
            'success': True,
            'gameType': game_type,
            'leaderboard': leaderboard
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# وظيفة لإعادة تعيين عدد الإعلانات اليومية
def reset_daily_ads():
    while True:
        now = datetime.now()
        # الانتظار حتى منتصف الليل
        next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        time_to_wait = (next_midnight - now).total_seconds()

        time.sleep(time_to_wait)

        # إعادة تعيين عدد الإعلانات اليومية لجميع المستخدمين
        conn = get_db_connection()
        conn.execute('UPDATE users SET ads_watched_today = 0')
        conn.commit()
        conn.close()

        logger.info("Daily ads reset for all users")

# في نهاية الملف، استبدل السطر الأخير بـ:
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
