"""Database initialization and connection. Supports SQLite (local) and PostgreSQL (Railway)."""
import os
import sqlite3
from contextlib import contextmanager

from settings import DB_PATH, DATABASE_URL

# Ensure data directory exists for SQLite
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Detect which database to use
USE_PG = bool(DATABASE_URL)

# ---------------------------------------------------------------------------
# PostgreSQL wrapper: auto-convert ? placeholders to %s and return dict rows
# ---------------------------------------------------------------------------
class _PgCursor:
    """Wrap a psycopg2 cursor so it behaves like sqlite3 (dict rows, ? placeholders)."""

    def __init__(self, conn, cur):
        self._conn = conn
        self._cur = cur
        self._lastrowid = None

    def execute(self, sql: str, params=None):
        sql = sql.replace("?", "%s")
        self._cur.execute(sql, params or ())
        self._lastrowid = self._cur.lastrowid
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None or self._cur.description is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return dict(zip(cols, row))

    def fetchall(self):
        rows = self._cur.fetchall()
        if self._cur.description is None:
            return []
        cols = [d[0] for d in self._cur.description]
        return [dict(zip(cols, r)) for r in rows]

    @property
    def lastrowid(self):
        return self._lastrowid

    def close(self):
        self._cur.close()
        self._conn.close()


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    """Return a db connection/cursor compatible with both SQLite and PostgreSQL."""
    if USE_PG:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        db = _PgCursor(conn, cur)
        try:
            yield db
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            db.close()
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        class _SQLiteWrapper:
            def __init__(self, conn):
                self._conn = conn
                self.lastrowid = None

            def execute(self, sql, params=None):
                cur = self._conn.execute(sql, params or ())
                self.lastrowid = cur.lastrowid
                self._cur = cur
                return self

            def fetchone(self):
                row = self._cur.fetchone()
                return dict(row) if row else None

            def fetchall(self):
                return [dict(r) for r in self._cur.fetchall()]

        db = _SQLiteWrapper(conn)
        try:
            yield db
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def init_db():
    """Create all tables if they don't exist."""
    with get_db() as db:
        if USE_PG:
            _init_pg_schema(db)
        else:
            _init_sqlite_schema(db)


def _init_pg_schema(db):
    """PostgreSQL-compatible schema."""
    db.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        address TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(255) UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        full_name VARCHAR(255) DEFAULT '',
        role VARCHAR(50) NOT NULL DEFAULT 'STAFF' CHECK(role IN ('STAFF','MANAGER','OWNER')),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS user_locations (
        user_id INTEGER NOT NULL REFERENCES users(id),
        location_id INTEGER NOT NULL REFERENCES locations(id),
        PRIMARY KEY (user_id, location_id)
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        code VARCHAR(50) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        phone VARCHAR(50) DEFAULT '',
        email VARCHAR(255) DEFAULT '',
        notes TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT,
        UNIQUE (location_id, code)
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS drinks (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name VARCHAR(255) NOT NULL,
        price_per_serving REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS ingredients (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name VARCHAR(255) NOT NULL,
        unit VARCHAR(50) NOT NULL DEFAULT 'muỗng' CHECK(unit IN ('muỗng','nắp','gói')),
        current_stock REAL NOT NULL DEFAULT 0,
        min_stock REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS drink_recipes (
        id SERIAL PRIMARY KEY,
        drink_id INTEGER NOT NULL REFERENCES drinks(id),
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        quantity_per_serving REAL NOT NULL DEFAULT 0
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS packages (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        name VARCHAR(255) DEFAULT '',
        total_amount REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS package_items (
        id SERIAL PRIMARY KEY,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        drink_id INTEGER NOT NULL REFERENCES drinks(id),
        total_servings REAL NOT NULL DEFAULT 0,
        remaining_servings REAL NOT NULL DEFAULT 0
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        drink_id INTEGER NOT NULL REFERENCES drinks(id),
        package_item_id INTEGER REFERENCES package_items(id),
        servings REAL NOT NULL DEFAULT 1,
        amount REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS inventory_adjustments (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        adjustment_type VARCHAR(50) NOT NULL CHECK(adjustment_type IN ('add','remove','count_correct')),
        quantity REAL NOT NULL,
        reason TEXT DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        location_id INTEGER REFERENCES locations(id),
        user_id INTEGER REFERENCES users(id),
        action VARCHAR(255) NOT NULL,
        entity_type VARCHAR(100) NOT NULL,
        entity_id INTEGER,
        details TEXT DEFAULT '',
        ip_address VARCHAR(50) DEFAULT '',
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS package_templates (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name VARCHAR(255) NOT NULL,
        package_type VARCHAR(50) NOT NULL CHECK(package_type IN ('BASIC','FAT_LOSS','COMBO')),
        duration_days INTEGER NOT NULL DEFAULT 90,
        total_sessions INTEGER NOT NULL DEFAULT 0,
        total_drinks INTEGER NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS package_sessions (
        id SERIAL PRIMARY KEY,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        checkin_date TEXT NOT NULL,
        checkin_time TEXT,
        transaction_id INTEGER REFERENCES transactions(id),
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS pt_rates (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name VARCHAR(255) NOT NULL,
        location_type VARCHAR(50) NOT NULL CHECK(location_type IN ('AT_GYM','OUTSIDE')),
        rate_type VARCHAR(50) NOT NULL CHECK(rate_type IN ('PER_HOUR','PER_SESSION','PER_MONTH')),
        price REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS pt_sessions (
        id SERIAL PRIMARY KEY,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        trainer_id INTEGER REFERENCES users(id),
        pt_rate_id INTEGER REFERENCES pt_rates(id),
        session_date TEXT NOT NULL,
        duration_hours REAL DEFAULT 1,
        include_nutrition INTEGER NOT NULL DEFAULT 0,
        drink_id INTEGER REFERENCES drinks(id),
        package_item_id INTEGER REFERENCES package_items(id),
        pt_amount REAL NOT NULL DEFAULT 0,
        drink_amount REAL NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )""")


def _init_sqlite_schema(db):
    """SQLite-compatible schema."""
    db.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        address TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        full_name TEXT DEFAULT '',
        role TEXT NOT NULL DEFAULT 'STAFF' CHECK(role IN ('STAFF','MANAGER','OWNER')),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS user_locations (
        user_id INTEGER NOT NULL REFERENCES users(id),
        location_id INTEGER NOT NULL REFERENCES locations(id),
        PRIMARY KEY (user_id, location_id)
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        code TEXT NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT,
        UNIQUE (location_id, code)
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS drinks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name TEXT NOT NULL,
        price_per_serving REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'muỗng' CHECK(unit IN ('muỗng','nắp','gói')),
        current_stock REAL NOT NULL DEFAULT 0,
        min_stock REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS drink_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        drink_id INTEGER NOT NULL REFERENCES drinks(id),
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        quantity_per_serving REAL NOT NULL DEFAULT 0
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        name TEXT DEFAULT '',
        total_amount REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS package_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        drink_id INTEGER NOT NULL REFERENCES drinks(id),
        total_servings REAL NOT NULL DEFAULT 0,
        remaining_servings REAL NOT NULL DEFAULT 0
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        drink_id INTEGER NOT NULL REFERENCES drinks(id),
        package_item_id INTEGER REFERENCES package_items(id),
        servings REAL NOT NULL DEFAULT 1,
        amount REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS inventory_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        adjustment_type TEXT NOT NULL CHECK(adjustment_type IN ('add','remove','count_correct')),
        quantity REAL NOT NULL,
        reason TEXT DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER REFERENCES locations(id),
        user_id INTEGER REFERENCES users(id),
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER,
        details TEXT DEFAULT '',
        ip_address TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS package_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name TEXT NOT NULL,
        package_type TEXT NOT NULL CHECK(package_type IN ('BASIC','FAT_LOSS','COMBO')),
        duration_days INTEGER NOT NULL DEFAULT 90,
        total_sessions INTEGER NOT NULL DEFAULT 0,
        total_drinks INTEGER NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS package_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        checkin_date TEXT NOT NULL,
        checkin_time TEXT,
        transaction_id INTEGER REFERENCES transactions(id),
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS pt_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        name TEXT NOT NULL,
        location_type TEXT NOT NULL CHECK(location_type IN ('AT_GYM','OUTSIDE')),
        rate_type TEXT NOT NULL CHECK(rate_type IN ('PER_HOUR','PER_SESSION','PER_MONTH')),
        price REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS pt_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL REFERENCES locations(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        trainer_id INTEGER REFERENCES users(id),
        pt_rate_id INTEGER REFERENCES pt_rates(id),
        session_date TEXT NOT NULL,
        duration_hours REAL DEFAULT 1,
        include_nutrition INTEGER NOT NULL DEFAULT 0,
        drink_id INTEGER REFERENCES drinks(id),
        package_item_id INTEGER REFERENCES package_items(id),
        pt_amount REAL NOT NULL DEFAULT 0,
        drink_amount REAL NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")


def seed_defaults():
    """Seed default locations, admin user, and sample data."""
    import bcrypt as _bcrypt

    with get_db() as db:
        # Seed locations: ensure at least location 1 and 2 exist
        existing1 = db.execute("SELECT id FROM locations WHERE id = 1").fetchone()
        if existing1 is None:
            db.execute("INSERT INTO locations (id, name, address) VALUES (1, 'Cơ sở 1', '')")
            db.execute("INSERT INTO locations (id, name, address) VALUES (2, 'Cơ sở 2', '')")
        existing2 = db.execute("SELECT id FROM locations WHERE id = 2").fetchone()
        if existing2 is None and existing1 is None:
            # Already inserted 2 above in the same branch
            pass
        # Only operate on locations that actually exist
        existing_loc_ids = [r["id"] for r in db.execute("SELECT id FROM locations").fetchall()]

        # Default admin
        existing = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        admin_id = None
        if existing is None:
            hashed = _bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode("utf-8")
            db.execute(
                "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin", hashed, "Admin", "OWNER"),
            )
            admin_id = db.lastrowid
        else:
            admin_id = existing["id"]

        # Assign admin to existing locations
        for loc_id in existing_loc_ids:
            ul = db.execute(
                "SELECT user_id FROM user_locations WHERE user_id = ? AND location_id = ?",
                (admin_id, loc_id),
            ).fetchone()
            if ul is None:
                db.execute(
                    "INSERT INTO user_locations (user_id, location_id) VALUES (?, ?)",
                    (admin_id, loc_id),
                )

        # Sample staff user
        existing = db.execute("SELECT id FROM users WHERE username = ?", ("giangvien1",)).fetchone()
        staff_id = None
        if existing is None:
            hashed = _bcrypt.hashpw(b"123456", _bcrypt.gensalt()).decode("utf-8")
            db.execute(
                "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
                ("giangvien1", hashed, "Giáo viên 1", "STAFF"),
            )
            staff_id = db.lastrowid
        else:
            staff_id = existing["id"]

        # Assign staff to existing locations
        for loc_id in existing_loc_ids:
            ul = db.execute(
                "SELECT user_id FROM user_locations WHERE user_id = ? AND location_id = ?",
                (staff_id, loc_id),
            ).fetchone()
            if ul is None:
                db.execute(
                    "INSERT INTO user_locations (user_id, location_id) VALUES (?, ?)",
                    (staff_id, loc_id),
                )

        # Sample customers for each existing location
        for loc_id in existing_loc_ids:
            existing = db.execute(
                "SELECT id FROM customers WHERE location_id = ? AND code = ?",
                (loc_id, f"HV0{loc_id}01"),
            ).fetchone()
            if existing is None:
                db.execute(
                    "INSERT INTO customers (location_id, code, full_name, phone) VALUES (?, ?, ?, ?)",
                    (loc_id, f"HV0{loc_id}01", f"Khách hàng A (CS{loc_id})", "0901000001"),
                )
                db.execute(
                    "INSERT INTO customers (location_id, code, full_name, phone) VALUES (?, ?, ?, ?)",
                    (loc_id, f"HV0{loc_id}02", f"Khách hàng B (CS{loc_id})", "0901000002"),
                )

        # Sample ingredients for each existing location
        for loc_id in existing_loc_ids:
            existing = db.execute(
                "SELECT id FROM ingredients WHERE location_id = ? AND name = ?",
                (loc_id, "Bột Protein"),
            ).fetchone()
            if existing is None:
                db.execute(
                    "INSERT INTO ingredients (location_id, name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                    (loc_id, "Bột Protein", "muỗng", 300, 50, admin_id),
                )
                db.execute(
                    "INSERT INTO ingredients (location_id, name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                    (loc_id, "Bột Matcha", "muỗng", 200, 30, admin_id),
                )

        # Sample drinks for each existing location
        for loc_id in existing_loc_ids:
            existing = db.execute(
                "SELECT id FROM drinks WHERE location_id = ? AND name = ?",
                (loc_id, "Protein Shake"),
            ).fetchone()
            if existing is None:
                db.execute(
                    "INSERT INTO drinks (location_id, name, price_per_serving, created_by) VALUES (?, ?, ?, ?)",
                    (loc_id, "Protein Shake", 25000, admin_id),
                )
                db.execute(
                    "INSERT INTO drinks (location_id, name, price_per_serving, created_by) VALUES (?, ?, ?, ?)",
                    (loc_id, "Matcha Latte", 20000, admin_id),
                )

        # Seed sample package templates per location
        _seed_package_templates(db, admin_id)

        # Seed sample PT rates per location
        _seed_pt_rates(db)


def _seed_package_templates(db, admin_id):
    """Seed a few sample package templates for each location."""
    samples = [
        # (name, package_type, duration_days, total_sessions, total_drinks, total_amount)
        ("Gói cơ bản 3 tháng", "BASIC", 90, 36, 36, 3000000),
        ("Gói cơ bản 6 tháng", "BASIC", 180, 72, 72, 5500000),
        ("Gói giảm mỡ 3 tháng (90 ly)", "FAT_LOSS", 90, 0, 90, 4000000),
        ("Gói combo giảm mỡ 6 tháng (180 ly)", "COMBO", 180, 72, 180, 8000000),
    ]
    loc_ids = [r["id"] for r in db.execute("SELECT id FROM locations").fetchall()]
    for loc_id in loc_ids:
        for name, ptype, dur, sess, drnks, amt in samples:
            existing = db.execute(
                "SELECT id FROM package_templates WHERE location_id = ? AND name = ?",
                (loc_id, name),
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO package_templates
                       (location_id, name, package_type, duration_days,
                        total_sessions, total_drinks, total_amount, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (loc_id, name, ptype, dur, sess, drnks, amt, admin_id),
                )


def _seed_pt_rates(db):
    """Seed default PT rate cards for each location."""
    samples = [
        # (name, location_type, rate_type, price)
        ("PT tại phòng - Theo buổi", "AT_GYM", "PER_SESSION", 200000),
        ("PT tại phòng - Theo giờ", "AT_GYM", "PER_HOUR", 250000),
        ("PT tại nhà - Theo giờ", "OUTSIDE", "PER_HOUR", 350000),
        ("PT nhóm (3 người) - Theo buổi", "AT_GYM", "PER_SESSION", 350000),
    ]
    loc_ids = [r["id"] for r in db.execute("SELECT id FROM locations").fetchall()]
    for loc_id in loc_ids:
        for name, ltype, rtype, price in samples:
            existing = db.execute(
                "SELECT id FROM pt_rates WHERE location_id = ? AND name = ?",
                (loc_id, name),
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO pt_rates
                       (location_id, name, location_type, rate_type, price)
                       VALUES (?, ?, ?, ?, ?)""",
                    (loc_id, name, ltype, rtype, price),
                )


# ---------------------------------------------------------------------------
# Migration: add new columns to existing tables
# ---------------------------------------------------------------------------
def migrate_schema():
    """Add new columns for the package/PT upgrade. Safe to run multiple times."""
    with get_db() as db:
        if USE_PG:
            # packages: add package_template_id, duration_days, start_date, end_date,
            # total_sessions, remaining_sessions
            db.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS package_template_id INTEGER")
            db.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 0")
            db.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS start_date TEXT")
            db.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS end_date TEXT")
            db.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS total_sessions INTEGER DEFAULT 0")
            db.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS remaining_sessions INTEGER DEFAULT 0")
            # transactions: session_checkin flag
            db.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS session_checkin INTEGER DEFAULT 0")
        else:
            # SQLite: check column existence via pragma
            def _has_col(table, col):
                rows = db.execute(f"PRAGMA table_info({table})").fetchall()
                return any(r["name"] == col for r in rows)

            if not _has_col("packages", "package_template_id"):
                db.execute("ALTER TABLE packages ADD COLUMN package_template_id INTEGER")
            if not _has_col("packages", "duration_days"):
                db.execute("ALTER TABLE packages ADD COLUMN duration_days INTEGER DEFAULT 0")
            if not _has_col("packages", "start_date"):
                db.execute("ALTER TABLE packages ADD COLUMN start_date TEXT")
            if not _has_col("packages", "end_date"):
                db.execute("ALTER TABLE packages ADD COLUMN end_date TEXT")
            if not _has_col("packages", "total_sessions"):
                db.execute("ALTER TABLE packages ADD COLUMN total_sessions INTEGER DEFAULT 0")
            if not _has_col("packages", "remaining_sessions"):
                db.execute("ALTER TABLE packages ADD COLUMN remaining_sessions INTEGER DEFAULT 0")
            if not _has_col("transactions", "session_checkin"):
                db.execute("ALTER TABLE transactions ADD COLUMN session_checkin INTEGER DEFAULT 0")
            # Backfill location_id for legacy single-location databases
            # Ensure a default location exists for legacy backfill
            db.execute("INSERT OR IGNORE INTO locations (id, name) VALUES (1, 'Cơ sở mặc định')")
            if not _has_col("customers", "location_id"):
                db.execute("ALTER TABLE customers ADD COLUMN location_id INTEGER REFERENCES locations(id)")
                db.execute("UPDATE customers SET location_id = 1 WHERE location_id IS NULL")
            if not _has_col("drinks", "location_id"):
                db.execute("ALTER TABLE drinks ADD COLUMN location_id INTEGER REFERENCES locations(id)")
                db.execute("UPDATE drinks SET location_id = 1 WHERE location_id IS NULL")
            if not _has_col("ingredients", "location_id"):
                db.execute("ALTER TABLE ingredients ADD COLUMN location_id INTEGER REFERENCES locations(id)")
                db.execute("UPDATE ingredients SET location_id = 1 WHERE location_id IS NULL")
            if not _has_col("packages", "location_id"):
                db.execute("ALTER TABLE packages ADD COLUMN location_id INTEGER REFERENCES locations(id)")
                db.execute("UPDATE packages SET location_id = 1 WHERE location_id IS NULL")
