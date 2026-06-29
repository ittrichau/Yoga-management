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


def seed_defaults():
    """Seed default locations, admin user, and sample data."""
    import bcrypt as _bcrypt

    with get_db() as db:
        # Seed locations
        existing = db.execute("SELECT id FROM locations WHERE id = 1").fetchone()
        if existing is None:
            db.execute("INSERT INTO locations (id, name, address) VALUES (1, 'Cơ sở 1', '')")
            db.execute("INSERT INTO locations (id, name, address) VALUES (2, 'Cơ sở 2', '')")

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

        # Assign admin to both locations
        for loc_id in [1, 2]:
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

        # Assign staff to both locations (luân phiên sáng/chiều)
        for loc_id in [1, 2]:
            ul = db.execute(
                "SELECT user_id FROM user_locations WHERE user_id = ? AND location_id = ?",
                (staff_id, loc_id),
            ).fetchone()
            if ul is None:
                db.execute(
                    "INSERT INTO user_locations (user_id, location_id) VALUES (?, ?)",
                    (staff_id, loc_id),
                )

        # Sample customers for each location
        for loc_id in [1, 2]:
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

        # Sample ingredients for each location
        for loc_id in [1, 2]:
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

        # Sample drinks for each location (same name, different location)
        for loc_id in [1, 2]:
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