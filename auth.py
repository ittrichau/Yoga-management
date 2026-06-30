"""Authentication and authorization."""
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from nicegui import app, ui
import bcrypt as _bcrypt
import jwt as _jwt
from pydantic import BaseModel

from database import get_db
from settings import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# ==================== Helpers: current user's location ====================
def get_current_location_id() -> int | None:
    return app.storage.user.get("location_id")

def get_current_location_name() -> str:
    return app.storage.user.get("location_name", "Chưa chọn cơ sở")


# ==================== Password ====================
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ==================== Shared Navbar ====================
def render_navbar():
    """Navbar with location switcher."""
    role = app.storage.user.get("role", "STAFF")
    loc_name = get_current_location_name()
    loc_id = get_current_location_id()

    with ui.header().classes("bg-blue-600 text-white p-2 shadow-lg"):
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("items-center w-full justify-between"):
                ui.label("🏋️ Quản lý Gym").classes("text-md md:text-lg font-bold")
                with ui.row().classes("items-center gap-2"):
                    loc_color = "bg-green-500" if loc_id else "bg-red-400"
                    with ui.row().classes(f"items-center gap-1 px-2 py-1 rounded {loc_color}"):
                        ui.label(f"📍 {loc_name}").classes("text-xs md:text-sm")
                    username = app.storage.user.get("username", "")
                    ui.label(f"👤 {username}").classes("text-xs md:text-sm")
                    def do_logout():
                        app.storage.user.clear()
                        ui.navigate.to("/login")
                    ui.button("Đăng xuất", icon="logout", on_click=do_logout).props("flat color=white dense")
                    def show_loc():
                        loc_dialog.open()
                    ui.button("Đổi cơ sở", icon="swap_horiz", on_click=show_loc).props("flat color=white dense")
            with ui.row().classes("items-center gap-x-2 gap-y-1 flex-wrap text-xs md:text-sm"):
                ui.link("📊 Bảng điều khiển", "/").classes("text-white hover:underline px-2")
                # Kinh doanh dropdown
                with ui.button("👥 Kinh doanh ▾").props("flat color=white dense"):
                    with ui.menu():
                        ui.menu_item("Khách hàng", on_click=lambda: ui.navigate.to("/customers"))
                        ui.menu_item("Check-in 🟡", on_click=lambda: ui.navigate.to("/checkin"))
                        ui.menu_item("Gói trả trước", on_click=lambda: ui.navigate.to("/packages"))
                        ui.menu_item("PT", on_click=lambda: ui.navigate.to("/pt"))
                        if role in ("MANAGER", "OWNER"):
                            ui.separator()
                            ui.menu_item("Nâng cấp gói", on_click=lambda: ui.navigate.to("/packages/upgrade"))
                # Kho dropdown
                with ui.button("🥤 Kho ▾").props("flat color=white dense"):
                    with ui.menu():
                        ui.menu_item("Đồ uống", on_click=lambda: ui.navigate.to("/drinks"))
                        ui.menu_item("Nguyên liệu", on_click=lambda: ui.navigate.to("/ingredients"))
                        if role in ("MANAGER", "OWNER"):
                            ui.separator()
                            ui.menu_item("Mẫu gói", on_click=lambda: ui.navigate.to("/package-templates"))
                # Hệ thống dropdown
                if role in ("MANAGER", "OWNER"):
                    with ui.button("⚙️ Hệ thống ▾").props("flat color=white dense"):
                        with ui.menu():
                            ui.menu_item("Nhật ký", on_click=lambda: ui.navigate.to("/audit"))
                            if role == "OWNER":
                                ui.separator()
                                ui.menu_item("Người dùng", on_click=lambda: ui.navigate.to("/users"))
                                ui.menu_item("Cơ sở", on_click=lambda: ui.navigate.to("/locations"))

    # Switcher dialog
    with ui.dialog() as loc_dialog, ui.card().classes("p-6 w-80"):
        ui.label("Chọn cơ sở làm việc").classes("text-xl font-bold mb-4")
        with ui.column().classes("w-full gap-2"):
            uid = app.storage.user.get("user_id", 0)
            with get_db() as conn:
                locs = conn.execute(
                    """SELECT l.id, l.name, l.address
                       FROM locations l
                       JOIN user_locations ul ON ul.location_id = l.id
                       WHERE ul.user_id = ? AND l.is_active = 1
                       ORDER BY l.name""",
                    (uid,),
                ).fetchall()
            if loc_id:
                ui.label(f"Đang làm việc tại: {loc_name}").classes("text-sm font-bold")
            for loc in locs:
                is_cur = loc["id"] == loc_id
                label = f"📍 {loc['name']}"
                if is_cur:
                    label += " (hiện tại)"
                ui.button(
                    label,
                    on_click=lambda l=loc: switch_location(l["id"], l["name"]),
                    icon="check" if is_cur else "place",
                ).props("unelevated" if is_cur else "outlined").classes(
                    "w-full" + (" bg-green-500 text-white" if is_cur else "")
                )
        ui.button("Đóng", on_click=loc_dialog.close, icon="close").props("outlined").classes("w-full mt-4")


def switch_location(location_id: int, location_name: str):
    """Switch location and reload dashboard."""
    app.storage.user.update({"location_id": location_id, "location_name": location_name})
    ui.navigate.to("/")
    ui.notify(f"Đã chuyển sang {location_name}", type="positive")


# ==================== JWT ====================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return _jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict | None:
    try:
        return _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except _jwt.PyJWTError:
        return None


# ==================== FastAPI deps ====================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, full_name, role FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Không tìm thấy người dùng")
    return dict(row)

def require_role(required: str):
    hierarchy = {"STAFF": 1, "MANAGER": 2, "OWNER": 3}
    async def check(user: dict = Depends(get_current_user)):
        if hierarchy.get(user["role"], 0) < hierarchy.get(required, 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không đủ quyền")
        return user
    return check


# ==================== API Router ====================
router = APIRouter(tags=["auth"])

@router.post("/api/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, hashed_password, role, is_active FROM users WHERE username = ?",
            (form.username,),
        ).fetchone()
    if row is None or not row["is_active"] or not verify_password(form.password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai thông tin đăng nhập")
    token = create_access_token({"sub": row["username"], "role": row["role"]})
    return Token(access_token=token)

@router.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]}

@router.get("/api/my-locations")
def my_locations(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        locs = conn.execute(
            """SELECT l.id, l.name, l.address
               FROM locations l
               JOIN user_locations ul ON ul.location_id = l.id
               WHERE ul.user_id = ? AND l.is_active = 1
               ORDER BY l.name""",
            (user["id"],),
        ).fetchall()
    return [dict(loc) for loc in locs]


# ==================== User Management API (OWNER) ====================
class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role: str = "STAFF"
    location_ids: list[int] = []

class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    location_ids: list[int] | None = None

@router.get("/api/users")
def list_users(user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY role, username"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        with get_db() as conn:
            locs = conn.execute(
                "SELECT id, name FROM locations l JOIN user_locations ul ON ul.location_id = l.id WHERE ul.user_id = ?",
                (r["id"],),
            ).fetchall()
        d["locations"] = [dict(loc) for loc in locs]
        result.append(d)
    return result

@router.get("/api/locations")
def list_locations(user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM locations WHERE is_active = 1 ORDER BY name").fetchall()
    return [dict(r) for r in rows]

@router.post("/api/locations", status_code=201)
def create_location(data: dict, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM locations WHERE name = ?", (data["name"],)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Tên cơ sở đã tồn tại")
        conn.execute(
            "INSERT INTO locations (name, address) VALUES (?, ?)",
            (data["name"], data.get("address", "")),
        )
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'create', 'location', ?, ?)",
            (user["id"], conn.lastrowid, json.dumps({"name": data["name"]})),
        )
    return {"id": conn.lastrowid, "message": "Cơ sở đã được tạo"}

@router.put("/api/locations/{location_id}")
def update_location(location_id: int, data: dict, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cơ sở")
        conn.execute(
            "UPDATE locations SET name = ?, address = ? WHERE id = ?",
            (data.get("name", row["name"]), data.get("address", row["address"]), location_id),
        )
    return {"message": "Cơ sở đã được cập nhật"}

@router.post("/api/users", status_code=201)
def create_user(data: UserCreate, user: dict = Depends(require_role("OWNER"))):
    if data.role not in ("STAFF", "MANAGER", "OWNER"):
        raise HTTPException(status_code=400, detail="Vai trò không hợp lệ")
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (data.username,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
        hashed = hash_password(data.password)
        conn.execute(
            "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
            (data.username, hashed, data.full_name, data.role),
        )
        user_id = conn.lastrowid
        for loc_id in data.location_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_locations (user_id, location_id) VALUES (?, ?)",
                (user_id, loc_id),
            )
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'create', 'user', ?, ?)",
            (user["id"], user_id, json.dumps({"username": data.username, "role": data.role})),
        )
    return {"id": user_id, "message": "Người dùng đã được tạo"}

@router.put("/api/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        updates = {}
        for field in ["full_name", "role", "is_active"]:
            val = getattr(data, field)
            if val is not None:
                if field == "role" and val not in ("STAFF", "MANAGER", "OWNER"):
                    raise HTTPException(status_code=400, detail="Vai trò không hợp lệ")
                updates[field] = val
        if data.password:
            updates["hashed_password"] = hash_password(data.password)
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [user_id]
            conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        if data.location_ids is not None:
            conn.execute("DELETE FROM user_locations WHERE user_id = ?", (user_id,))
            for loc_id in data.location_ids:
                conn.execute(
                    "INSERT INTO user_locations (user_id, location_id) VALUES (?, ?)",
                    (user_id, loc_id),
                )
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'update', 'user', ?, ?)",
            (user["id"], user_id, json.dumps({k: v for k, v in updates.items() if k != "hashed_password"})),
        )
    return {"message": "Người dùng đã được cập nhật"}

@router.put("/api/users/{user_id}/deactivate")
def deactivate_user(user_id: int, user: dict = Depends(require_role("OWNER"))):
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Không thể vô hiệu hóa chính mình")
    with get_db() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?", (now, user_id))
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'deactivate', 'user', ?, ?)",
            (user["id"], user_id, json.dumps({"username": row["username"]})),
        )
    return {"message": "Người dùng đã bị vô hiệu hóa"}


# ==================== NiceGUI Pages ====================

# ---------- Login ----------
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
            user_data = None
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id, username, hashed_password, role, is_active FROM users WHERE username = ?",
                    (username.value,),
                ).fetchone()
                if row is not None:
                    user_data = dict(row)
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
            ui.navigate.to("/select-location")

        ui.button("Đăng nhập", on_click=handle_login, icon="login").props("unelevated").classes("w-full bg-blue-600 text-white")


# ---------- Location Selection ----------
@ui.page("/select-location")
def select_location_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return

    user_id = app.storage.user.get("user_id", 0)

    with get_db() as conn:
        locs = conn.execute(
            """SELECT l.id, l.name, l.address
               FROM locations l
               JOIN user_locations ul ON ul.location_id = l.id
               WHERE ul.user_id = ? AND l.is_active = 1
               ORDER BY l.name""",
            (user_id,),
        ).fetchall()

    if app.storage.user.get("location_id"):
        ui.navigate.to("/")
        return

    if len(locs) == 1:
        loc = locs[0]
        app.storage.user.update({"location_id": loc["id"], "location_name": loc["name"]})
        ui.navigate.to("/")
        return

    ui.query("body").classes("flex items-center justify-center min-h-screen bg-gray-100")
    with ui.card().classes("p-6 md:p-8 w-full max-w-md mx-4 shadow-xl"):
        ui.label("Chọn cơ sở làm việc").classes("text-2xl font-bold text-center mb-2")
        username = app.storage.user.get("username", "")
        ui.label(f"Xin chào, {username}").classes("text-center text-gray-500 mb-6")

        if not locs:
            ui.label("Bạn chưa được gán vào cơ sở nào. Vui lòng liên hệ quản lý.").classes("text-red-500 text-center")
            def go_login():
                app.storage.user.clear()
                ui.navigate.to("/login")
            ui.button("Quay lại đăng nhập", on_click=go_login, icon="arrow_back").props("outlined").classes("w-full mt-4")
            return

        for loc in locs:
            ui.button(
                f"📍 {loc['name']}",
                on_click=lambda l=loc: _pick_location(l["id"], l["name"]),
            ).props("unelevated").classes("w-full bg-blue-600 text-white mb-2")

        def do_logout():
            app.storage.user.clear()
            ui.navigate.to("/login")
        ui.button("Đăng xuất", on_click=do_logout, icon="logout").props("outlined").classes("w-full mt-2 text-red-500")


def _pick_location(location_id: int, location_name: str):
    app.storage.user.update({"location_id": location_id, "location_name": location_name})
    ui.navigate.to("/")
    ui.notify(f"Đang làm việc tại: {location_name}", type="positive")


# ---------- User Management ----------
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
            {"name": "locations", "label": "Cơ sở", "field": "locations"},
            {"name": "status", "label": "Trạng thái", "field": "status"},
            {"name": "action", "label": "Thao tác", "field": "action"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, username, full_name, role, is_active FROM users ORDER BY role, username"
            ).fetchall()
        result = []
        for r in rows:
            with get_db() as conn:
                locs = conn.execute(
                    "SELECT l.name FROM locations l JOIN user_locations ul ON ul.location_id = l.id WHERE ul.user_id = ?",
                    (r["id"],),
                ).fetchall()
            loc_names = ", ".join(l["name"] for l in locs) if locs else "Chưa gán"
            d = {
                "id": r["id"],
                "username": r["username"],
                "full_name": r["full_name"],
                "role": r["role"],
                "locations": loc_names,
                "status": "Hoạt động" if r["is_active"] else "Vô hiệu",
            }
            d["action"] = d["id"]
            result.append(d)
        user_table.rows = result
        user_table.update()

    # Load locations for assignment
    with get_db() as conn:
        all_locations = conn.execute("SELECT id, name FROM locations WHERE is_active = 1 ORDER BY name").fetchall()
    location_options = {loc["id"]: loc["name"] for loc in all_locations}

    # Create dialog
    with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
        ui.label("Người dùng mới").classes("text-xl font-bold mb-4")
        u_username = ui.input("Tên đăng nhập *").props("outlined").classes("w-full mb-2")
        u_password = ui.input("Mật khẩu *", password=True, password_toggle_button=True).props("outlined").classes("w-full mb-2")
        u_fullname = ui.input("Họ tên").props("outlined").classes("w-full mb-2")
        u_role = ui.select(["STAFF", "MANAGER", "OWNER"], label="Vai trò *", value="STAFF").props("outlined").classes("w-full mb-2")
        u_locs = ui.select(location_options, label="Cơ sở", multiple=True).props("outlined").classes("w-full mb-4")
        err = ui.label().classes("text-red-500 text-sm")

        def handle_create():
            if not u_username.value or not u_password.value:
                err.set_text("Vui lòng nhập tên đăng nhập và mật khẩu")
                return
            uid = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                ex = conn.execute("SELECT id FROM users WHERE username = ?", (u_username.value,)).fetchone()
                if ex:
                    err.set_text("Tên đăng nhập đã tồn tại")
                    return
                hashed = hash_password(u_password.value)
                conn.execute(
                    "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
                    (u_username.value, hashed, u_fullname.value, u_role.value),
                )
                new_id = conn.lastrowid
                if u_locs.value:
                    for lid in u_locs.value:
                        conn.execute("INSERT OR IGNORE INTO user_locations (user_id, location_id) VALUES (?, ?)", (new_id, lid))
                conn.execute(
                    "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'create', 'user', ?, ?)",
                    (uid, new_id, json.dumps({"username": u_username.value, "role": u_role.value})),
                )
            create_dialog.close()
            refresh()
            ui.notify("Người dùng đã được tạo", type="positive")

        with ui.row().classes("gap-2"):
            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("bg-blue-600 text-white")
            ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")

    # Edit dialog
    with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96"):
        ui.label("Sửa người dùng").classes("text-xl font-bold mb-4")
        e_id_label = ui.label().classes("text-sm text-gray-500 mb-2")
        e_username = ui.input("Tên đăng nhập").props("outlined readonly").classes("w-full mb-2")
        e_fullname = ui.input("Họ tên").props("outlined").classes("w-full mb-2")
        e_role = ui.select(["STAFF", "MANAGER", "OWNER"], label="Vai trò").props("outlined").classes("w-full mb-2")
        e_password = ui.input("Mật khẩu mới (bỏ trống nếu không đổi)", password=True, password_toggle_button=True).props("outlined").classes("w-full mb-2")
        e_locs = ui.select(location_options, label="Cơ sở", multiple=True).props("outlined").classes("w-full mb-4")
        e_err = ui.label().classes("text-red-500 text-sm")

        def handle_edit():
            uid = app.storage.user.get("user_id", 1)
            row_id = e_id_label.text
            if not row_id:
                return
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET full_name = ?, role = ? WHERE id = ?",
                    (e_fullname.value, e_role.value, int(row_id)),
                )
                if e_password.value:
                    hashed = hash_password(e_password.value)
                    conn.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (hashed, int(row_id)))
                if e_locs.value is not None:
                    conn.execute("DELETE FROM user_locations WHERE user_id = ?", (int(row_id),))
                    for lid in e_locs.value:
                        conn.execute("INSERT OR IGNORE INTO user_locations (user_id, location_id) VALUES (?, ?)", (int(row_id), lid))
                conn.execute(
                    "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'update', 'user', ?, ?)",
                    (uid, int(row_id), json.dumps({"full_name": e_fullname.value, "role": e_role.value})),
                )
            edit_dialog.close()
            refresh()
            ui.notify("Người dùng đã được cập nhật", type="positive")

        with ui.row().classes("gap-2"):
            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("bg-blue-600 text-white")
            ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")

    # ---------- Actions ----------
    with ui.row().classes("gap-2 mb-4"):
        ui.button("Người dùng mới", on_click=create_dialog.open, icon="add").props("unelevated").classes("bg-green-600 text-white")
        ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

    def open_edit(row_id):
        with get_db() as conn:
            r = conn.execute(
                "SELECT id, username, full_name, role FROM users WHERE id = ?", (row_id,)
            ).fetchone()
            ll = conn.execute(
                "SELECT location_id FROM user_locations WHERE user_id = ?", (row_id,)
            ).fetchall()
        if not r:
            return
        e_id_label.set_text(str(r["id"]))
        e_username.value = r["username"]
        e_fullname.value = r["full_name"]
        e_role.value = r["role"]
        e_locs.value = [x["location_id"] for x in ll]
        e_password.value = ""
        e_err.set_text("")
        edit_dialog.open()

    def do_deactivate(row_id):
        uid = app.storage.user.get("user_id", 1)
        if row_id == uid:
            ui.notify("Không thể vô hiệu hóa chính mình", type="warning")
            return
        with get_db() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (row_id,))
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'deactivate', 'user', ?, ?)",
                (uid, row_id, json.dumps({"deactivated": True})),
            )
        refresh()
        ui.notify("Người dùng đã bị vô hiệu hóa", type="positive")

    def do_activate(row_id):
        uid = app.storage.user.get("user_id", 1)
        with get_db() as conn:
            conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (row_id,))
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'activate', 'user', ?, ?)",
                (uid, row_id, json.dumps({"activated": True})),
            )
        refresh()
        ui.notify("Người dùng đã được kích hoạt", type="positive")

    # Wire up action buttons in table
    user_table.add_slot("body-cell-action", """
        <q-td :props="props">
            <q-btn flat round icon="edit" @click="$parent.open_edit(props.value)" color="blue" />
            <q-btn flat round icon="block" @click="$parent.do_deactivate(props.value)" color="red" />
            <q-btn flat round icon="check_circle" @click="$parent.do_activate(props.value)" color="green" />
        </q-td>
    """)

    # Expose functions to Vue context
    import vue
    vue.open_edit = open_edit
    vue.do_deactivate = do_deactivate
    vue.do_activate = do_activate

    refresh()


# ---------- Location Management ----------
@ui.page("/locations")
def locations_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    role = app.storage.user.get("role", "STAFF")
    if role != "OWNER":
        ui.label("Từ chối truy cập. Chỉ OWNER mới có quyền.").classes("text-red-500 text-xl")
        return

    render_navbar()
    ui.label("Quản lý cơ sở").classes("text-2xl font-bold mb-4")

    loc_table = ui.table(
        columns=[
            {"name": "name", "label": "Tên cơ sở", "field": "name"},
            {"name": "address", "label": "Địa chỉ", "field": "address"},
            {"name": "created_at", "label": "Ngày tạo", "field": "created_at"},
            {"name": "action", "label": "Thao tác", "field": "action"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh_locs():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, name, address, created_at FROM locations WHERE is_active = 1 ORDER BY name"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["action"] = d["id"]
            result.append(d)
        loc_table.rows = result
        loc_table.update()

    # Create dialog
    with ui.dialog() as loc_create_dlg, ui.card().classes("p-6 w-96"):
        ui.label("Cơ sở mới").classes("text-xl font-bold mb-4")
        l_name = ui.input("Tên cơ sở *").props("outlined").classes("w-full mb-2")
        l_addr = ui.input("Địa chỉ").props("outlined").classes("w-full mb-4")
        l_err = ui.label().classes("text-red-500 text-sm")

        def handle_create_loc():
            if not l_name.value:
                l_err.set_text("Vui lòng nhập tên cơ sở")
                return
            uid = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                ex = conn.execute("SELECT id FROM locations WHERE name = ?", (l_name.value,)).fetchone()
                if ex:
                    l_err.set_text("Tên cơ sở đã tồn tại")
                    return
                conn.execute(
                    "INSERT INTO locations (name, address) VALUES (?, ?)",
                    (l_name.value, l_addr.value or ""),
                )
                conn.execute(
                    "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'create', 'location', ?, ?)",
                    (uid, conn.lastrowid, json.dumps({"name": l_name.value})),
                )
            loc_create_dlg.close()
            refresh_locs()
            ui.notify("Cơ sở đã được tạo", type="positive")

        with ui.row().classes("gap-2"):
            ui.button("Lưu", on_click=handle_create_loc, icon="save").props("unelevated").classes("bg-blue-600 text-white")
            ui.button("Đóng", on_click=loc_create_dlg.close, icon="close").props("outlined")

    # Edit dialog
    with ui.dialog() as loc_edit_dlg, ui.card().classes("p-6 w-96"):
        ui.label("Sửa cơ sở").classes("text-xl font-bold mb-4")
        le_id = ui.label().classes("hidden")
        le_name = ui.input("Tên cơ sở *").props("outlined").classes("w-full mb-2")
        le_addr = ui.input("Địa chỉ").props("outlined").classes("w-full mb-4")
        le_err = ui.label().classes("text-red-500 text-sm")

        def handle_edit_loc():
            uid = app.storage.user.get("user_id", 1)
            lid = le_id.text
            if not lid or not le_name.value:
                le_err.set_text("Vui lòng nhập tên cơ sở")
                return
            with get_db() as conn:
                conn.execute(
                    "UPDATE locations SET name = ?, address = ? WHERE id = ?",
                    (le_name.value, le_addr.value or "", int(lid)),
                )
            loc_edit_dlg.close()
            refresh_locs()
            ui.notify("Cơ sở đã được cập nhật", type="positive")

        with ui.row().classes("gap-2"):
            ui.button("Lưu", on_click=handle_edit_loc, icon="save").props("unelevated").classes("bg-blue-600 text-white")
            ui.button("Đóng", on_click=loc_edit_dlg.close, icon="close").props("outlined")

    with ui.row().classes("gap-2 mb-4"):
        ui.button("Cơ sở mới", on_click=loc_create_dlg.open, icon="add").props("unelevated").classes("bg-green-600 text-white")
        ui.button("Làm mới", on_click=refresh_locs, icon="refresh").props("outlined")

    def open_edit_loc(row_id):
        with get_db() as conn:
            r = conn.execute("SELECT id, name, address FROM locations WHERE id = ?", (row_id,)).fetchone()
        if not r:
            return
        le_id.set_text(str(r["id"]))
        le_name.value = r["name"]
        le_addr.value = r["address"] or ""
        le_err.set_text("")
        loc_edit_dlg.open()

    def do_deactivate_loc(row_id):
        uid = app.storage.user.get("user_id", 1)
        with get_db() as conn:
            conn.execute("UPDATE locations SET is_active = 0 WHERE id = ?", (row_id,))
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, 'deactivate', 'location', ?, ?)",
                (uid, row_id, json.dumps({"deactivated": True})),
            )
        refresh_locs()
        ui.notify("Cơ sở đã bị vô hiệu hóa", type="positive")

    loc_table.add_slot("body-cell-action", """
        <q-td :props="props">
            <q-btn flat round icon="edit" @click="$parent.open_edit_loc(props.value)" color="blue" />
            <q-btn flat round icon="delete" @click="$parent.do_deactivate_loc(props.value)" color="red" />
        </q-td>
    """)

    import vue
    vue.open_edit_loc = open_edit_loc
    vue.do_deactivate_loc = do_deactivate_loc

    refresh_locs()
