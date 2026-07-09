from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import requests
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key_change_this')

# -------------------- إعدادات ديسكورد (من البيئة) --------------------
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')
DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')

# -------------------- قاعدة البيانات --------------------
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT,
        discord_tag TEXT,
        avatar TEXT,
        roles TEXT,
        whitelist_status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS whitelist_apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        character_name TEXT,
        backstory TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    conn.commit()
    conn.close()
    print("✅ قاعدة البيانات جاهزة")

init_db()

# -------------------- دوال ديسكورد --------------------
def get_discord_roles(user_id):
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        return []
    url = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{user_id}"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('roles', [])
    except:
        pass
    return []

# -------------------- المصادقة --------------------
@app.route('/login')
def login():
    if not DISCORD_CLIENT_ID:
        return "الرجاء إعداد مفاتيح Discord", 500
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "خطأ في التوثيق", 400

    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post('https://discord.com/api/v10/oauth2/token', data=data, headers=headers)
    if response.status_code != 200:
        return "فشل في الحصول على التوكن", 400

    token_data = response.json()
    access_token = token_data['access_token']
    
    user_response = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {access_token}'})
    user_data = user_response.json()
    
    roles_list = get_discord_roles(user_data['id'])
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (id, username, discord_tag, avatar, roles) VALUES (?, ?, ?, ?, ?)",
              (user_data['id'], user_data['username'], f"{user_data['username']}#{user_data['discriminator']}", user_data['avatar'], str(roles_list)))
    conn.commit()
    conn.close()
    
    session['user_id'] = user_data['id']
    session['username'] = user_data['username']
    session['avatar'] = user_data['avatar']
    session['roles'] = roles_list
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# -------------------- الصفحات --------------------
@app.route('/')
def index():
    target_date = datetime(2026, 7, 31)
    days_left = (target_date - datetime.now()).days
    if days_left < 0: days_left = 0
    return render_template('index.html', days_left=days_left, user=session.get('user_id'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user_data = c.fetchone()
    conn.close()
    return render_template('dashboard.html', user=session, roles=session.get('roles', []))

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        character_name = request.form.get('character_name')
        backstory = request.form.get('backstory')
        user_id = session['user_id']
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("INSERT INTO whitelist_apps (user_id, character_name, backstory) VALUES (?, ?, ?)",
                  (user_id, character_name, backstory))
        conn.commit()
        conn.close()
        return render_template('apply.html', success=True)
    
    return render_template('apply.html', success=False)

# -------------------- تشغيل السيرفر --------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)