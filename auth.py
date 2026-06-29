"""Authentication and authorization."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from nicegui import app, ui
import bcrypt as _bcrypt
import jwt as _jwt
from pydantic import BaseModel

from database import get_db
from settings import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode('utf-8'), _bcrypt.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

# ---------------------------------------------------------------------------
# Shared navbar (dịch sang tiếng Việt)
# ---------------------------------------------------------------------------
def render_navbar():
    """Render common navigation bar with responsive wrapping for mobile."""
    role = app.storage.user.get("role", "STAFF")
    with ui.header().classes("bg-blue-600 text-white p-2 shadow-lg"):
        with ui.column().classes("w-full gap-1"):
            # Top row: logo + user info + logout
            with ui.row().classes("items-center w-full justify-between"):
                ui.label("🏋️ Quản lý Gym").classes("text-md md:text-lg font-bold")
                with ui.row().classes("items-center gap-2"):
                    username = app.storage.user.get("username", "")
                    ui.label(f"👤 {username}").classes("text-xs md:text-sm")
                    def do_logout():
                        app.storage.user.clear()
                        ui.navigate.to("/login")
                    ui.button("Đăng xuất", icon="logout", on_click=do_logout).props("flat color=white dense")
            # Bottom row: nav links (wrap on mobile)
            with ui.row().classes("items-center gap-x-3 gap-y-1 flex-wrap text-xs md:text-sm"):
                ui.link("Bảng điều khiển", "/").classes("text-white hover:underline")
                ui.link("Khách hàng", "/customers").classes("text-white hover:underline")
                ui.link("Đồ uống", "/drinks").classes("text-white hover:underline")
                ui.link("Nguyên liệu", "/ingredients").classes("text-white hover:underline")
                ui.link("Gói trả trước", "/packages").classes("text-white hover:underline")
                ui.link("Bán hàng", "/sales").classes("text-white hover:underline")
                if role in ("MANAGER", "OWNER"):
                    ui.link("Nhật ký", "/audit").classes("text-white hover:underline")
                if role == "OWNER":
                    ui.link("Người dùng", "/users").classes("text-white hover:underline")

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: str | None = None

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return _jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict | None:
    try:
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except _jwt.PyJWTError:
        return None

# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validate token and return user dict."""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    with get_db() as conn:
        row = conn.execute("SELECT id, username, full_name, role FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return dict(row)

def require_role(required: str):
    """Dependency factory: require a minimum role."""
    hierarchy = {"STAFF": 1, "MANAGER": 2, "OWNER": 3}
    async def check(user: dict = Depends(get_current_user)):
        if hierarchy.get(user["role"], 0) < hierarchy.get(required, 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return check

# ---------------------------------------------------------------------------
# API Router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["auth"])

@router.post("/api/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    """Authenticate and return JWT token."""
    with get_db() as conn:
        row = conn.execute("SELECT id, username, hashed_password, role, is_active FROM users WHERE username = ?", (form.username,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = dict(row)
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account deactivated")
    if not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return Token(access_token=token)

@router.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {"id": user["id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]}

# ---------------------------------------------------------------------------
# User Management API (OWNER only)
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role: str = "STAFF"

class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None

@router.get("/api/users")
def list_users(user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY role, username"
        ).fetchall()
    return [dict(r) for r in rows]

@router.post("/api/users", status_code=201)
def create_user(data: UserCreate, user: dict = Depends(require_role("OWNER"))):
    if data.role not in ("STAFF", "MANAGER", "OWNER"):
        raise HTTPException(status_code=400, detail="Invalid role")
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (data.username,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        hashed = hash_password(data.password)
        cur = conn.execute(
            "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
            (data.username, hashed, data.full_name, data.role),
        )
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'create', 'user', ?, ?)",
            (user["id"], cur.lastrowid, f'{{"username": "{data.username}", "role": "{data.role}"}}'),
        )
    return {"id": cur.lastrowid, "message": "User created"}

@router.put("/api/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        updates = {}
        for field in ["full_name", "role", "is_active"]:
            val = getattr(data, field)
            if val is not None:
                if field == "role" and val not in ("STAFF", "MANAGER", "OWNER"):
                    raise HTTPException(status_code=400, detail="Invalid role")
                updates[field] = val
        if data.password:
            updates["hashed_password"] = hash_password(data.password)
        if not updates:
            return {"message": "No changes"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'update', 'user', ?, ?)",
            (user["id"], user_id, str(updates)),
        )

@router.put("/api/users/{user_id}/deactivate")
def deactivate_user(user_id: int, user: dict = Depends(require_role("OWNER"))):
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    with get_db() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?", (now, user_id))
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'deactivate', 'user', ?, ?)",
            (user["id"], user_id, f'{{"username": "{row["username"]}"}}'),
        )
    return {"message": "User deactivated"}

# ---------------------------------------------------------------------------
# NiceGUI Login Page
# ---------------------------------------------------------------------------
@ui.page("/login")
def login_page():
    ui.query("body").classes("flex items-center justify-center min-h-screen bg-gray-100")

    with ui.card().classes("p-6 md:p-8 w-full max-w-sm mx-4 shadow-xl"):
        ui.label("Quản lý Dinh dưỡng Gym").classes("text-2xl font-bold text-center mb-6")

        username = ui.input("Tên đăng nhập").props("outlined").classes("w-full mb-4")
        password = ui.input("Mật khẩu", password=True, password_toggle_button=True).props("outlined").classes("w-full mb-6")

        error_label = ui.label().classes("text-red-500 text-sm mb-2")

        def handle_login():
            error_label.set_text("")
            # Fetch user data while connection is open
            user_data = None
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id, username, hashed_password, role, is_active FROM users WHERE username = ?",
                    (username.value,),
                ).fetchone()
                if row is not None:
                    user_data = {"id": row["id"], "username": row["username"], "hashed_password": row["hashed_password"], "role": row["role"], "is_active": row["is_active"]}
            if user_data is None:
                error_label.set_text("Sai tên đăng nhập hoặc mật khẩu")
                return
            if not user_data["is_active"]:
                error_label.set_text("Tài khoản đã bị vô hiệu hóa")
                return
            if not verify_password(password.value, user_data["hashed_password"]):
                error_label.set_text("Sai tên đăng nhập hoặc mật khẩu")
                return
            token = create_access_token({"sub": user_data["username"], "role": user_data["role"]})
            app.storage.user.update({
                "token": token,
                "username": user_data["username"],
                "role": user_data["role"],
                "user_id": user_data["id"],
            })
            ui.navigate.to("/")

        ui.button("Đăng nhập", on_click=handle_login, icon="login").props("unelevated").classes("w-full bg-blue-600 text-white")

# ---------------------------------------------------------------------------
# NiceGUI User Management Page
# ---------------------------------------------------------------------------
@ui.page("/users")
def users_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    role = app.storage.user.get("role", "STAFF")
    if role != "OWNER":
        ui.label("Từ chối truy cập. Chỉ OWNER mới có quyền.").classes("text-red-500 text-xl")
        return

    render_navbar()
    ui.label("Quản lý người dùng").classes("text-2xl font-bold mb-4")

    user_table = ui.table(
        columns=[
            {"name": "username", "label": "Tên đăng nhập", "field": "username"},
            {"name": "full_name", "label": "Họ tên", "field": "full_name"},
            {"name": "role", "label": "Vai trò", "field": "role"},
            {"name": "status", "label": "Trạng thái", "field": "status"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, username, full_name, role, is_active FROM users ORDER BY role, username"
            ).fetchall()
        user_table.rows = [
            {
                "id": r["id"],
                "username": r["username"],
                "full_name": r["full_name"],
                "role": r["role"],
                "status": "Hoạt động" if r["is_active"] else "Vô hiệu",
            }
            for r in rows
        ]
        user_table.update()

    with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
        ui.label("Người dùng mới").classes("text-xl font-bold mb-4")
        u_username = ui.input("Tên đăng nhập *").props("outlined").classes("w-full mb-2")
        u_password = ui.input("Mật khẩu *", password=True, password_toggle_button=True).props("outlined").classes("w-full mb-2")
        u_fullname = ui.input("Họ tên").props("outlined").classes("w-full mb-2")
        u_role = ui.select(["STAFF", "MANAGER", "OWNER"], label="Vai trò *", value="STAFF").props("outlined").classes("w-full mb-4")
        err = ui.label().classes("text-red-500 text-sm")

        def handle_save():
            if not u_username.value or not u_password.value:
                err.set_text("Vui lòng nhập tên đăng nhập và mật khẩu")
                return
            user_id = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                existing = conn.execute("SELECT id FROM users WHERE username = ?", (u_username.value,)).fetchone()
                if existing:
                    err.set_text("Tên đăng nhập đã tồn tại")
                    return
                hashed = hash_password(u_password.value)
                conn.execute(
                    "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
                    (u_username.value, hashed, u_fullname.value, u_role.value),
                )
            create_dialog.close()
            refresh()
            ui.notify(f"User {u_username.value} created", type="positive")

        ui.button("Lưu", on_click=handle_save, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    ui.button("Người dùng mới", on_click=create_dialog.open, icon="person_add").props("unelevated").classes("bg-green-600 text-white mb-4")
    ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined").classes("mb-4")
    refresh()
