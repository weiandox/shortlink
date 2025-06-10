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


def create_templates():
    """创建HTML模板文件"""

    # 登录页面模板
    login_html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>短链系统 - 管理员登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }
        .container { max-width: 400px; margin: 100px auto; padding: 40px; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .title { text-align: center; margin-bottom: 30px; color: #333; font-size: 24px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; color: #555; font-weight: 500; }
        input[type="text"], input[type="password"] { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }
        input[type="text"]:focus, input[type="password"]:focus { outline: none; border-color: #007bff; }
        .btn { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
        .btn:hover { background: #0056b3; }
        .alert { padding: 10px; margin-bottom: 20px; border-radius: 4px; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="title">短链系统管理</h1>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'error' if category == 'error' else 'success' }}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="form-group">
                <label for="username">用户名</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">密码</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn">登录</button>
        </form>
    </div>
</body>
</html>'''

    # 仪表板页面模板
    dashboard_html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>短链系统 - 管理面板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }
        .header { background: white; padding: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header-content { max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; padding: 0 20px; }
        .logo { font-size: 20px; font-weight: bold; color: #333; }
        .user-info { display: flex; align-items: center; gap: 15px; }
        .logout-btn { color: #dc3545; text-decoration: none; }
        .logout-btn:hover { text-decoration: underline; }
        .container { max-width: 1200px; margin: 30px auto; padding: 0 20px; }
        .add-form { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .add-form h2 { margin-bottom: 20px; color: #333; }
        .form-row { display: flex; gap: 15px; align-items: end; flex-wrap: wrap; }
        .form-group { flex: 1; min-width: 200px; }
        .form-group label { display: block; margin-bottom: 5px; color: #555; font-weight: 500; }
        input[type="text"], input[type="password"], input[type="url"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
        input[type="text"]:focus, input[type="password"]:focus, input[type="url"]:focus { outline: none; border-color: #007bff; }
        .btn { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap; }
        .btn:hover { background: #0056b3; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .table-container { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; }
        .table-header { padding: 20px; border-bottom: 1px solid #eee; }
        .table-header h2 { color: #333; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; color: #555; }
        .shortlink-key { font-family: monospace; color: #007bff; font-weight: 500; }
        .copy-url { color: #666; cursor: pointer; transition: color 0.2s; }
        .copy-url:hover { color: #007bff; text-decoration: underline; }
        .shortlink-url { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .visits { text-align: center; color: #666; }
        .actions { text-align: center; }
        .alert { padding: 12px; margin-bottom: 20px; border-radius: 4px; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .empty-state { text-align: center; padding: 60px 20px; color: #666; }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="logo">短链管理系统</div>
            <div class="user-info">
                <span>欢迎，{{ session.admin_username }}</span>
                <a href="{{ url_for('admin_logout') }}" class="logout-btn">退出登录</a>
            </div>
        </div>
    </div>

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'error' if category == 'error' else 'success' }}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="add-form">
            <h2>添加新短链</h2>
            <form id="addForm">
                <div class="form-row">
                    <div class="form-group">
                        <label for="url">目标URL</label>
                        <input type="url" id="url" name="url" placeholder="例如：https://www.example.com" required>
                    </div>
                    <div class="form-group">
                        <label for="key">短链Key（可选）</label>
                        <input type="text" id="key" name="key" placeholder="留空自动生成4位随机key">
                    </div>
                    <button type="submit" class="btn">添加短链</button>
                </div>
            </form>
        </div>

        <div class="table-container">
            <div class="table-header">
                <h2>短链列表 ({{ shortlinks|length }} 条)</h2>
            </div>
            {% if shortlinks %}
                <table>
                    <thead>
                        <tr>
                            <th>短链Key</th>
                            <th>目标URL</th>
                            <th>访问次数</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for link in shortlinks %}
                        <tr>
                            <td>
                                <span class="shortlink-key">{{ link.key }}</span>
                                <br>
                                <small class="copy-url" data-url="{{ request.host_url }}{{ link.key }}" title="点击复制">
                                    {{ request.host_url }}{{ link.key }}
                                </small>
                            </td>
                            <td class="shortlink-url" title="{{ link.url }}">{{ link.url }}</td>
                            <td class="visits">{{ link.visits }}</td>
                            <td>{{ link.created_at[:16] }}</td>
                            <td class="actions">
                                <button class="btn btn-danger" onclick="deleteLink({{ link.id }})">删除</button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <div class="empty-state">
                    <p>暂无短链，请添加第一个短链</p>
                </div>
            {% endif %}
        </div>
    </div>

    <script>
        // 复制到剪贴板
        // 使用事件委托的方式
        document.addEventListener('click', async function(e) {
            if (e.target.classList.contains('copy-url')) {
                const url = e.target.getAttribute('data-url');
                const element = e.target;
                
                try {
                    await navigator.clipboard.writeText(url);
                    
                    const originalText = element.textContent;
                    element.textContent = '已复制!';
                    element.style.color = '#28a745';
                    
                    setTimeout(() => {
                        element.textContent = originalText;
                        element.style.color = '#666';
                    }, 1500);
                    
                } catch (err) {
                    // Fallback
                    const textArea = document.createElement('textarea');
                    textArea.value = url;
                    textArea.style.position = 'fixed';
                    textArea.style.opacity = '0';
                    document.body.appendChild(textArea);
                    textArea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textArea);
                    
                    const originalText = element.textContent;
                    element.textContent = '已复制!';
                    element.style.color = '#28a745';
                    
                    setTimeout(() => {
                        element.textContent = originalText;
                        element.style.color = '#666';
                    }, 1500);
                }
            }
        });

        // 添加短链
        document.getElementById('addForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const formData = new FormData(this);

            try {
                const response = await fetch('/admin/add', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();

                if (result.success) {
                    location.reload();
                } else {
                    alert('错误：' + result.message);
                }
            } catch (error) {
                alert('添加失败，请重试');
            }
        });

        // 删除短链
        async function deleteLink(id) {
            if (!confirm('确定要删除这个短链吗？')) return;

            try {
                const response = await fetch(`/admin/delete/${id}`, {
                    method: 'POST'
                });
                const result = await response.json();

                if (result.success) {
                    location.reload();
                } else {
                    alert('删除失败：' + result.message);
                }
            } catch (error) {
                alert('删除失败，请重试');
            }
        }
    </script>
</body>
</html>'''

    # 写入模板文件
    with open('templates/login.html', 'w', encoding='utf-8') as f:
        f.write(login_html)

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(dashboard_html)

if __name__ == '__main__':
    # 初始化数据库
    init_db()

    # 创建模板文件夹
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # 创建HTML模板文件
    create_templates()

    # 获取端口配置
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_ENV') == 'development'

    print(f"启动短链服务...")
    print(f"管理员用户名: {ADMIN_USERNAME}")
    print(f"数据库路径: {DATABASE}")
    print(f"监听地址: {host}:{port}")

    app.run(debug=False, host=host, port=port)

