"""
Django settings for tt_osint project.
Trinidad Incident Intelligence Map
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root so local env vars (e.g. DATABASE_URL, ALLOWED_HOSTS) are used.
# override=True so .env wins over existing env vars (e.g. production ALLOWED_HOSTS when running locally).
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except ImportError:
        pass


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


# ──────────── Core ────────────
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-tt-osint-dev-key-change-in-production-2026",
)
DEBUG = _env_bool("DJANGO_DEBUG", "true")

_allowed = os.environ.get("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()] if _allowed else ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    # Project apps
    'core',
    'articles',
    'incidents',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tt_osint.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.seo_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'tt_osint.wsgi.application'

# Database: use DATABASE_URL (PostgreSQL), or POSTGRES_* vars, or SQLite
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(_db_url)}
elif os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "tt_osint"),
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "OPTIONS": {"sslmode": os.environ.get("POSTGRES_SSLMODE", "prefer")},
        }
    }
else:
    # SQLite: explicit path, or data/db.sqlite3 (pushed to git), or writable dir, or cloud /tmp, else project root.
    # On cloud, use /tmp so the DB is writable; copy bundled DB if present, else use/create /tmp/db.sqlite3.
    _bundled_db = BASE_DIR / "data" / "db.sqlite3"
    _on_cloud = bool(os.environ.get("PORT") or os.environ.get("DYNO") or os.environ.get("HEROKU_APP_NAME"))
    _tmp_db = os.path.join(os.environ.get("TMPDIR", "/tmp"), "db.sqlite3")

    def _is_valid_sqlite(path: str) -> bool:
        if not path or not os.path.isfile(path):
            return False
        try:
            import sqlite3
            with sqlite3.connect(path) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _ensure_writable_sqlite(path: str) -> None:
        if os.path.isfile(path) and not _is_valid_sqlite(path):
            try:
                os.remove(path)
            except OSError:
                pass

    _sqlite_path_env = os.environ.get("SQLITE_DB_PATH")
    if _sqlite_path_env:
        _sqlite_path = _sqlite_path_env
    elif _bundled_db.exists():
        if _on_cloud:
            import shutil
            shutil.copy2(str(_bundled_db), _tmp_db)
            _ensure_writable_sqlite(_tmp_db)
            _sqlite_path = _tmp_db
        else:
            _sqlite_path = str(_bundled_db)
    else:
        _sqlite_dir = os.environ.get("SQLITE_DB_DIR")
        if _sqlite_dir:
            _sqlite_path = os.path.join(_sqlite_dir, "db.sqlite3")
        elif _on_cloud:
            _ensure_writable_sqlite(_tmp_db)
            _sqlite_path = _tmp_db
        else:
            _sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _sqlite_path,
        }
    }

# If PostgreSQL and PG_SCHEMA is set, use that schema (avoids "permission denied for schema public" on managed DBs).
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    _pg_schema = os.environ.get("PG_SCHEMA", "").strip()
    if _pg_schema:
        if "OPTIONS" not in DATABASES["default"]:
            DATABASES["default"]["OPTIONS"] = {}
        DATABASES["default"]["OPTIONS"]["options"] = f"-c search_path={_pg_schema}"

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Port_of_Spain'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'core' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ──────────── Production security (when DEBUG is False) ────────────
_is_local = any(h in ("127.0.0.1", "localhost") for h in ALLOWED_HOSTS)
if not DEBUG:
    if "django-insecure-" in SECRET_KEY:
        raise ValueError("Set DJANGO_SECRET_KEY in production and do not use the default dev key.")
    if "*" in ALLOWED_HOSTS:
        raise ValueError("Set ALLOWED_HOSTS in production (comma-separated hostnames).")
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Only redirect to HTTPS when not on localhost (so local runserver over HTTP works).
    if not _is_local and os.environ.get("DJANGO_HTTPS_ONLY", "true").lower() in ("1", "true", "yes"):
        SECURE_SSL_REDIRECT = True

# ──────────── Logging (see 500 errors in console / DO logs) ────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"level": "ERROR", "handlers": ["console"], "propagate": False},
    },
}

# ──────────── Application Config ────────────
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3')
OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
NOMINATIM_USER_AGENT = 'tt-osint-intelligence-map/1.0'
