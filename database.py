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
    """Return a db connection/cursor compatible with both SQLite and PostgreSQL.

    Always returns an object with:
      - execute(sql, params) -> self
      - fetchone() -> dict | None
      - fetchall() -> list[dict]
      - lastrowid -> int | None
    """
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
        # Enable returning dict for sqlite3.Row via fetch wrappers
        # sqlite3.Row is already dict-like, but we wrap for consistency
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
# Schema (compatible with both SQLite and PostgreSQL via get_db wrapper)
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
    CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        code VARCHAR(50) UNIQUE NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        phone VARCHAR(50) DEFAULT '',
        email VARCHAR(255) DEFAULT '',
        notes TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS drinks (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
        price_per_serving REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS ingredients (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
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
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS drinks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        price_per_serving REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT
    )""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
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
        user_id INTEGER REFERENCES users(id),
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER,
        details TEXT DEFAULT '',
        ip_address TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""")


def seed_defaults():
    """Seed default admin user and sample data."""
    import bcrypt as _bcrypt

    with get_db() as db:
        # Default admin
        existing = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if existing is None:
            hashed = _bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode("utf-8")
            db.execute(
                "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin", hashed, "Admin", "OWNER"),
            )

        # Sample staff user
        existing = db.execute("SELECT id FROM users WHERE username = ?", ("giangvien1",)).fetchone()
        if existing is None:
            hashed = _bcrypt.hashpw(b"123456", _bcrypt.gensalt()).decode("utf-8")
            db.execute(
                "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
                ("giangvien1", hashed, "Giáo viên 1", "STAFF"),
            )

        # Sample customers
        existing = db.execute("SELECT id FROM customers WHERE code = ?", ("HV001",)).fetchone()
        if existing is None:
            db.execute("INSERT INTO customers (code, full_name, phone) VALUES (?, ?, ?)", ("HV001", "Nguyễn Thị Hương", "0901000001"))
            db.execute("INSERT INTO customers (code, full_name, phone) VALUES (?, ?, ?)", ("HV002", "Trần Minh Anh", "0901000002"))
            db.execute("INSERT INTO customers (code, full_name, phone) VALUES (?, ?, ?)", ("HV003", "Lê Hoàng Yến", "0901000003"))

        # Sample ingredients
        existing = db.execute("SELECT id FROM ingredients WHERE name = ?", ("Bột Protein",)).fetchone()
        if existing is None:
            db.execute("INSERT INTO ingredients (name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?)", ("Bột Protein", "muỗng", 300, 50, 1))
            db.execute("INSERT INTO ingredients (name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?)", ("Bột Matcha", "muỗng", 200, 30, 1))
            db.execute("INSERT INTO ingredients (name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?)", ("Bột Collagen", "muỗng", 150, 20, 1))

        # Sample drinks
        existing = db.execute("SELECT id FROM drinks WHERE name = ?", ("Protein Shake",)).fetchone()
        if existing is None:
            db.execute("INSERT INTO drinks (name, price_per_serving, created_by) VALUES (?, ?, ?)", ("Protein Shake", 25000, 1))
            db.execute("INSERT INTO drinks (name, price_per_serving, created_by) VALUES (?, ?, ?)", ("Matcha Latte", 20000, 1))
            db.execute("INSERT INTO drinks (name, price_per_serving, created_by) VALUES (?, ?, ?)", ("Collagen Drink", 30000, 1))

            # Sample recipes (2 muỗng mỗi ly)
            db.execute("INSERT INTO drink_recipes (drink_id, ingredient_id, quantity_per_serving) VALUES (?, ?, ?)", (1, 1, 2.0))
            db.execute("INSERT INTO drink_recipes (drink_id, ingredient_id, quantity_per_serving) VALUES (?, ?, ?)", (2, 2, 2.0))
            db.execute("INSERT INTO drink_recipes (drink_id, ingredient_id, quantity_per_serving) VALUES (?, ?, ?)", (3, 3, 2.0))