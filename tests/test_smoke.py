"""
Smoke test suite — verifies every major page renders and core flows work.
Runs against a throwaway SQLite database; no external services required.
"""
import os
import re
import sys
import tempfile
import uuid

# ------------------------------------------------------------------
# Set env vars BEFORE importing app so the module-level config picks
# them up correctly.
# ------------------------------------------------------------------
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="smoke_test_")
os.close(_db_fd)

os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["SECRET_KEY"] = "smoke-test-secret-key"

# Ensure project root is on the path when pytest is run from a subdirectory.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import app as appmod  # noqa: E402

# ------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------
_EMAIL = f"smoke_{uuid.uuid4().hex[:8]}@test.local"
_PASSWORD = "SmokePass123!"
_PARTNER_EMAIL = f"partner_{uuid.uuid4().hex[:8]}@test.local"
_WEDDING_TITLE = "Smoke Wedding"


def _make_client():
    """Return a test client with a persistent cookie jar (session)."""
    return appmod.app.test_client()


def _register_and_login(client):
    """Register a new user + wedding, then confirm we are logged in."""
    rv = client.post(
        "/register",
        data={
            "email": _EMAIL,
            "password": _PASSWORD,
            "partner_email": _PARTNER_EMAIL,
            "wedding_title": _WEDDING_TITLE,
        },
        follow_redirects=True,
    )
    assert rv.status_code == 200, f"Register failed: {rv.status_code}"
    return rv


def _first_match(pattern, text):
    """Return the first capturing group of *pattern* in *text*, or None."""
    m = re.search(pattern, text)
    return m.group(1) if m else None


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_login_page_returns_200():
    with _make_client() as c:
        assert c.get("/login").status_code == 200


def test_register_page_returns_200():
    with _make_client() as c:
        assert c.get("/register").status_code == 200


def test_full_smoke_flow():
    """
    Register → create group → add guest → add expense → add song →
    assert all pages return 200 → assert edit pages return 200 →
    switch language → home still 200 + English nav label present.
    """
    with _make_client() as c:
        # ---- register / login ----
        _register_and_login(c)

        # ---- home ("/") must be 200 after login ----
        assert c.get("/").status_code == 200

        # ---- create a group ----
        rv = c.post(
            "/add_omada",
            data={"onoma": "Smoke Group", "pleura": "nyfis"},
            follow_redirects=True,
        )
        assert rv.status_code == 200

        # Discover group id from the home page HTML
        home_html = c.get("/").data.decode("utf-8")
        omada_id = _first_match(r'/edit_omada/(\d+)', home_html)
        assert omada_id is not None, "Could not find omada id in home page HTML"

        # ---- add a guest ----
        rv = c.post(
            "/add_kalesmeno",
            data={
                "onoma": "Smoke Guest",
                "omada_id": omada_id,
                "tilefono": "6900000000",
                "email": "smokeguest@test.local",
                "plus_one": "0",
                "fylo": "Δεν ορίστηκε",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200

        # Discover guest id from the home page HTML
        home_html = c.get("/").data.decode("utf-8")
        guest_id = _first_match(r'/edit_kalesmeno/(\d+)', home_html)
        assert guest_id is not None, "Could not find guest id in home page HTML"

        # ---- add an expense ----
        rv = c.post(
            "/add_exodo",
            data={
                "perigrafi": "Smoke Expense",
                "katigoria": "Catering",
                "promithiefthis": "Smoke Vendor",
                "ektimomeno_kostos": "1000",
                "teliko_kostos": "900",
                "plirothike": "450",
                "imerominia_pliromis": "2025-01-01",
                "sxolia": "",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200

        # Discover expense id from the oikonomika page HTML
        oik_html = c.get("/oikonomika").data.decode("utf-8")
        exodo_id = _first_match(r'/edit_exodo/(\d+)', oik_html)
        assert exodo_id is not None, "Could not find exodo id in oikonomika page HTML"

        # ---- add a song ----
        rv = c.post(
            "/add_tragoudi",
            data={
                "titlos": "Smoke Song",
                "kallitechnis": "Smoke Artist",
                "katigoria": "Πάρτι",
                "link": "",
                "sxolia": "",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200

        # Discover song id from the playlist page HTML
        playlist_html = c.get("/playlist").data.decode("utf-8")
        tragoudi_id = _first_match(r'/edit_tragoudi/(\d+)', playlist_html)
        assert tragoudi_id is not None, "Could not find tragoudi id in playlist page HTML"

        # ---- assert all main pages return 200 ----
        pages = [
            "/",
            "/glenti",
            "/oikonomika",
            "/analytics",
            "/settings",
            "/backup",
            "/playlist",
            "/invite_preview",
            "/export_data",
        ]
        for page in pages:
            rv = c.get(page)
            assert rv.status_code == 200, f"GET {page} returned {rv.status_code}"

        # ---- assert edit pages return 200 ----
        edit_pages = [
            f"/edit_kalesmeno/{guest_id}",
            f"/edit_omada/{omada_id}",
            f"/edit_exodo/{exodo_id}",
            f"/edit_tragoudi/{tragoudi_id}",
        ]
        for page in edit_pages:
            rv = c.get(page)
            assert rv.status_code == 200, f"GET {page} returned {rv.status_code}"

        # ---- switch language to English ----
        rv = c.get("/set_lang/en", follow_redirects=True)
        assert rv.status_code == 200

        # ---- home still 200 and contains an English nav label ----
        rv = c.get("/")
        assert rv.status_code == 200
        body = rv.data.decode("utf-8")
        # "Guests" is the English label for the nav.guests translation key
        assert "Guests" in body, "English nav label 'Guests' not found after language switch"


# ------------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):
    """Remove the temp DB file after the test run."""
    try:
        os.unlink(_db_path)
    except OSError:
        pass
