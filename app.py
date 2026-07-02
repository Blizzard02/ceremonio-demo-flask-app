from flask import Flask, render_template, request, redirect, flash, jsonify, url_for, send_file, session
from flask_sqlalchemy import SQLAlchemy
import json
import uuid
import os
import re
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Production-ready config: local SQLite by default, DATABASE_URL for online hosting/PostgreSQL.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///gamos.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Keep DB connections healthy on hosts that drop idle connections (e.g. PythonAnywhere MySQL
# closes idle connections after ~5 min). pool_pre_ping revives stale ones; recycle stays under it.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}

# Session-cookie hardening. HTTPONLY + SameSite are always safe; SECURE is opt-in via env so
# local http://localhost still works (set SESSION_COOKIE_SECURE=1 in production over HTTPS).
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
)

db = SQLAlchemy(app)


# -----------------------------
# Auth / multi-wedding models
# -----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.String(30), default=lambda: now_iso())

    memberships = db.relationship("WeddingMember", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Wedding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="Ο γάμος μας")
    owner_email = db.Column(db.String(255), nullable=False)
    partner_email = db.Column(db.String(255), nullable=False, index=True)
    created_at = db.Column(db.String(30), default=lambda: now_iso())

    members = db.relationship("WeddingMember", backref="wedding", lazy=True, cascade="all, delete-orphan")


class WeddingMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    role = db.Column(db.String(30), default="partner")

    __table_args__ = (db.UniqueConstraint("wedding_id", "user_id", name="uq_wedding_user"),)


# -----------------------------
# App data models
# -----------------------------
class Omada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    onoma = db.Column(db.String(100), nullable=False)
    pleura = db.Column(db.String(20), nullable=False)

    kalesmeni = db.relationship("Kalesmenos", backref="omada", lazy=True)

    def synolo_atoma(self):
        return len(self.kalesmeni) + sum((k.plus_one or 0) for k in self.kalesmeni)


class Kalesmenos(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    onoma = db.Column(db.String(100), nullable=False)
    tilefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    rsvp = db.Column(db.String(50), default="Δεν έχει απαντήσει")
    plus_one = db.Column(db.Integer, default=0)
    fylo = db.Column(db.String(20), default="Δεν ορίστηκε")
    einai_paidi = db.Column(db.Boolean, default=False)
    prosklitirio_stalthike = db.Column(db.Boolean, default=False)
    invitation_token = db.Column(db.String(80), unique=True)
    diatrofi = db.Column(db.String(50), default="Δεν απάντησε")
    diatrofi_sxolia = db.Column(db.Text)
    rsvp_apantithike_at = db.Column(db.String(30))

    omada_id = db.Column(db.Integer, db.ForeignKey("omada.id"), nullable=False)


class GlentiState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    objects_json = db.Column(db.Text, default="[]")
    assignments_json = db.Column(db.Text, default="{}")


class BudgetSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    synoliko_budget = db.Column(db.Float, default=0)


class WeddingSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    onoma_zeugariou = db.Column(db.String(200), default="Ο γάμος μας")
    imerominia_gamou = db.Column(db.String(50), default="")
    ora_gamou = db.Column(db.String(30), default="")
    topothesia = db.Column(db.String(250), default="")
    maps_link = db.Column(db.String(500), default="")
    koumparoi = db.Column(db.String(250), default="")
    oikogeneia_nyfis = db.Column(db.String(250), default="")
    oikogeneia_gambrou = db.Column(db.String(250), default="")
    iban_owner = db.Column(db.String(200), default="")
    bank_name = db.Column(db.String(150), default="")
    iban = db.Column(db.String(80), default="")
    minima = db.Column(db.Text, default="Με χαρά σας προσκαλούμε στον γάμο μας!")
    background_image = db.Column(db.String(300))
    rsvp_deadline = db.Column(db.String(20))
    invite_template = db.Column(db.String(50), default="romantic")

    # Custom invitation maker (empty = fall back to the preset/template defaults)
    invite_font = db.Column(db.String(40), default="")
    invite_color = db.Column(db.String(20), default="")          # main / accent (names, buttons)
    invite_bg = db.Column(db.String(20), default="")             # page background
    invite_bg2 = db.Column(db.String(20), default="")            # 2nd background colour -> gradient
    invite_text_color = db.Column(db.String(20), default="")     # body / detail text colour
    invite_emoji = db.Column(db.String(16), default="")          # ornament + background-pattern symbol
    invite_pattern_opacity = db.Column(db.Integer, default=0)    # 0 = no pattern, else 1..30 (%)

    # Ceremony / reception split locations
    ceremony_name = db.Column(db.String(250), default="")
    ceremony_address = db.Column(db.String(350), default="")
    ceremony_time = db.Column(db.String(30), default="")
    ceremony_maps_link = db.Column(db.String(500), default="")
    reception_name = db.Column(db.String(250), default="")
    reception_address = db.Column(db.String(350), default="")
    reception_time = db.Column(db.String(30), default="")
    reception_maps_link = db.Column(db.String(500), default="")

    # Customisable side labels (empty = fall back to translated default)
    side_nyfis = db.Column(db.String(60), default="")
    side_gambrou = db.Column(db.String(60), default="")


class Exodo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    perigrafi = db.Column(db.String(200), nullable=False)
    katigoria = db.Column(db.String(100), nullable=False)
    promithiefthis = db.Column(db.String(150))
    ektimomeno_kostos = db.Column(db.Float, default=0)
    teliko_kostos = db.Column(db.Float, default=0)
    plirothike = db.Column(db.Float, default=0)
    imerominia_pliromis = db.Column(db.String(20))
    sxolia = db.Column(db.Text)

    def ypoloipo(self):
        return (self.teliko_kostos or 0) - (self.plirothike or 0)


class Tragoudi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), index=True)
    titlos = db.Column(db.String(200), nullable=False)
    kallitechnis = db.Column(db.String(150))
    katigoria = db.Column(db.String(100), nullable=False)
    link = db.Column(db.String(300))
    sxolia = db.Column(db.Text)


# Static reference list (kept for backups/imports). The live list is built by
# expense_categories(), which makes the two attire rows follow the side names.
KATIGORIES_EXODON = [
    "Χώρος δεξίωσης", "Catering", "Ενδυμασία Νύφης", "Ενδυμασία Γαμπρού", "Κοσμήματα",
    "Φωτογράφος / Βιντεογράφος", "DJ / Μουσική", "Στολισμός",
    "Προσκλητήρια", "Μπομπονιέρες", "Εκκλησία / Δημαρχείο",
    "Μακιγιάζ / Μαλλιά", "Μεταφορές", "Λοιπά έξοδα"
]

KATIGORIES_MOUSIKIS = ["Είσοδος ζευγαριού", "Πρώτος χορός", "Κοπή τούρτας", "Πάρτι", "Να μην παιχτούν"]

# Legacy preset names — kept so older saved invitations keep working and so the
# custom maker can offer "preset styles" as quick-start buttons.
INVITE_TEMPLATES = {
    "romantic": "Romantic Pink",
    "classic": "Classic Elegant",
    "minimal": "Minimal Modern",
    "floral": "Floral",
    "luxury": "Dark Luxury",
    "photo": "Photo Background"
}

# Curated, cross-platform font stacks for the invitation maker. The stored value is
# the KEY; the stack is resolved at render time so we never ship heavyweight font files.
# NB: font names use single quotes so the stack can be dropped into an inline
# style="" attribute (double-quoted) without breaking it.
# IMPORTANT: every stack must render GREEK (the app is Greek-first), so each one
# leads with a font that ships Greek glyphs on common systems and ends in a
# Greek-capable generic — never a Latin-only display face.
INVITE_FONTS = {
    "serif":    "'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif",
    "classic":  "'Times New Roman', 'Nimbus Roman', Georgia, serif",
    "georgia":  "Georgia, 'Palatino Linotype', 'Times New Roman', serif",
    "didone":   "'Didot', Constantia, Georgia, 'Times New Roman', serif",
    "sans":     "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    "rounded":  "'Trebuchet MS', 'Segoe UI', Tahoma, Verdana, sans-serif",
    "corbel":   "Corbel, 'Segoe UI', Candara, 'Lucida Grande', Verdana, sans-serif",
    "mono":     "'Courier New', 'DejaVu Sans Mono', monospace",
}
DEFAULT_INVITE_FONT = "serif"


def safe_hex(value):
    """Accept only a CSS hex colour (#rgb / #rrggbb / #rrggbbaa); otherwise empty."""
    v = (value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3}([0-9a-fA-F]{2})?)?", v):
        return v
    return ""

# Quick-start "preset styles": each fills EVERY maker control at once (font, colours,
# text colour, gradient, ornament, pattern). The user can then tweak anything.
INVITE_PRESETS = {
    "romantic": {"font": "serif",    "color": "#be3d7a", "bg": "#fdf2f8", "bg2": "#f7d4e6", "text": "#5b3650", "emoji": "🌸", "pattern": 6},
    "classic":  {"font": "classic",  "color": "#b45309", "bg": "#fffbeb", "bg2": "#fbe9cf", "text": "#4a3b22", "emoji": "❦", "pattern": 0},
    "minimal":  {"font": "sans",     "color": "#111827", "bg": "#f9fafb", "bg2": "",        "text": "#374151", "emoji": "",   "pattern": 0},
    "floral":   {"font": "georgia",  "color": "#be185d", "bg": "#fdf2f8", "bg2": "#fbe2ef", "text": "#4a2740", "emoji": "🌷", "pattern": 9},
    "luxury":   {"font": "didone",   "color": "#caa24a", "bg": "#161019", "bg2": "#2c2233", "text": "#ece6d6", "emoji": "✨", "pattern": 7},
    "garden":   {"font": "georgia",  "color": "#3f7d5a", "bg": "#f2faf3", "bg2": "#dcefe0", "text": "#234534", "emoji": "🌿", "pattern": 10},
    "dusty":    {"font": "serif",    "color": "#6d6a99", "bg": "#f5f4fb", "bg2": "#e4e2f3", "text": "#3c3a55", "emoji": "🦋", "pattern": 7},
    "boho":     {"font": "rounded",  "color": "#b07b3e", "bg": "#fbf6ee", "bg2": "#f0e2cd", "text": "#4d3a22", "emoji": "🌾", "pattern": 9},
}

# Curated, lightweight emoji / ornament palette for the maker (also the whitelist
# used to validate stored values — prevents any CSS injection via the symbol).
INVITE_EMOJIS = [
    "🌸", "🌷", "🌹", "🌻", "🌼", "🪷", "💐", "🌺",
    "🌿", "🍃", "🍀", "🌾", "🕊️", "🦋", "🐝", "🌙",
    "❦", "❧", "❀", "✿", "❁", "✾", "♥", "❤️",
    "💕", "💞", "💍", "💎", "✨", "⭐", "🌟", "👑",
    "🥂", "🍾", "🎀", "🔔",
]


def invite_font_stack(key):
    return INVITE_FONTS.get(key or DEFAULT_INVITE_FONT, INVITE_FONTS[DEFAULT_INVITE_FONT])


def safe_emoji(value):
    """Only allow a symbol from our curated palette; anything else -> empty."""
    v = (value or "").strip()
    return v if v in INVITE_EMOJIS else ""


def clamp_pattern_opacity(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(30, n))


def pattern_data_uri(emoji):
    """A tileable SVG (one centred emoji) as a CSS url() — no image files needed."""
    if not emoji:
        return ""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='104' height='104'>"
        "<text x='52' y='66' font-size='38' text-anchor='middle'>" + emoji + "</text></svg>"
    )
    # Everything special is percent-encoded, so the result is safe unquoted in url().
    return "url(data:image/svg+xml," + urllib.parse.quote(svg) + ")"


def generate_invitation_token():
    return uuid.uuid4().hex


def today_iso():
    return date.today().isoformat()


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_email(email):
    return (email or "").strip().lower()


def get_diatrofi_options():
    return ["Δεν απάντησε", "Τα τρώω όλα", "Vegetarian", "Vegan", "Άλλη διατροφική προτίμηση"]


# -----------------------------
# i18n (lightweight JSON dictionaries; add a language by dropping in translations/<code>.json)
# -----------------------------
AVAILABLE_LANGUAGES = ["el", "en"]
DEFAULT_LANGUAGE = "el"


def _load_translations():
    loaded = {}
    tdir = os.path.join(app.root_path, "translations")
    for lang in AVAILABLE_LANGUAGES:
        try:
            with open(os.path.join(tdir, f"{lang}.json"), encoding="utf-8") as fh:
                loaded[lang] = json.load(fh)
        except (OSError, ValueError):
            loaded[lang] = {}
    return loaded


TRANSLATIONS = _load_translations()


def current_lang():
    lang = session.get("lang", DEFAULT_LANGUAGE)
    return lang if lang in AVAILABLE_LANGUAGES else DEFAULT_LANGUAGE


def t(key, **kwargs):
    lang = current_lang()
    text = TRANSLATIONS.get(lang, {}).get(key)
    if text is None:
        text = TRANSLATIONS.get(DEFAULT_LANGUAGE, {}).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def te(value):
    """Translate a stored Greek enum value (e.g. RSVP/gender/diet) for display only.
    Stored data stays Greek; this maps it to the active language, falling back to the value."""
    if value is None:
        return value
    lang = current_lang()
    if lang == DEFAULT_LANGUAGE:
        return value
    return TRANSLATIONS.get(lang, {}).get("enum", {}).get(value, value)


def table_names():
    if db.engine.url.get_backend_name().startswith("sqlite"):
        return [row[0] for row in db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
    return []


def ensure_sqlite_column(table, column, ddl):
    if not db.engine.url.get_backend_name().startswith("sqlite"):
        return
    if table not in table_names():
        return
    columns = [row[1] for row in db.session.execute(db.text(f"PRAGMA table_info({table})")).fetchall()]
    if column not in columns:
        db.session.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        db.session.commit()


def ensure_extra_columns():
    """Lightweight SQLite migration for existing local testing databases."""
    ensure_sqlite_column("omada", "wedding_id", "wedding_id INTEGER")
    ensure_sqlite_column("kalesmenos", "wedding_id", "wedding_id INTEGER")
    ensure_sqlite_column("glenti_state", "wedding_id", "wedding_id INTEGER")
    ensure_sqlite_column("budget_settings", "wedding_id", "wedding_id INTEGER")
    ensure_sqlite_column("wedding_settings", "wedding_id", "wedding_id INTEGER")
    ensure_sqlite_column("exodo", "wedding_id", "wedding_id INTEGER")
    ensure_sqlite_column("tragoudi", "wedding_id", "wedding_id INTEGER")

    ensure_sqlite_column("kalesmenos", "fylo", "fylo VARCHAR(20) DEFAULT 'Δεν ορίστηκε'")
    ensure_sqlite_column("kalesmenos", "einai_paidi", "einai_paidi BOOLEAN DEFAULT 0")
    ensure_sqlite_column("kalesmenos", "prosklitirio_stalthike", "prosklitirio_stalthike BOOLEAN DEFAULT 0")
    ensure_sqlite_column("kalesmenos", "invitation_token", "invitation_token VARCHAR(80)")
    ensure_sqlite_column("kalesmenos", "diatrofi", "diatrofi VARCHAR(50) DEFAULT 'Δεν απάντησε'")
    ensure_sqlite_column("kalesmenos", "diatrofi_sxolia", "diatrofi_sxolia TEXT")
    ensure_sqlite_column("kalesmenos", "rsvp_apantithike_at", "rsvp_apantithike_at VARCHAR(30)")

    for col, ddl in [
        ("background_image", "background_image VARCHAR(300)"),
        ("rsvp_deadline", "rsvp_deadline VARCHAR(20)"),
        ("oikogeneia_nyfis", "oikogeneia_nyfis VARCHAR(250) DEFAULT ''"),
        ("oikogeneia_gambrou", "oikogeneia_gambrou VARCHAR(250) DEFAULT ''"),
        ("iban_owner", "iban_owner VARCHAR(200) DEFAULT ''"),
        ("bank_name", "bank_name VARCHAR(150) DEFAULT ''"),
        ("iban", "iban VARCHAR(80) DEFAULT ''"),
        ("invite_template", "invite_template VARCHAR(50) DEFAULT 'romantic'"),
        ("invite_font", "invite_font VARCHAR(40) DEFAULT ''"),
        ("invite_color", "invite_color VARCHAR(20) DEFAULT ''"),
        ("invite_bg", "invite_bg VARCHAR(20) DEFAULT ''"),
        ("invite_bg2", "invite_bg2 VARCHAR(20) DEFAULT ''"),
        ("invite_text_color", "invite_text_color VARCHAR(20) DEFAULT ''"),
        ("invite_emoji", "invite_emoji VARCHAR(16) DEFAULT ''"),
        ("invite_pattern_opacity", "invite_pattern_opacity INTEGER DEFAULT 0"),
        ("ceremony_name", "ceremony_name VARCHAR(250) DEFAULT ''"),
        ("ceremony_address", "ceremony_address VARCHAR(350) DEFAULT ''"),
        ("ceremony_time", "ceremony_time VARCHAR(30) DEFAULT ''"),
        ("ceremony_maps_link", "ceremony_maps_link VARCHAR(500) DEFAULT ''"),
        ("reception_name", "reception_name VARCHAR(250) DEFAULT ''"),
        ("reception_address", "reception_address VARCHAR(350) DEFAULT ''"),
        ("reception_time", "reception_time VARCHAR(30) DEFAULT ''"),
        ("reception_maps_link", "reception_maps_link VARCHAR(500) DEFAULT ''"),
    ]:
        ensure_sqlite_column("wedding_settings", col, ddl)

    ensure_sqlite_column("wedding_settings", "side_nyfis", "side_nyfis VARCHAR(60) DEFAULT ''")
    ensure_sqlite_column("wedding_settings", "side_gambrou", "side_gambrou VARCHAR(60) DEFAULT ''")


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def user_weddings(user=None):
    user = user or current_user()
    if not user:
        return []
    return [m.wedding for m in WeddingMember.query.filter_by(user_id=user.id).all()]


def current_wedding():
    user = current_user()
    if not user:
        return None
    wedding_id = session.get("wedding_id")
    if wedding_id:
        member = WeddingMember.query.filter_by(user_id=user.id, wedding_id=wedding_id).first()
        if member:
            return member.wedding
    member = WeddingMember.query.filter_by(user_id=user.id).first()
    if member:
        session["wedding_id"] = member.wedding_id
        return member.wedding
    return None


def current_wedding_id():
    wedding = current_wedding()
    return wedding.id if wedding else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        if not current_wedding() and request.endpoint not in {"logout", "register"}:
            flash(t('flash.no_wedding_linked'), "error")
            return redirect(url_for("register"))
        return fn(*args, **kwargs)
    return wrapper


def auto_join_pending_weddings(user):
    """If a wedding has this email as partner_email, connect this user to it."""
    email = normalize_email(user.email)
    pending = Wedding.query.filter_by(partner_email=email).all()
    joined = 0
    for wedding in pending:
        exists = WeddingMember.query.filter_by(wedding_id=wedding.id, user_id=user.id).first()
        if not exists:
            db.session.add(WeddingMember(wedding_id=wedding.id, user_id=user.id, role="partner"))
            joined += 1
    if joined:
        db.session.commit()
    return joined


def adopt_orphan_data(wedding_id):
    """Attach old single-wedding local data to the first created wedding."""
    for model in [Omada, Kalesmenos, GlentiState, BudgetSettings, WeddingSettings, Exodo, Tragoudi]:
        try:
            model.query.filter(model.wedding_id.is_(None)).update({"wedding_id": wedding_id}, synchronize_session=False)
        except Exception:
            pass
    db.session.commit()


def get_wedding_settings():
    wid = current_wedding_id()
    settings = WeddingSettings.query.filter_by(wedding_id=wid).first()
    if not settings:
        wedding = current_wedding()
        settings = WeddingSettings(wedding_id=wid, onoma_zeugariou=wedding.title if wedding else "Ο γάμος μας")
        db.session.add(settings)
        db.session.commit()
    return settings


def get_budget_settings():
    wid = current_wedding_id()
    settings = BudgetSettings.query.filter_by(wedding_id=wid).first()
    if not settings:
        settings = BudgetSettings(wedding_id=wid, synoliko_budget=0)
        db.session.add(settings)
        db.session.commit()
    return settings


def get_glenti_state():
    wid = current_wedding_id()
    state = GlentiState.query.filter_by(wedding_id=wid).first()
    if not state:
        state = GlentiState(wedding_id=wid, objects_json="[]", assignments_json="{}")
        db.session.add(state)
        db.session.commit()
    return state


def is_rsvp_expired(settings):
    if not settings or not settings.rsvp_deadline:
        return False
    try:
        return date.today() > date.fromisoformat(settings.rsvp_deadline)
    except ValueError:
        return False


def days_until_wedding(settings):
    if not settings or not settings.imerominia_gamou:
        return None
    try:
        return (date.fromisoformat(settings.imerominia_gamou) - date.today()).days
    except ValueError:
        return None


def side_labels():
    wid = current_wedding_id()
    s = WeddingSettings.query.filter_by(wedding_id=wid).first() if wid else None
    return {
        "nyfis": (s.side_nyfis if s and s.side_nyfis else t("side.bride_label")),
        "gambrou": (s.side_gambrou if s and s.side_gambrou else t("side.groom_label")),
    }


def expense_categories():
    """Expense categories. The two attire ones follow the wedding's side names
    (same as πλευρές): custom names if set, otherwise the Greek defaults. Built
    from the RAW stored side value so the category stays canonical/Greek for storage
    and still translates via te() for the default case."""
    wid = current_wedding_id()
    s = WeddingSettings.query.filter_by(wedding_id=wid).first() if wid else None
    nyfis = (s.side_nyfis if s and s.side_nyfis else "Νύφης")
    gambrou = (s.side_gambrou if s and s.side_gambrou else "Γαμπρού")
    return [
        "Χώρος δεξίωσης", "Catering",
        "Ενδυμασία " + nyfis, "Ενδυμασία " + gambrou, "Κοσμήματα",
        "Φωτογράφος / Βιντεογράφος", "DJ / Μουσική", "Στολισμός",
        "Προσκλητήρια", "Μπομπονιέρες", "Εκκλησία / Δημαρχείο",
        "Μακιγιάζ / Μαλλιά", "Μεταφορές", "Λοιπά έξοδα",
    ]


@app.context_processor
def inject_globals():
    return {
        "logged_user": current_user(),
        "active_wedding": current_wedding(),
        "user_weddings": user_weddings(),
        "is_guest_mode": bool(session.get("guest_mode")),
        "invite_templates": INVITE_TEMPLATES,
        "invite_fonts": INVITE_FONTS,
        "invite_emojis": INVITE_EMOJIS,
        "pattern_data_uri": pattern_data_uri,
        "t": t,
        "te": te,
        "lang": current_lang(),
        "available_langs": AVAILABLE_LANGUAGES,
        "year": datetime.now().year,
        "sides": side_labels(),
    }


with app.app_context():
    db.create_all()
    ensure_extra_columns()
    for k in Kalesmenos.query.all():
        if not k.invitation_token:
            k.invitation_token = generate_invitation_token()
        if not k.diatrofi:
            k.diatrofi = "Δεν απάντησε"
    db.session.commit()


# -----------------------------
# Auth routes
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        partner_email = normalize_email(request.form.get("partner_email"))
        wedding_title = request.form.get("wedding_title", "Ο γάμος μας").strip() or "Ο γάμος μας"

        if not email or not password:
            flash(t('flash.fill_email_password'), "error")
            return redirect("/register")

        user = User.query.filter_by(email=email).first()
        if user:
            flash(t('flash.email_already_exists'), "error")
            return redirect("/login")

        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # If this email was declared as partner in an existing wedding, join that wedding.
        pending = Wedding.query.filter_by(partner_email=email).all()
        if pending and not partner_email:
            for wedding in pending:
                db.session.add(WeddingMember(wedding_id=wedding.id, user_id=user.id, role="partner"))
            db.session.commit()
            session["user_id"] = user.id
            session["wedding_id"] = pending[0].id
            flash(t('flash.account_created_joined_wedding'), "success")
            return redirect("/")

        if not partner_email:
            db.session.rollback()
            flash(t('flash.partner_email_required'), "error")
            return redirect("/register")

        wedding = Wedding(title=wedding_title, owner_email=email, partner_email=partner_email)
        db.session.add(wedding)
        db.session.flush()
        db.session.add(WeddingMember(wedding_id=wedding.id, user_id=user.id, role="owner"))
        db.session.commit()

        adopt_orphan_data(wedding.id)
        session["user_id"] = user.id
        session["wedding_id"] = wedding.id
        flash(t('flash.wedding_created'), "success")
        return redirect("/")

    suggested_email = normalize_email(request.args.get("email"))
    return render_template("register.html", suggested_email=suggested_email)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash(t('flash.wrong_credentials'), "error")
            return redirect("/login")

        auto_join_pending_weddings(user)
        session["user_id"] = user.id
        weddings = user_weddings(user)
        if weddings:
            session["wedding_id"] = weddings[0].id
        flash(t('flash.logged_in'), "success")
        return redirect(request.args.get("next") or "/")
    return render_template("login.html")


@app.route("/guest")
def guest_mode():
    """Temporary demo mode. Data is usable for testing but not meant as permanent storage."""
    email = f"guest_{uuid.uuid4().hex[:12]}@demo.local"
    user = User(email=email)
    user.set_password(uuid.uuid4().hex)
    db.session.add(user)
    db.session.flush()

    wedding = Wedding(
        title="Demo γάμος",
        owner_email=email,
        partner_email=f"partner_{uuid.uuid4().hex[:12]}@demo.local"
    )
    db.session.add(wedding)
    db.session.flush()
    db.session.add(WeddingMember(wedding_id=wedding.id, user_id=user.id, role="guest"))
    db.session.commit()

    session["user_id"] = user.id
    session["wedding_id"] = wedding.id
    session["guest_mode"] = True
    flash(t('flash.guest_mode_entered'), "success")
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    flash(t('flash.logged_out'), "success")
    return redirect("/login")


@app.route("/set_lang/<lang>")
def set_lang(lang):
    if lang in AVAILABLE_LANGUAGES:
        session["lang"] = lang
    return redirect(request.referrer or "/")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/robots.txt")
def robots():
    # Allow search engines to index the app, but keep guests' private RSVP links out.
    return "User-agent: *\nDisallow: /invite/\n", 200, {"Content-Type": "text/plain"}


@app.route("/download")
def download():
    # Public, shareable install page. Detects the platform client-side and either
    # triggers the native PWA prompt (Android / desktop Chrome-Edge) or shows
    # step-by-step install instructions (iPhone / other browsers).
    return render_template("download.html")


@app.route("/switch_wedding/<int:wedding_id>")
@login_required
def switch_wedding(wedding_id):
    member = WeddingMember.query.filter_by(user_id=current_user().id, wedding_id=wedding_id).first_or_404()
    session["wedding_id"] = member.wedding_id
    return redirect("/")


# -----------------------------
# Guests / groups
# -----------------------------
@app.route("/")
def home():
    # Public marketing landing page for logged-out visitors.
    if not current_user():
        return render_template("landing.html")
    # Logged in but no wedding linked yet → send to register (same as login_required).
    if not current_wedding():
        flash(t('flash.no_wedding_linked'), "error")
        return redirect(url_for("register"))
    wid = current_wedding_id()
    omades = Omada.query.filter_by(wedding_id=wid).order_by(Omada.pleura, Omada.onoma).all()
    kq = Kalesmenos.query.filter_by(wedding_id=wid)
    synolo_eggrafes = kq.count()
    plus_ones = db.session.query(db.func.sum(Kalesmenos.plus_one)).filter_by(wedding_id=wid).scalar() or 0
    synolo_atoma = synolo_eggrafes + plus_ones
    synolo_paidia = kq.filter_by(einai_paidi=True).count()
    prosklitiria = kq.filter_by(prosklitirio_stalthike=True).count()
    return render_template("index.html", omades=omades, synolo_eggrafes=synolo_eggrafes, synolo_atoma=synolo_atoma, synolo_paidia=synolo_paidia, prosklitiria=prosklitiria, diatrofi_options=get_diatrofi_options())


@app.route("/add_omada", methods=["POST"])
@login_required
def add_omada():
    db.session.add(Omada(wedding_id=current_wedding_id(), onoma=request.form["onoma"], pleura=request.form["pleura"]))
    db.session.commit()
    flash(t('flash.group_created'), "success")
    return redirect("/")


@app.route("/edit_omada/<int:id>", methods=["GET", "POST"])
@login_required
def edit_omada(id):
    o = Omada.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    if request.method == "POST":
        o.onoma = request.form["onoma"]
        o.pleura = request.form["pleura"]
        db.session.commit()
        flash(t('flash.group_updated'), "success")
        return redirect("/")
    return render_template("edit_omada.html", o=o)


@app.route("/delete_omada/<int:id>", methods=["POST"])
@login_required
def delete_omada(id):
    o = Omada.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    if len(o.kalesmeni) > 0:
        flash(t('flash.group_has_guests'), "error")
        return redirect("/")
    db.session.delete(o)
    db.session.commit()
    flash(t('flash.group_deleted'), "success")
    return redirect("/")


@app.route("/add_kalesmeno", methods=["POST"])
@login_required
def add_kalesmeno():
    omada = Omada.query.filter_by(id=request.form["omada_id"], wedding_id=current_wedding_id()).first_or_404()
    neos = Kalesmenos(
        wedding_id=current_wedding_id(),
        onoma=request.form["onoma"],
        tilefono=request.form.get("tilefono", ""),
        email=request.form.get("email", ""),
        rsvp="Δεν έχει απαντήσει",
        omada_id=omada.id,
        plus_one=int(request.form.get("plus_one", 0) or 0),
        fylo=request.form.get("fylo", "Δεν ορίστηκε"),
        einai_paidi="einai_paidi" in request.form,
        prosklitirio_stalthike=False,
        invitation_token=generate_invitation_token(),
        diatrofi="Δεν απάντησε"
    )
    db.session.add(neos)
    db.session.commit()
    flash(t('flash.guest_added'), "success")
    return redirect("/")


@app.route("/delete_kalesmeno/<int:id>", methods=["POST"])
@login_required
def delete_kalesmeno(id):
    k = Kalesmenos.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    db.session.delete(k)
    db.session.commit()
    flash(t('flash.guest_deleted'), "success")
    return redirect("/")


@app.route("/edit_kalesmeno/<int:id>", methods=["GET", "POST"])
@login_required
def edit_kalesmeno(id):
    k = Kalesmenos.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    omades = Omada.query.filter_by(wedding_id=current_wedding_id()).all()
    if request.method == "POST":
        omada = Omada.query.filter_by(id=request.form["omada_id"], wedding_id=current_wedding_id()).first_or_404()
        k.onoma = request.form["onoma"]
        k.tilefono = request.form.get("tilefono", "")
        k.email = request.form.get("email", "")
        k.rsvp = request.form["rsvp"]
        k.omada_id = omada.id
        k.plus_one = int(request.form.get("plus_one", 0) or 0)
        k.fylo = request.form.get("fylo", "Δεν ορίστηκε")
        k.einai_paidi = "einai_paidi" in request.form
        k.prosklitirio_stalthike = "prosklitirio_stalthike" in request.form
        k.diatrofi = request.form.get("diatrofi", "Δεν απάντησε")
        k.diatrofi_sxolia = request.form.get("diatrofi_sxolia", "")
        if k.rsvp != "Δεν έχει απαντήσει" and not k.rsvp_apantithike_at:
            k.rsvp_apantithike_at = now_iso()
        if not k.invitation_token:
            k.invitation_token = generate_invitation_token()
        db.session.commit()
        flash(t('flash.guest_updated'), "success")
        return redirect("/")
    return render_template("edit.html", k=k, omades=omades, diatrofi_options=get_diatrofi_options())


@app.route("/toggle_prosklitirio/<int:id>", methods=["POST"])
@login_required
def toggle_prosklitirio(id):
    k = Kalesmenos.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    k.prosklitirio_stalthike = "prosklitirio_stalthike" in request.form
    db.session.commit()
    return redirect("/")


# -----------------------------
# Glenti
# -----------------------------
@app.route("/glenti")
@login_required
def glenti():
    state = get_glenti_state()
    try:
        objects = json.loads(state.objects_json)
    except Exception:
        objects = []
    try:
        assignments = json.loads(state.assignments_json)
    except Exception:
        assignments = {}

    kalesmenoi = Kalesmenos.query.filter_by(wedding_id=current_wedding_id()).order_by(Kalesmenos.onoma).all()
    guest_list = [{"id": k.id, "onoma": k.onoma, "plus_one": k.plus_one or 0, "synolo": 1 + (k.plus_one or 0), "omada": k.omada.onoma if k.omada else "", "fylo": k.fylo or "Δεν ορίστηκε", "einai_paidi": bool(k.einai_paidi), "diatrofi": k.diatrofi or "Δεν απάντησε"} for k in kalesmenoi]
    return render_template("glenti.html", objects=objects, assignments=assignments, guests=guest_list)


@app.route("/save_glenti", methods=["POST"])
@login_required
def save_glenti():
    data = request.get_json() or {}
    state = get_glenti_state()
    state.objects_json = json.dumps(data.get("objects", []), ensure_ascii=False)
    state.assignments_json = json.dumps(data.get("assignments", {}), ensure_ascii=False)
    db.session.commit()
    return jsonify({"status": "ok"})


# -----------------------------
# Oikonomika
# -----------------------------
@app.route("/oikonomika")
@login_required
def oikonomika():
    settings = get_budget_settings()
    exoda = Exodo.query.filter_by(wedding_id=current_wedding_id()).order_by(Exodo.katigoria, Exodo.perigrafi).all()
    synoliko_budget = settings.synoliko_budget or 0
    synoliko_ektimomeno = sum(e.ektimomeno_kostos or 0 for e in exoda)
    synoliko_teliko = sum(e.teliko_kostos or 0 for e in exoda)
    synoliko_plirothike = sum(e.plirothike or 0 for e in exoda)
    synoliko_ypoloipo = sum(e.ypoloipo() for e in exoda)
    diafora_budget = synoliko_budget - synoliko_teliko
    return render_template("oikonomika.html", exoda=exoda, katigories=expense_categories(), synoliko_budget=synoliko_budget, synoliko_ektimomeno=synoliko_ektimomeno, synoliko_teliko=synoliko_teliko, synoliko_plirothike=synoliko_plirothike, synoliko_ypoloipo=synoliko_ypoloipo, diafora_budget=diafora_budget)


@app.route("/update_budget", methods=["POST"])
@login_required
def update_budget():
    settings = get_budget_settings()
    settings.synoliko_budget = float(request.form.get("synoliko_budget") or 0)
    db.session.commit()
    flash(t('flash.budget_updated'), "success")
    return redirect("/oikonomika")


@app.route("/add_exodo", methods=["POST"])
@login_required
def add_exodo():
    ex = Exodo(wedding_id=current_wedding_id(), perigrafi=request.form["perigrafi"], katigoria=request.form["katigoria"], promithiefthis=request.form.get("promithiefthis", ""), ektimomeno_kostos=float(request.form.get("ektimomeno_kostos") or 0), teliko_kostos=float(request.form.get("teliko_kostos") or 0), plirothike=float(request.form.get("plirothike") or 0), imerominia_pliromis=request.form.get("imerominia_pliromis", ""), sxolia=request.form.get("sxolia", ""))
    db.session.add(ex)
    db.session.commit()
    flash(t('flash.expense_added'), "success")
    return redirect("/oikonomika")


@app.route("/delete_exodo/<int:id>", methods=["POST"])
@login_required
def delete_exodo(id):
    exodo = Exodo.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    db.session.delete(exodo)
    db.session.commit()
    flash(t('flash.expense_deleted'), "success")
    return redirect("/oikonomika")


@app.route("/edit_exodo/<int:id>", methods=["GET", "POST"])
@login_required
def edit_exodo(id):
    exodo = Exodo.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    if request.method == "POST":
        exodo.perigrafi = request.form["perigrafi"]
        exodo.katigoria = request.form["katigoria"]
        exodo.promithiefthis = request.form.get("promithiefthis", "")
        exodo.ektimomeno_kostos = float(request.form.get("ektimomeno_kostos") or 0)
        exodo.teliko_kostos = float(request.form.get("teliko_kostos") or 0)
        exodo.plirothike = float(request.form.get("plirothike") or 0)
        exodo.imerominia_pliromis = request.form.get("imerominia_pliromis", "")
        exodo.sxolia = request.form.get("sxolia", "")
        db.session.commit()
        flash(t('flash.expense_updated'), "success")
        return redirect("/oikonomika")
    return render_template("edit_exodo.html", exodo=exodo, katigories=expense_categories())


# -----------------------------
# Analytics / settings / invite
# -----------------------------
@app.route("/analytics")
@login_required
def analytics():
    wid = current_wedding_id()
    kalesmenoi = Kalesmenos.query.filter_by(wedding_id=wid).all()
    omades = Omada.query.filter_by(wedding_id=wid).all()
    synolo_eggrafes = len(kalesmenoi)
    synolo_atoma = sum(1 + (k.plus_one or 0) for k in kalesmenoi)
    synolo_paidia = sum(1 for k in kalesmenoi if k.einai_paidi)
    prosklitiria = sum(1 for k in kalesmenoi if k.prosklitirio_stalthike)
    apantisan = sum(1 for k in kalesmenoi if k.rsvp != "Δεν έχει απαντήσει")
    den_apantisan = synolo_eggrafes - apantisan
    fylo_counts = {"Άνδρες": sum(1 for k in kalesmenoi if k.fylo == "Άνδρας"), "Γυναίκες": sum(1 for k in kalesmenoi if k.fylo == "Γυναίκα"), "Δεν ορίστηκε": sum(1 for k in kalesmenoi if not k.fylo or k.fylo == "Δεν ορίστηκε")}
    sl = side_labels()
    pleura_counts = {sl["nyfis"]: sum(1 + (k.plus_one or 0) for k in kalesmenoi if k.omada and k.omada.pleura == "nyfis"), sl["gambrou"]: sum(1 + (k.plus_one or 0) for k in kalesmenoi if k.omada and k.omada.pleura == "gambrou")}
    rsvp_counts = {"Έρχεται": sum(1 for k in kalesmenoi if k.rsvp == "Έρχεται"), "Δεν έρχεται": sum(1 for k in kalesmenoi if k.rsvp == "Δεν έρχεται"), "Δεν έχει απαντήσει": sum(1 for k in kalesmenoi if k.rsvp == "Δεν έχει απαντήσει")}
    diatrofi_counts = {opt: sum(1 for k in kalesmenoi if (k.diatrofi or "Δεν απάντησε") == opt) for opt in get_diatrofi_options()}
    omada_rows = [{"onoma": o.onoma, "pleura": sl["nyfis"] if o.pleura == "nyfis" else sl["gambrou"], "eggrafes": len(o.kalesmeni), "atoma": o.synolo_atoma(), "paidia": sum(1 for k in o.kalesmeni if k.einai_paidi), "prosklitiria": sum(1 for k in o.kalesmeni if k.prosklitirio_stalthike), "apantisan": sum(1 for k in o.kalesmeni if k.rsvp != "Δεν έχει απαντήσει"), "erxontai": sum(1 for k in o.kalesmeni if k.rsvp == "Έρχεται")} for o in omades]
    return render_template("analytics.html", synolo_eggrafes=synolo_eggrafes, synolo_atoma=synolo_atoma, synolo_paidia=synolo_paidia, prosklitiria=prosklitiria, apantisan=apantisan, den_apantisan=den_apantisan, fylo_counts=fylo_counts, pleura_counts=pleura_counts, rsvp_counts=rsvp_counts, diatrofi_counts=diatrofi_counts, omada_rows=omada_rows)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    settings = get_wedding_settings()
    if request.method == "POST":
        for field in [
            "onoma_zeugariou", "imerominia_gamou", "ora_gamou", "topothesia", "maps_link",
            "koumparoi", "oikogeneia_nyfis", "oikogeneia_gambrou", "iban_owner",
            "bank_name", "iban", "minima", "rsvp_deadline", "invite_template",
            "invite_font", "invite_color", "invite_bg", "invite_bg2", "invite_text_color",
            "ceremony_name", "ceremony_address", "ceremony_time", "ceremony_maps_link",
            "reception_name", "reception_address", "reception_time", "reception_maps_link",
            "side_nyfis", "side_gambrou",
        ]:
            setattr(settings, field, request.form.get(field, ""))
        # Validate the custom-maker fields so only known fonts / real hex colours are stored.
        if settings.invite_font not in INVITE_FONTS:
            settings.invite_font = ""
        settings.invite_color = safe_hex(settings.invite_color)
        settings.invite_bg = safe_hex(settings.invite_bg)
        settings.invite_text_color = safe_hex(settings.invite_text_color)
        # Second background colour only kept when the gradient toggle is on.
        settings.invite_bg2 = safe_hex(settings.invite_bg2) if request.form.get("invite_gradient") else ""
        settings.invite_emoji = safe_emoji(request.form.get("invite_emoji"))
        settings.invite_pattern_opacity = clamp_pattern_opacity(request.form.get("invite_pattern_opacity"))
        file = request.files.get("background_image")
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                final_name = f"invite_bg_{current_wedding_id()}_{uuid.uuid4().hex}{ext}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], final_name))
                settings.background_image = final_name
            else:
                flash(t('flash.invalid_image_type'), "error")
                return redirect("/settings")
        wedding = current_wedding()
        wedding.title = settings.onoma_zeugariou or wedding.title
        db.session.commit()
        flash(t('flash.settings_saved'), "success")
        return redirect("/settings")
    return render_template(
        "settings.html",
        settings=settings,
        days_until=days_until_wedding(settings),
        templates=INVITE_TEMPLATES,
        fonts=INVITE_FONTS,
        presets=INVITE_PRESETS,
        emojis=INVITE_EMOJIS,
        default_font=DEFAULT_INVITE_FONT,
    )


@app.route("/invite_preview")
@login_required
def invite_preview():
    settings = get_wedding_settings()
    # Live preview: query params preview a look WITHOUT saving it. Fall back to the saved values.
    requested = request.args.get("template")
    preview_template = requested if requested in INVITE_TEMPLATES else None
    class FakeGuest:
        onoma = "Παράδειγμα Καλεσμένου"
        rsvp = "Δεν έχει απαντήσει"
        plus_one = 0
        diatrofi = "Δεν απάντησε"
        diatrofi_sxolia = ""
    return render_template(
        "invite.html",
        k=FakeGuest(),
        settings=settings,
        days_until=days_until_wedding(settings),
        expired=False,
        diatrofi_options=get_diatrofi_options(),
        preview=True,
        preview_template=preview_template,
        preview_font=(request.args.get("font") if request.args.get("font") in INVITE_FONTS else None),
        preview_color=(safe_hex(request.args.get("color")) or None),
        preview_bg=(safe_hex(request.args.get("bg")) or None),
        preview_bg2=(safe_hex(request.args.get("bg2")) or None),
        preview_text=(safe_hex(request.args.get("text")) or None),
        preview_emoji=(safe_emoji(request.args.get("emoji")) or None),
        preview_pattern=(clamp_pattern_opacity(request.args.get("pattern")) if request.args.get("pattern") is not None else None),
    )


@app.route("/invite/<token>", methods=["GET", "POST"])
def invite(token):
    k = Kalesmenos.query.filter_by(invitation_token=token).first_or_404()
    settings = WeddingSettings.query.filter_by(wedding_id=k.wedding_id).first()
    if not settings:
        settings = WeddingSettings(wedding_id=k.wedding_id)
        db.session.add(settings)
        db.session.commit()
    if is_rsvp_expired(settings):
        return render_template("invite_expired.html", k=k, settings=settings, days_until=days_until_wedding(settings))
    if request.method == "POST":
        apantisi = request.form.get("rsvp")
        if apantisi == "yes":
            k.rsvp = "Έρχεται"
            k.plus_one = int(request.form.get("plus_one", 0) or 0)
            k.diatrofi = request.form.get("diatrofi", "Δεν απάντησε")
            k.diatrofi_sxolia = request.form.get("diatrofi_sxolia", "")
        elif apantisi == "no":
            k.rsvp = "Δεν έρχεται"
            k.plus_one = 0
            k.diatrofi = "Δεν απάντησε"
            k.diatrofi_sxolia = ""
        else:
            k.rsvp = "Δεν έχει απαντήσει"
        k.rsvp_apantithike_at = now_iso()
        db.session.commit()
        return render_template("invite_thanks.html", k=k, settings=settings, days_until=days_until_wedding(settings))
    return render_template("invite.html", k=k, settings=settings, days_until=days_until_wedding(settings), expired=False, diatrofi_options=get_diatrofi_options(), preview=False)


# -----------------------------
# PWA service worker (served at root so its scope is the whole site)
# -----------------------------
@app.route("/service-worker.js")
def service_worker():
    resp = app.send_static_file("service-worker.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# -----------------------------
# Backup per wedding
# -----------------------------
def model_to_dict(obj, fields):
    return {field: getattr(obj, field) for field in fields}


@app.route("/backup")
@login_required
def backup_page():
    return render_template("backup.html")


@app.route("/export_data")
@login_required
def export_data():
    wid = current_wedding_id()
    data = {
        "version": 4,
        "exported_at": now_iso(),
        "wedding": model_to_dict(current_wedding(), ["id", "title", "owner_email", "partner_email", "created_at"]),
        "omades": [model_to_dict(o, ["id", "wedding_id", "onoma", "pleura"]) for o in Omada.query.filter_by(wedding_id=wid).all()],
        "kalesmenoi": [model_to_dict(k, ["id", "wedding_id", "onoma", "tilefono", "email", "rsvp", "plus_one", "fylo", "einai_paidi", "prosklitirio_stalthike", "invitation_token", "diatrofi", "diatrofi_sxolia", "rsvp_apantithike_at", "omada_id"]) for k in Kalesmenos.query.filter_by(wedding_id=wid).all()],
        "glenti_state": [model_to_dict(g, ["id", "wedding_id", "objects_json", "assignments_json"]) for g in GlentiState.query.filter_by(wedding_id=wid).all()],
        "budget_settings": [model_to_dict(b, ["id", "wedding_id", "synoliko_budget"]) for b in BudgetSettings.query.filter_by(wedding_id=wid).all()],
        "wedding_settings": [model_to_dict(w, ["id", "wedding_id", "onoma_zeugariou", "imerominia_gamou", "ora_gamou", "topothesia", "maps_link", "koumparoi", "oikogeneia_nyfis", "oikogeneia_gambrou", "iban_owner", "bank_name", "iban", "minima", "background_image", "rsvp_deadline", "invite_template", "invite_font", "invite_color", "invite_bg", "invite_bg2", "invite_text_color", "invite_emoji", "invite_pattern_opacity", "ceremony_name", "ceremony_address", "ceremony_time", "ceremony_maps_link", "reception_name", "reception_address", "reception_time", "reception_maps_link", "side_nyfis", "side_gambrou"]) for w in WeddingSettings.query.filter_by(wedding_id=wid).all()],
        "exoda": [model_to_dict(e, ["id", "wedding_id", "perigrafi", "katigoria", "promithiefthis", "ektimomeno_kostos", "teliko_kostos", "plirothike", "imerominia_pliromis", "sxolia"]) for e in Exodo.query.filter_by(wedding_id=wid).all()],
        "tragoudia": [model_to_dict(t, ["id", "wedding_id", "titlos", "kallitechnis", "katigoria", "link", "sxolia"]) for t in Tragoudi.query.filter_by(wedding_id=wid).all()]
    }
    buffer = BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return send_file(buffer, mimetype="application/json", as_attachment=True, download_name=f"gamos_backup_{date.today().isoformat()}.json")


@app.route("/import_data", methods=["POST"])
@login_required
def import_data():
    file = request.files.get("backup_file")
    if not file or not file.filename:
        flash(t('flash.no_backup_file'), "error")
        return redirect("/backup")
    try:
        data = json.load(file)
    except Exception:
        flash(t('flash.invalid_backup_file'), "error")
        return redirect("/backup")

    wid = current_wedding_id()
    try:
        # Διαγράφει μόνο τα δεδομένα του τρέχοντος γάμου, όχι άλλων χρηστών.
        Kalesmenos.query.filter_by(wedding_id=wid).delete()
        Omada.query.filter_by(wedding_id=wid).delete()
        GlentiState.query.filter_by(wedding_id=wid).delete()
        BudgetSettings.query.filter_by(wedding_id=wid).delete()
        WeddingSettings.query.filter_by(wedding_id=wid).delete()
        Exodo.query.filter_by(wedding_id=wid).delete()
        Tragoudi.query.filter_by(wedding_id=wid).delete()
        db.session.commit()

        omada_id_map = {}
        guest_id_map = {}

        for row in data.get("omades", []):
            old_id = row.get("id")
            obj = Omada(wedding_id=wid, onoma=row.get("onoma") or "Ομάδα", pleura=row.get("pleura") or "nyfis")
            db.session.add(obj)
            db.session.flush()
            omada_id_map[str(old_id)] = obj.id
            omada_id_map[old_id] = obj.id

        for row in data.get("kalesmenoi", []):
            old_guest_id = row.get("id")
            old_omada_id = row.get("omada_id")
            mapped_omada_id = omada_id_map.get(old_omada_id) or omada_id_map.get(str(old_omada_id))
            if not mapped_omada_id:
                # Safety fallback: create a default group if backup is incomplete.
                default_group = Omada.query.filter_by(wedding_id=wid, onoma="Χωρίς ομάδα").first()
                if not default_group:
                    default_group = Omada(wedding_id=wid, onoma="Χωρίς ομάδα", pleura="nyfis")
                    db.session.add(default_group)
                    db.session.flush()
                mapped_omada_id = default_group.id

            guest = Kalesmenos(
                wedding_id=wid,
                onoma=row.get("onoma") or "Καλεσμένος",
                tilefono=row.get("tilefono", ""),
                email=row.get("email", ""),
                rsvp=row.get("rsvp", "Δεν έχει απαντήσει"),
                plus_one=row.get("plus_one") or 0,
                fylo=row.get("fylo") or "Δεν ορίστηκε",
                einai_paidi=bool(row.get("einai_paidi")),
                prosklitirio_stalthike=bool(row.get("prosklitirio_stalthike")),
                invitation_token=row.get("invitation_token") or generate_invitation_token(),
                diatrofi=row.get("diatrofi") or "Δεν απάντησε",
                diatrofi_sxolia=row.get("diatrofi_sxolia", ""),
                rsvp_apantithike_at=row.get("rsvp_apantithike_at"),
                omada_id=mapped_omada_id
            )
            db.session.add(guest)
            db.session.flush()
            guest_id_map[str(old_guest_id)] = guest.id
            guest_id_map[old_guest_id] = guest.id

        for row in data.get("glenti_state", []):
            objects_json = row.get("objects_json", "[]")
            assignments_json = row.get("assignments_json", "{}")
            try:
                assignments = json.loads(assignments_json)
                remapped = {}
                for old_guest_id, object_id in assignments.items():
                    new_guest_id = guest_id_map.get(old_guest_id) or guest_id_map.get(str(old_guest_id))
                    if new_guest_id:
                        remapped[str(new_guest_id)] = object_id
                assignments_json = json.dumps(remapped, ensure_ascii=False)
            except Exception:
                assignments_json = "{}"
            db.session.add(GlentiState(wedding_id=wid, objects_json=objects_json, assignments_json=assignments_json))

        for row in data.get("budget_settings", []):
            db.session.add(BudgetSettings(wedding_id=wid, synoliko_budget=row.get("synoliko_budget", 0)))

        for row in data.get("wedding_settings", []):
            clean = {k: row.get(k) for k in ["onoma_zeugariou", "imerominia_gamou", "ora_gamou", "topothesia", "maps_link", "koumparoi", "oikogeneia_nyfis", "oikogeneia_gambrou", "iban_owner", "bank_name", "iban", "minima", "background_image", "rsvp_deadline", "invite_template", "invite_font", "invite_color", "invite_bg", "invite_bg2", "invite_text_color", "invite_emoji", "invite_pattern_opacity", "ceremony_name", "ceremony_address", "ceremony_time", "ceremony_maps_link", "reception_name", "reception_address", "reception_time", "reception_maps_link", "side_nyfis", "side_gambrou"] if row.get(k) is not None}
            clean["wedding_id"] = wid
            db.session.add(WeddingSettings(**clean))

        for row in data.get("exoda", []):
            clean = {k: row.get(k) for k in ["perigrafi", "katigoria", "promithiefthis", "ektimomeno_kostos", "teliko_kostos", "plirothike", "imerominia_pliromis", "sxolia"]}
            clean["wedding_id"] = wid
            db.session.add(Exodo(**clean))

        for row in data.get("tragoudia", []):
            clean = {k: row.get(k) for k in ["titlos", "kallitechnis", "katigoria", "link", "sxolia"]}
            clean["wedding_id"] = wid
            db.session.add(Tragoudi(**clean))

        db.session.commit()
        flash(t('flash.import_success'), "success")
    except Exception as e:
        db.session.rollback()
        flash(t('flash.import_failed', error=e), "error")
    return redirect("/backup")


# -----------------------------
# Playlist
# -----------------------------
@app.route("/playlist")
@login_required
def playlist():
    tragoudia = Tragoudi.query.filter_by(wedding_id=current_wedding_id()).order_by(Tragoudi.katigoria, Tragoudi.titlos).all()
    tragoudia_ana_katigoria = {kat: [] for kat in KATIGORIES_MOUSIKIS}
    for t in tragoudia:
        tragoudia_ana_katigoria.setdefault(t.katigoria, []).append(t)
    return render_template("playlist.html", katigories_mousikis=KATIGORIES_MOUSIKIS, tragoudia_ana_katigoria=tragoudia_ana_katigoria)


@app.route("/export_playlist")
@login_required
def export_playlist():
    """Plain-text playlist export to hand to the DJ."""
    wid = current_wedding_id()
    songs = Tragoudi.query.filter_by(wedding_id=wid).order_by(Tragoudi.katigoria, Tragoudi.titlos).all()
    settings = get_wedding_settings()
    header = settings.onoma_zeugariou or "Ceremonio"
    lines = [f"PLAYLIST - {header}", "=" * 44, ""]
    extra = [c for c in {s.katigoria for s in songs} if c not in KATIGORIES_MOUSIKIS]
    for kat in list(KATIGORIES_MOUSIKIS) + extra:
        group = [s for s in songs if s.katigoria == kat]
        if not group:
            continue
        label = te(kat)
        lines.append(label.upper())
        lines.append("-" * max(3, len(label)))
        for i, s in enumerate(group, 1):
            row = f"{i}. {s.titlos}"
            if s.kallitechnis:
                row += f" - {s.kallitechnis}"
            lines.append(row)
            if s.link:
                lines.append(f"   {s.link}")
            if s.sxolia:
                lines.append(f"   * {s.sxolia}")
        lines.append("")
    if not songs:
        lines.append("(empty)")
    buf = BytesIO("\n".join(lines).encode("utf-8"))
    return send_file(buf, mimetype="text/plain; charset=utf-8", as_attachment=True,
                     download_name=f"ceremio_playlist_{date.today().isoformat()}.txt")


@app.route("/add_tragoudi", methods=["POST"])
@login_required
def add_tragoudi():
    db.session.add(Tragoudi(wedding_id=current_wedding_id(), titlos=request.form["titlos"], kallitechnis=request.form.get("kallitechnis", ""), katigoria=request.form["katigoria"], link=request.form.get("link", ""), sxolia=request.form.get("sxolia", "")))
    db.session.commit()
    flash(t('flash.song_added'), "success")
    return redirect("/playlist")


@app.route("/delete_tragoudi/<int:id>", methods=["POST"])
@login_required
def delete_tragoudi(id):
    tragoudi = Tragoudi.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    db.session.delete(tragoudi)
    db.session.commit()
    flash(t('flash.song_deleted'), "success")
    return redirect("/playlist")


@app.route("/edit_tragoudi/<int:id>", methods=["GET", "POST"])
@login_required
def edit_tragoudi(id):
    tragoudi = Tragoudi.query.filter_by(id=id, wedding_id=current_wedding_id()).first_or_404()
    if request.method == "POST":
        tragoudi.titlos = request.form["titlos"]
        tragoudi.kallitechnis = request.form.get("kallitechnis", "")
        tragoudi.katigoria = request.form["katigoria"]
        tragoudi.link = request.form.get("link", "")
        tragoudi.sxolia = request.form.get("sxolia", "")
        db.session.commit()
        flash(t('flash.song_updated'), "success")
        return redirect("/playlist")
    return render_template("edit_tragoudi.html", tragoudi=tragoudi, katigories_mousikis=KATIGORIES_MOUSIKIS)


if __name__ == "__main__":
    # Watch translation files + CSS so dev edits trigger an auto-reload too.
    extra_files = [os.path.join(app.root_path, "translations", f"{lang}.json") for lang in AVAILABLE_LANGUAGES]
    extra_files.append(os.path.join(app.root_path, "static", "app.css"))
    app.run(debug=True, extra_files=extra_files)
