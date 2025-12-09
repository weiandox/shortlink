from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# 数据库配置 - 支持环境变量
DATABASE = os.environ.get('DATABASE_PATH', '/app/data/shortlinks.db')

# 管理员账户配置 - 支持环境变量
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')


def init_db():
    """初始化数据库"""
    # 确保数据库目录存在
    db_dir = os.path.dirname(DATABASE)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # 创建管理员表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')

    # 创建短链表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shortlinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visits INTEGER DEFAULT 0
        )
    ''')

    # 创建或更新管理员账户
    cursor.execute('SELECT COUNT(*) FROM admin WHERE username = ?', (ADMIN_USERNAME,))
    if cursor.fetchone()[0] == 0:
        # 创建新管理员
        password_hash = generate_password_hash(ADMIN_PASSWORD)
        cursor.execute('INSERT INTO admin (username, password_hash) VALUES (?, ?)',
                       (ADMIN_USERNAME, password_hash))
        print(f"创建管理员账户: {ADMIN_USERNAME}")
    else:
        # 更新现有管理员密码
        password_hash = generate_password_hash(ADMIN_PASSWORD)
        cursor.execute('UPDATE admin SET password_hash = ? WHERE username = ?',
                       (password_hash, ADMIN_USERNAME))
        print(f"更新管理员账户: {ADMIN_USERNAME}")

    conn.commit()
    conn.close()


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def generate_short_key():
    """生成4位随机短链key"""
    chars = string.ascii_lowercase + string.digits  # 26个小写字母 + 10个数字
    while True:
        key = ''.join(random.choice(chars) for _ in range(4))
        # 检查是否已存在
        conn = get_db_connection()
        existing = conn.execute('SELECT COUNT(*) FROM shortlinks WHERE key = ?', (key,)).fetchone()[0]
        conn.close()
        if existing == 0:
            return key


@app.route('/')
def index():
    """首页重定向到管理页面"""
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """管理员登录页面"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admin WHERE username = ?', (username,)).fetchone()
        conn.close()

        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('登录成功！', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('用户名或密码错误！', 'error')

    return render_template('login.html')


@app.route('/admin/logout')
def admin_logout():
    """管理员登出"""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('已退出登录', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin')
def admin_dashboard():
    """管理员仪表板"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    shortlinks = conn.execute('SELECT * FROM shortlinks ORDER BY created_at DESC').fetchall()
    conn.close()

    return render_template('dashboard.html', shortlinks=shortlinks)


@app.route('/admin/add', methods=['POST'])
def add_shortlink():
    """添加新短链"""
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登录'})

    key = request.form.get('key', '').strip()
    url = request.form['url'].strip()

    if not url:
        return jsonify({'success': False, 'message': 'URL不能为空'})

    # 如果没有输入key，则自动生成
    if not key:
        key = generate_short_key()
        auto_generated = True
    else:
        auto_generated = False

    # 确保URL格式正确
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO shortlinks (key, url) VALUES (?, ?)', (key, url))
        conn.commit()
        if auto_generated:
            flash(f'短链添加成功！自动生成key: {key}', 'success')
        else:
            flash(f'短链 {key} 添加成功！', 'success')
        return jsonify({'success': True, 'message': '添加成功', 'key': key, 'auto_generated': auto_generated})
    except sqlite3.IntegrityError:
        if auto_generated:
            # 如果自动生成的key重复（极小概率），重新生成
            return add_shortlink()
        else:
            return jsonify({'success': False, 'message': '该短链key已存在'})
    finally:
        conn.close()


@app.route('/admin/delete/<int:link_id>', methods=['POST'])
def delete_shortlink(link_id):
    """删除短链"""
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db_connection()
    conn.execute('DELETE FROM shortlinks WHERE id = ?', (link_id,))
    conn.commit()
    conn.close()

    flash('短链删除成功！', 'success')
    return jsonify({'success': True, 'message': '删除成功'})


@app.route('/<key>')
def redirect_shortlink(key):
    """短链重定向"""
    conn = get_db_connection()
    shortlink = conn.execute('SELECT * FROM shortlinks WHERE key = ?', (key,)).fetchone()

    if shortlink:
        # 增加访问次数
        conn.execute('UPDATE shortlinks SET visits = visits + 1 WHERE key = ?', (key,))
        conn.commit()
        conn.close()
        return redirect(shortlink['url'])
    else:
        conn.close()
        return '短链不存在', 404


@app.route('/health')
def health_check():
    """健康检查端点"""
    return {'status': 'healthy', 'database': DATABASE}, 200

if __name__ == '__main__':
    # 初始化数据库
    init_db()

    # 获取端口配置
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_ENV') == 'development'

    print(f"启动短链服务...")
    print(f"管理员用户名: {ADMIN_USERNAME}")
    print(f"数据库路径: {DATABASE}")
    print(f"监听地址: {host}:{port}")

    app.run(debug=False, host=host, port=port)

