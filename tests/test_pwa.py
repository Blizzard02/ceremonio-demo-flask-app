import os
import json
import atexit
import tempfile

# Use a throwaway DB in the temp dir (not the project's instance/ folder) and clean it up.
_TEST_DB = os.path.join(tempfile.gettempdir(), "glenti_test_pwa.db")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + _TEST_DB.replace(os.sep, "/"))
os.environ.setdefault("SECRET_KEY", "test-secret")
def _cleanup_test_db():
    try:
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)
    except OSError:
        pass  # file may still be locked on Windows at shutdown — harmless, it's in temp

atexit.register(_cleanup_test_db)

import app as appmod  # noqa: E402

client = appmod.app.test_client()


def test_service_worker_served_at_root_scope():
    r = client.get("/service-worker.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["Content-Type"]
    assert r.headers.get("Service-Worker-Allowed") == "/"


def test_manifest_valid():
    r = client.get("/static/manifest.json")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["short_name"] == "Ceremonio"
    assert data["display"] == "standalone"
    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    assert len(data["icons"]) >= 2


def test_icons_exist():
    base = os.path.join(os.path.dirname(appmod.__file__), "static", "icons")
    for name in ["icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"]:
        assert os.path.exists(os.path.join(base, name)), name


def test_login_page_has_pwa_tags():
    r = client.get("/login")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert 'rel="manifest"' in body
    assert "register(" in body and "service-worker.js" in body
    assert 'name="theme-color"' in body
    assert "apple-touch-icon" in body


def test_translations_loaded():
    assert "el" in appmod.TRANSLATIONS and "en" in appmod.TRANSLATIONS
    assert appmod.TRANSLATIONS["en"].get("login.submit") == "Sign in"
    assert appmod.TRANSLATIONS["el"].get("login.submit") == "Σύνδεση"


def test_set_lang_route_redirects_and_ignores_invalid():
    with appmod.app.test_client() as c:
        assert c.get("/set_lang/en").status_code in (301, 302)
        assert c.get("/set_lang/zz").status_code in (301, 302)  # invalid ignored, no crash


def test_language_switch_changes_login_text():
    with appmod.app.test_client() as c:
        el = c.get("/login").data.decode("utf-8")
        assert "Σύνδεση" in el            # Greek by default
        c.get("/set_lang/en")
        en = c.get("/login").data.decode("utf-8")
        assert "Sign in" in en                       # switched to English
        # The flag switcher is built client-side from this bootstrap; assert the
        # real mechanism is present rather than markup that only exists for the test.
        assert "GLENTI_I18N" in en                    # i18n bootstrap present
        assert "/set_lang/" in en                     # switcher builds language links
        assert '"en"' in en and '"el"' in en          # both languages offered
