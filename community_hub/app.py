"""Community Hub: a small, deployable Flask + SQLite community website."""
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
    DATABASE_PATH=os.environ.get('DATABASE_PATH', str(BASE_DIR / 'community.db')),
    MAX_CONTENT_LENGTH=1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',
)


def db():
    if 'db' not in g:
        path = Path(app.config['DATABASE_PATH'])
        path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path, timeout=20)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.execute('PRAGMA busy_timeout = 20000')
    return g.db


@app.teardown_appcontext
def close_db(_exception):
    conn = g.pop('db', None)
    if conn:
        conn.close()


def init_db():
    db().executescript('''
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('issue','task')),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        event_at TEXT,
        location TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Open',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        author_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
    CREATE INDEX IF NOT EXISTS idx_posts_kind ON posts(kind);
    CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
    ''')
    db().commit()


@app.before_request
def before():
    init_db()
    g.user = None
    if session.get('user_id'):
        g.user = db().execute('SELECT id, name, username FROM members WHERE id=?', (session['user_id'],)).fetchone()
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    if request.method == 'POST' and not secrets.compare_digest(request.form.get('csrf_token', ''), session['csrf']):
        abort(400, 'Invalid form token. Refresh the page and try again.')


@app.context_processor
def inject():
    return {'csrf_token': lambda: session.get('csrf', ''), 'current_year': datetime.now().year}


def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if g.user is None:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return inner


def validate_post(form, kind):
    title = form.get('title', '').strip()
    description = form.get('description', '').strip()
    location = form.get('location', '').strip()
    event_at = form.get('event_at', '').strip()
    status = form.get('status', 'Open').strip()
    if not 3 <= len(title) <= 120:
        return None, 'Title must be between 3 and 120 characters.'
    if not 1 <= len(description) <= 3000:
        return None, 'Description must be between 1 and 3,000 characters.'
    if len(location) > 150:
        return None, 'Location must be 150 characters or fewer.'
    if event_at:
        try:
            event_at = datetime.strptime(event_at, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%dT%H:%M')
        except ValueError:
            return None, 'Choose a valid date and time.'
    if kind == 'task' and status not in ('Open', 'In Progress', 'Completed'):
        return None, 'Choose a valid task status.'
    if kind == 'issue' and status not in ('Open', 'Resolved'):
        return None, 'Choose a valid issue status.'
    return {'title': title, 'description': description, 'location': location, 'event_at': event_at or None, 'status': status}, None


@app.get('/sw.js')
def service_worker():
    response = send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get('/')
def home():
    return redirect(url_for('issues')) if g.user else redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect(url_for('issues'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        if not 2 <= len(name) <= 80 or not re.fullmatch(r'[a-z0-9_.-]{3,30}', username):
            flash('Enter a name (2–80 characters) and username (3–30 letters, numbers, ., _ or -).', 'error')
        elif len(password) < 8:
            flash('Password must have at least 8 characters.', 'error')
        else:
            try:
                cur = db().execute('INSERT INTO members(name, username, password_hash) VALUES(?,?,?)', (name, username, generate_password_hash(password)))
                db().commit()
                session.clear()
                session['user_id'] = cur.lastrowid
                session['csrf'] = secrets.token_urlsafe(32)
                flash('Welcome to the community!', 'success')
                return redirect(url_for('issues'))
            except sqlite3.IntegrityError:
                flash('That username is already taken.', 'error')
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('issues'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = db().execute('SELECT * FROM members WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['csrf'] = secrets.token_urlsafe(32)
            return redirect(url_for('issues'))
        flash('Incorrect username or password.', 'error')
    return render_template('auth.html', mode='login')


@app.post('/logout')
@login_required
def logout():
    session.clear()
    flash('You have logged out.', 'success')
    return redirect(url_for('login'))


def listing(kind):
    rows = db().execute('''
        SELECT p.*, m.name AS author_name, m.username AS author_username,
        (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) AS comment_count
        FROM posts p JOIN members m ON m.id=p.author_id
        WHERE p.kind=? ORDER BY m.name COLLATE NOCASE ASC, m.id ASC, p.title COLLATE NOCASE ASC, p.id DESC
    ''', (kind,)).fetchall()
    grouped = []
    for row in rows:
        if not grouped or grouped[-1]['author_id'] != row['author_id']:
            grouped.append({'name': row['author_name'], 'author_id': row['author_id'], 'posts': []})
        grouped[-1]['posts'].append(row)
    return render_template('listing.html', kind=kind, grouped=grouped)


@app.get('/issues')
@login_required
def issues():
    return listing('issue')


@app.get('/tasks')
@login_required
def tasks():
    return listing('task')


@app.get('/members')
@login_required
def members():
    rows = db().execute('''SELECT m.id, m.name, m.username, m.joined_at,
        (SELECT COUNT(*) FROM posts p WHERE p.author_id=m.id AND p.kind='issue') AS issue_count,
        (SELECT COUNT(*) FROM posts p WHERE p.author_id=m.id AND p.kind='task') AS task_count
        FROM members m ORDER BY m.name COLLATE NOCASE, m.username''').fetchall()
    return render_template('members.html', members=rows)


@app.route('/new/<kind>', methods=['GET', 'POST'])
@login_required
def new_post(kind):
    if kind not in ('issue', 'task'):
        abort(404)
    if request.method == 'POST':
        data, error = validate_post(request.form, kind)
        if error:
            flash(error, 'error')
        else:
            cur = db().execute('''INSERT INTO posts(author_id,kind,title,description,event_at,location,status)
                VALUES(?,?,?,?,?,?,?)''', (g.user['id'], kind, data['title'], data['description'], data['event_at'], data['location'], data['status']))
            db().commit()
            flash('Your post was published.', 'success')
            return redirect(url_for('post_detail', post_id=cur.lastrowid))
    return render_template('post_form.html', kind=kind, post=None)


def get_post(post_id):
    row = db().execute('''SELECT p.*, m.name AS author_name FROM posts p
        JOIN members m ON m.id=p.author_id WHERE p.id=?''', (post_id,)).fetchone()
    if not row:
        abort(404)
    return row


@app.get('/post/<int:post_id>')
@login_required
def post_detail(post_id):
    post = get_post(post_id)
    comments = db().execute('''SELECT c.*, m.name AS author_name FROM comments c
        JOIN members m ON m.id=c.author_id WHERE c.post_id=? ORDER BY c.id''', (post_id,)).fetchall()
    return render_template('post_detail.html', post=post, comments=comments)


@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = get_post(post_id)
    if post['author_id'] != g.user['id']:
        abort(403, 'Only the person who posted this can edit it.')
    if request.method == 'POST':
        data, error = validate_post(request.form, post['kind'])
        if error:
            flash(error, 'error')
        else:
            db().execute('''UPDATE posts SET title=?, description=?, event_at=?, location=?, status=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=?''', (data['title'], data['description'], data['event_at'], data['location'], data['status'], post_id))
            db().commit()
            flash('Your post was updated.', 'success')
            return redirect(url_for('post_detail', post_id=post_id))
    return render_template('post_form.html', kind=post['kind'], post=post)


@app.post('/post/<int:post_id>/delete')
@login_required
def delete_post(post_id):
    post = get_post(post_id)
    if post['author_id'] != g.user['id']:
        abort(403, 'Only the person who posted this can delete it.')
    db().execute('DELETE FROM posts WHERE id=?', (post_id,))
    db().commit()
    flash('Your post was deleted.', 'success')
    return redirect(url_for('issues' if post['kind'] == 'issue' else 'tasks'))


@app.post('/post/<int:post_id>/comment')
@login_required
def add_comment(post_id):
    get_post(post_id)
    body = request.form.get('body', '').strip()
    if not 1 <= len(body) <= 1000:
        flash('Reply must be between 1 and 1,000 characters.', 'error')
    else:
        db().execute('INSERT INTO comments(post_id,author_id,body) VALUES(?,?,?)', (post_id, g.user['id'], body))
        db().commit()
        flash('Reply added.', 'success')
    return redirect(url_for('post_detail', post_id=post_id) + '#discussion')


@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if not 1 <= len(body) <= 1000:
            flash('Message must be between 1 and 1,000 characters.', 'error')
        else:
            db().execute('INSERT INTO chat_messages(author_id,body) VALUES(?,?)', (g.user['id'], body))
            db().commit()
            return redirect(url_for('chat') + '#latest')
    messages = db().execute('''SELECT x.*, m.name AS author_name FROM (
        SELECT * FROM chat_messages ORDER BY id DESC LIMIT 100) x
        JOIN members m ON m.id=x.author_id ORDER BY x.id ASC''').fetchall()
    return render_template('chat.html', messages=messages)


@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html', code=403, message=str(error.description)), 403


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, message='That page or post does not exist.'), 404


@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', code=400, message=str(error.description)), 400


@app.cli.command('seed-demo')
def seed_demo():
    """Optional local sample data. Do NOT run on a public deployment."""
    init_db()
    users = [('Susan Miller', 'susan'), ('Joey Parker', 'joey'), ('Maria Lopez', 'maria')]
    ids = {}
    for name, username in users:
        user = db().execute('SELECT id FROM members WHERE username=?', (username,)).fetchone()
        if user:
            ids[username] = user['id']
        else:
            ids[username] = db().execute('INSERT INTO members(name,username,password_hash) VALUES(?,?,?)',
                (name, username, generate_password_hash('Welcome123!'))).lastrowid
    if db().execute('SELECT COUNT(*) FROM posts').fetchone()[0] == 0:
        sample = [
            (ids['susan'], 'issue', 'Neighborhood potluck', 'Bring a dish to share! Everyone is welcome. Please reply with what you plan to bring.', '2026-11-14T17:00', 'Community clubhouse', 'Open'),
            (ids['joey'], 'task', 'Clean the community garage', 'Looking for volunteers to help tidy the shared garage and organize tools.', '2026-11-07T10:00', 'Shared garage', 'Open'),
            (ids['maria'], 'issue', 'Streetlight not working', 'The streetlight by the west entrance has been out for a few days.', None, 'West entrance', 'Open'),
            (ids['susan'], 'task', 'Set up tables for the potluck', 'Need two volunteers to arrange tables and chairs before the potluck.', '2026-11-14T15:30', 'Community clubhouse', 'Open'),
        ]
        db().executemany('INSERT INTO posts(author_id,kind,title,description,event_at,location,status) VALUES(?,?,?,?,?,?,?)', sample)
        db().execute('INSERT INTO chat_messages(author_id,body) VALUES(?,?)', (ids['susan'], 'Welcome! Check the Issues and Tasks pages for community updates.'))
    db().commit()
    print('Demo ready. Local users: susan, joey, maria; password: Welcome123!')


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1')
