
from flask import Flask, g, render_template_string, request, redirect, url_for, session, jsonify
import sqlite3, os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'lms_flask.db')

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'devsecret')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        manager_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS leave_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        max_days INTEGER
    );
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        leave_type_id INTEGER,
        start_date TEXT,
        end_date TEXT,
        days INTEGER,
        reason TEXT,
        status TEXT,
        manager_id INTEGER,
        submitted_at TEXT,
        decided_at TEXT
    );
    """)
    db.commit()
    if cur.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'] == 0:
        cur.execute('INSERT INTO users (name,email,password,role,manager_id) VALUES (?,?,?,?,?)',
                    ('Alice Employee','alice@example.com','password','employee',2))
        cur.execute('INSERT INTO users (name,email,password,role,manager_id) VALUES (?,?,?,?,?)',
                    ('Bob Manager','bob@example.com','password','manager',None))
        cur.execute('INSERT INTO users (name,email,password,role,manager_id) VALUES (?,?,?,?,?)',
                    ('Carol HR','carol@example.com','password','hr',None))
        db.commit()
    if cur.execute('SELECT COUNT(*) as c FROM leave_types').fetchone()['c'] == 0:
        cur.execute('INSERT INTO leave_types (name,max_days) VALUES (?,?)', ('Annual',30))
        cur.execute('INSERT INTO leave_types (name,max_days) VALUES (?,?)', ('Sick',15))
        db.commit()

T_INDEX = """<!doctype html><html><body>
<h2>Leave Management System - Flask Demo</h2>
{% if user %}
  <p>Welcome {{user['name']}} ({{user['role']}}) — <a href="{{ url_for('logout') }}">Logout</a></p>
  <ul>
    <li><a href="{{ url_for('apply') }}">Apply Leave</a></li>
    <li><a href="{{ url_for('requests') }}">My / Team Requests</a></li>
  </ul>
{% else %}
  <p><a href="{{ url_for('login') }}">Login</a></p>
  <p>Sample accounts: alice@example.com / password (employee), bob@example.com / password (manager), carol@example.com / password (hr)</p>
{% endif %}
</body></html>"""

T_LOGIN = """<!doctype html><html><body>
<h3>Login</h3>
<form method="post">
  Email: <input name="email"><br>
  Password: <input name="password" type="password"><br>
  <button>Login</button>
</form>
<p><a href="{{ url_for('index') }}">Back</a></p>
</body></html>"""

T_APPLY = """<!doctype html><html><body>
<h3>Apply Leave</h3>
<form method="post">
  Type: <select name="leave_type_id">{% for t in types %}<option value='{{t['id']}}'>{{t['name']}}</option>{% endfor %}</select><br>
  Start: <input name="start_date" type="date"><br>
  End: <input name="end_date" type="date"><br>
  Days: <input name="days" type="number" value="1"><br>
  Reason: <input name="reason"><br>
  <button>Submit</button>
</form>
<p><a href="{{ url_for('index') }}">Home</a></p>
</body></html>"""

T_REQUESTS = """<!doctype html><html><body>
<h3>Requests</h3>
<table border=1 cellpadding=6>
  <tr><th>ID</th><th>User</th><th>Days</th><th>Status</th><th>Action</th></tr>
  {% for r in requests %}
  <tr>
    <td>{{ r['id'] }}</td>
    <td>{{ r['user_name'] }}</td>
    <td>{{ r['days'] }}</td>
    <td>{{ r['status'] }}</td>
    <td>
      {% if user_role in ['manager','hr'] and r['status']=='PENDING' %}
        <form method="post" action="{{ url_for('decision') }}" style="display:inline">
          <input type="hidden" name="request_id" value="{{r['id']}}">
          <button name="action" value="APPROVE">Approve</button>
          <button name="action" value="REJECT">Reject</button>
        </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>
<p><a href="{{ url_for('index') }}">Home</a></p>
</body></html>"""

@app.route('/')
def index():
    user = None
    if 'user_id' in session:
        db = get_db()
        user = db.execute('SELECT id,name,role FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    return render_template_string(T_INDEX, user=user)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password)).fetchone()
        if row:
            session['user_id'] = row['id']
            return redirect(url_for('index'))
        return 'Invalid credentials. <a href="/login">Try again</a>'
    return render_template_string(T_LOGIN)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/apply', methods=['GET','POST'])
def apply():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    types = db.execute('SELECT * FROM leave_types').fetchall()
    if request.method == 'POST':
        lt = request.form.get('leave_type_id')
        start = request.form.get('start_date')
        end = request.form.get('end_date')
        days = int(request.form.get('days') or 1)
        reason = request.form.get('reason') or ''
        user_row = db.execute('SELECT manager_id FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        manager_id = user_row['manager_id'] if user_row else None
        db.execute('INSERT INTO leave_requests (user_id,leave_type_id,start_date,end_date,days,reason,status,manager_id,submitted_at) VALUES (?,?,?,?,?,?,?,?,?)',
                   (session['user_id'], lt, start, end, days, reason, 'PENDING', manager_id, datetime.utcnow().isoformat()))
        db.commit()
        return 'Applied. <a href="/requests">View requests</a>'
    return render_template_string(T_APPLY, types=types)

@app.route('/requests', methods=['GET'])
def requests():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    role = db.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()['role']
    if role == 'employee':
        rows = db.execute('SELECT lr.*, u.name as user_name FROM leave_requests lr LEFT JOIN users u ON lr.user_id = u.id WHERE lr.user_id = ? ORDER BY submitted_at DESC', (session['user_id'],)).fetchall()
    elif role == 'manager':
        rows = db.execute('SELECT lr.*, u.name as user_name FROM leave_requests lr LEFT JOIN users u ON lr.user_id = u.id WHERE lr.manager_id = ? ORDER BY submitted_at DESC', (session['user_id'],)).fetchall()
    else:
        rows = db.execute('SELECT lr.*, u.name as user_name FROM leave_requests lr LEFT JOIN users u ON lr.user_id = u.id ORDER BY submitted_at DESC').fetchall()
    return render_template_string(T_REQUESTS, requests=rows, user_role=role)

@app.route('/decision', methods=['POST'])
def decision():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    action = request.form.get('action')
    request_id = request.form.get('request_id')
    db = get_db()
    role = db.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()['role']
    if role not in ('manager','hr'):
        return 'Not authorized'
    if action not in ('APPROVE','REJECT'):
        return 'Invalid action'
    status = 'APPROVED' if action == 'APPROVE' else 'REJECTED'
    db.execute('UPDATE leave_requests SET status = ?, decided_at = ? WHERE id = ?', (status, datetime.utcnow().isoformat(), request_id))
    db.commit()
    return redirect(url_for('requests'))

@app.route('/api/health')
def api_health():
    return jsonify({'ok': True})

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
