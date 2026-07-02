# Ceremio — Free Deployment to PythonAnywhere

---

## 0. Accounts (one-time)

1. Create a new Gmail address dedicated to this project.
2. Create a free PythonAnywhere "Beginner" account at:
   https://www.pythonanywhere.com/registration/register/beginner/
3. Choose username `ceremio` — the app URL becomes **https://ceremio.pythonanywhere.com**.
   - Fallback usernames if `ceremio` is taken: `ceremioapp`, `getceremio`, `ceremioplanner`.

---

## 1. Upload the code

Upload the whole project folder to `/home/<username>/gamos` using either the **Files** tab in the PythonAnywhere dashboard or a **Bash console** (`git clone` or manual upload).

> Do **not** upload `instance/gamos.db` if you are starting with a clean database on PythonAnywhere.

---

## 2. Create the free MySQL database

1. Go to the **Databases** tab in the PythonAnywhere dashboard.
2. Set a MySQL password (you will need it in Step 4).
3. Create a database named `<username>$ceremio`.
4. Note the host: `<username>.mysql.pythonanywhere-services.com`.

---

## 3. Web app + dependencies

1. Go to the **Web** tab → **Add a new web app** → **Manual configuration** → **Python 3.x** (choose the latest available, e.g. 3.10).
2. Open a **Bash console** and install dependencies:

```bash
pip3.10 install --user -r /home/<username>/gamos/requirements.txt
```

> Match the `pip3.x` version to whatever Python version you selected in the web app.

---

## 4. WSGI configuration

1. In the **Web** tab, click the link to edit the **WSGI configuration file**.
2. Replace the entire contents of the file with:

```python
import os, sys
os.environ["DATABASE_URL"] = "mysql+pymysql://<username>:<MYSQL_PASSWORD>@<username>.mysql.pythonanywhere-services.com/<username>$ceremio"
os.environ["SECRET_KEY"] = "<paste a long random string>"
path = "/home/<username>/gamos"
if path not in sys.path:
    sys.path.append(path)
from app import app as application  # noqa
```

3. Replace `<username>`, `<MYSQL_PASSWORD>`, and the `SECRET_KEY` placeholder with real values.

**Generate a SECRET_KEY locally** (run this on your PC or in a Bash console):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. Static files

In the **Web** tab, scroll to the **Static files** section and add a mapping:

| URL       | Directory                         |
|-----------|-----------------------------------|
| `/static/` | `/home/<username>/gamos/static/` |

---

## 6. Reload & test

1. Click the green **Reload** button in the Web tab.
2. Visit **https://ceremio.pythonanywhere.com**.
3. Smoke-test the app end-to-end:
   - Register a new account.
   - Add a guest group and a guest.
   - Open the invite link and submit an RSVP.
4. Install the PWA from a phone using **Add to Home Screen** in the browser menu.

---

## 7. Keep the free app alive

PythonAnywhere free accounts require periodic renewal. Log in at least once every 3 months and click **"Run until 3 months from today"** in the Web tab.

---

## Notes

- Invite links take the form `https://ceremio.pythonanywhere.com/invite/<token>` and retain their expiration date as configured in the app settings.
- Custom domain support and Firebase/scaling are deferred to a later phase.
- The database lives on PythonAnywhere's MySQL server — **not** on your local PC. Your local `instance/gamos.db` is only used for local development.
