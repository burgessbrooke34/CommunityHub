# Community Hub — working website

A complete small Flask web app with a SQLite database. Pages: **Issues** (opens first after sign-in), **Tasks**, **Members**, and **Chat**.

## What works

- Register and log in with your own username/password (passwords are hashed).
- Issues / events and tasks appear **alphabetically by the posting member's name**, then title. Example: Joey's garage cleanup; Susan's potluck.
- Create issues, announcements, potlucks, volunteer tasks, and projects with optional date/time and location.
- Only the member who created an issue or task can **edit or delete it**. This is enforced by the server even if another user types the editing URL directly.
- Issue statuses: Open / Resolved. Task statuses: Open / In Progress / Completed.
- Members directory; replies on each issue/task; shared Chat message board.
- Mobile-friendly pages; basic CSRF form protection; parameterized SQL queries.

## Run locally (Windows)

1. Install Python 3.10+ from https://www.python.org/downloads/ and check **Add python.exe to PATH**.
2. Extract this ZIP and open Command Prompt or VS Code terminal **inside `community_hub`**.
3. Run:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```

4. Open **http://127.0.0.1:5000** in a browser.
5. Click **Join now**, create an account, and add a post. A `community.db` SQLite database is created automatically.

On Mac/Linux: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt`, `python app.py`.

### Optional sample users/content (LOCAL ONLY)

Stop the website and run `flask --app app seed-demo` in your activated virtual environment. This creates sample posts for Susan, Joey, and Maria, with usernames `susan`, `joey`, `maria`, all using password `Welcome123!`. Restart `python app.py` and log in. **Do not use these demo accounts on a live/public site.** Existing posts are not removed by this command.

## Deploy online

**Important:** Files being ZIP-ready / deployment-ready does not mean the website is already live. Deploy it to a server or platform and configure the environment to make it reachable publicly. A SQLite database needs **persistent storage** or accounts/posts will be lost on restart/redeploy.

### Deploy via Docker to a host with persistent disk (recommended for this small project)

1. Upload the extracted project folder to a Docker-capable host such as Railway, Fly.io, or a VPS, and select **Deploy from Dockerfile** (platform menus vary).
2. Configure a **persistent volume mounted at `/data`**. This is essential; SQLite stores all members/posts/messages at `/data/community.db` in the container.
3. Set environment variable `SECRET_KEY` to a long random secret (for example `python -c "import secrets;print(secrets.token_hex(32))"`). Keep the same value between deploys.
4. Set `COOKIE_SECURE=1` when the site uses HTTPS (the Dockerfile sets this by default). Connect the platform's public HTTPS domain.
5. Run one application instance / one Gunicorn worker with a small SQLite app. Do not deploy multiple replicas against separate disks.
6. Test registration, creating an issue, logging in as a second person, and confirming the second person cannot edit the first person's issue. Restart the container and check that the posts remain.

A sample Dockerfile and Procfile are included. Hosts that offer **ephemeral-only** storage are not suitable for durable SQLite data unless you add persistent disk. For a larger public community with many simultaneous users, migrate to hosted PostgreSQL, add moderation/spam controls, rate limiting, backups, and password reset/email verification.

### Alternative: deploy to a persistent Python hosting environment

On a Python-capable server with persistent file storage:

```bash
pip install -r requirements.txt
export SECRET_KEY='your-long-random-secret'
export DATABASE_PATH='/path/to/persistent/community.db'
export COOKIE_SECURE=1
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 app:app
```

Put HTTPS in front of the app via your host/reverse proxy. **Never use Flask's built-in development server for a public website.**

## Files

- `app.py`: routes, authentication, authorization, data access, database schema.
- `templates/`: HTML UI for sign-in, listing, posts, members, and chat.
- `static/style.css`: responsive styles.
- `requirements.txt`, `Dockerfile`, `Procfile`: run/deployment files.
- `test_app.py`: basic automated tests.

## Data tables

`members` → usernames / hashed passwords; `posts` → issues and tasks; `comments` → replies to posts; `chat_messages` → community chat. Foreign keys link data to members.

## Notes / scope

- Chat is a shared **message board**, not real-time push chat; refresh to see updates. The latest 100 messages show at a time.
- Dates and times display as entered; this version does not automatically convert time zones.
- Only original posters edit/delete their issue/task, but other signed-in members may reply.
- Public registration is open to anyone with the website URL. For a private neighborhood, add invite-only registration or admin approval before publicly promoting it.
- For a real public deployment, add automated backups and monitoring, plus a process to handle abusive posts.


## PWA / Install on a phone

This edition includes `static/manifest.webmanifest`, app icons, an offline notice, and a service worker served at `/sw.js`. It uses the existing Flask backend and SQLite database unchanged.

- Run locally with `python app.py` and test at `http://127.0.0.1:5000`. PWA service workers are allowed on localhost.
- Deploy Flask on an HTTPS URL with a persistent disk for `DATABASE_PATH` and a stable `SECRET_KEY`. Set `COOKIE_SECURE=1` when using HTTPS. GitHub Pages cannot host a Python backend.
- On iPhone: open the **deployed HTTPS link** in Safari, use **Share → Add to Home Screen**, enable **Open as Web App** if prompted, and tap **Add**.
- On Android Chrome: open the HTTPS link and choose **Install app** or **Add to Home screen** in the browser menu.
- Offline behavior is deliberately limited: an offline notice is available, but account pages, issues, tasks, members, and chat are never cached. This prevents exposing member information from earlier signed-in sessions. Creating posts, login, and chat always need a connection.
- Push these updated files to the existing GitHub repository with `git add .`, `git commit -m "Add PWA support"`, `git push`.
