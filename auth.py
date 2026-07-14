"""Authentication, authorization, shared navigation, and owner admin pages."""
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt as _bcrypt
import jwt as _jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from settings import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY


ROLE_OPTIONS = ("ADMIN", "OWNER", "TEACHER")
ROLE_HIERARCHY = {"TEACHER": 1, "OWNER": 2, "ADMIN": 3}
ROLE_LABELS = {"ADMIN": "Admin", "OWNER": "Chủ phòng", "TEACHER": "Giáo viên"}


# ==================== Models ====================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role: str = "TEACHER"
    location_ids: list[int] = []


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    location_ids: list[int] | None = None


# ==================== Password & JWT ====================
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


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


# ==================== Session & Authorization ====================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def get_current_location_id() -> int | None:
    return app.storage.user.get("location_id")


def get_current_location_name() -> str:
    return app.storage.user.get("location_name", "Chưa chọn cơ sở")


def load_styles() -> None:
    ui.add_head_html('<link rel="stylesheet" href="/static/style.css">')


def logout() -> None:
    app.storage.user.clear()
    ui.navigate.to("/login")


def store_login_session(user_data: dict[str, Any]) -> None:
    token = create_access_token({"sub": user_data["username"], "role": user_data["role"]})
    app.storage.user.update(
        {
            "token": token,
            "username": user_data["username"],
            "role": user_data["role"],
            "user_id": user_data["id"],
        }
    )


def ensure_logged_in() -> bool:
    if app.storage.user.get("token"):
        return True
    ui.navigate.to("/login")
    return False


def ensure_owner_page() -> bool:
    if not ensure_logged_in():
        return False
    if app.storage.user.get("role", "TEACHER") == "ADMIN":
        return True
    load_styles()
    render_access_denied("Từ chối truy cập. Chỉ Admin mới có quyền.")
    return False


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    if payload is None or payload.get("sub") is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, full_name, role FROM users WHERE username = ? AND is_active = 1",
            (payload["sub"],),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Không tìm thấy người dùng")
    return dict(row)


def require_role(required: str):
    async def check(user: dict = Depends(get_current_user)):
        if ROLE_HIERARCHY.get(user["role"], 0) < ROLE_HIERARCHY.get(required, 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không đủ quyền")
        return user

    return check


# ==================== Database Helpers ====================
def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def audit(conn, actor_id: int, action: str, entity_type: str, entity_id: int, details: dict) -> None:
    conn.execute(
        "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)",
        (actor_id, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False)),
    )


def fetch_login_user(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, hashed_password, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def get_user_locations(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT l.id, l.name, l.address
               FROM locations l
               JOIN user_locations ul ON ul.location_id = l.id
               WHERE ul.user_id = ? AND l.is_active = 1
               ORDER BY l.name""",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_active_locations() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM locations WHERE is_active = 1 ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def fetch_users_with_locations() -> list[dict]:
    with get_db() as conn:
        users = conn.execute(
            "SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY role, username"
        ).fetchall()
        locations = conn.execute(
            """SELECT ul.user_id, l.id, l.name
               FROM user_locations ul
               JOIN locations l ON l.id = ul.location_id
               ORDER BY l.name"""
        ).fetchall()

    by_user: dict[int, list[dict]] = {}
    for loc in locations:
        by_user.setdefault(loc["user_id"], []).append({"id": loc["id"], "name": loc["name"]})

    result = []
    for row in users:
        item = dict(row)
        item["locations"] = by_user.get(row["id"], [])
        item["location_names"] = ", ".join(loc["name"] for loc in item["locations"]) or "Chưa gán"
        item["status"] = "Hoạt động" if row["is_active"] else "Vô hiệu"
        item["role_label"] = ROLE_LABELS.get(row["role"], row["role"])
        item["action"] = row["id"]
        result.append(item)
    return result


def fetch_user_for_edit(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, full_name, role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        location_rows = conn.execute(
            "SELECT location_id FROM user_locations WHERE user_id = ?",
            (user_id,),
        ).fetchall()

    user = dict(row)
    user["location_ids"] = [item["location_id"] for item in location_rows]
    return user


def validate_role(role: str) -> None:
    if role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail="Vai trò không hợp lệ")


def create_user_record(data: UserCreate, actor_id: int) -> int:
    validate_role(data.role)
    username = data.username.strip()
    if not username or not data.password:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên đăng nhập và mật khẩu")

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")

        location_ids = data.location_ids
        if not location_ids:
            location_rows = conn.execute("SELECT id FROM locations WHERE is_active = 1 ORDER BY name").fetchall()
            location_ids = [row["id"] for row in location_rows]

        conn.execute(
            "INSERT INTO users (username, hashed_password, full_name, role) VALUES (?, ?, ?, ?)",
            (username, hash_password(data.password), data.full_name.strip(), data.role),
        )
        user_id = conn.lastrowid

        for location_id in location_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_locations (user_id, location_id) VALUES (?, ?)",
                (user_id, location_id),
            )

        audit(
            conn,
            actor_id,
            "create",
            "user",
            user_id,
            {"username": username, "role": data.role, "location_ids": location_ids},
        )
    return user_id


def update_user_record(user_id: int, data: UserUpdate, actor_id: int) -> None:
    with get_db() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        updates: dict[str, Any] = {}
        if data.full_name is not None:
            updates["full_name"] = data.full_name.strip()
        if data.role is not None:
            validate_role(data.role)
            updates["role"] = data.role
        if data.is_active is not None:
            updates["is_active"] = int(data.is_active)
        if data.password:
            updates["hashed_password"] = hash_password(data.password)

        if updates:
            updates["updated_at"] = now_utc()
            set_clause = ", ".join(f"{field} = ?" for field in updates)
            conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", list(updates.values()) + [user_id])

        if data.location_ids is not None:
            conn.execute("DELETE FROM user_locations WHERE user_id = ?", (user_id,))
            for location_id in data.location_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO user_locations (user_id, location_id) VALUES (?, ?)",
                    (user_id, location_id),
                )

        details = {key: value for key, value in updates.items() if key != "hashed_password"}
        if data.location_ids is not None:
            details["location_ids"] = data.location_ids
        audit(conn, actor_id, "update", "user", user_id, details)


def set_user_active(user_id: int, is_active: bool, actor_id: int) -> None:
    if actor_id == user_id and not is_active:
        raise HTTPException(status_code=400, detail="Không thể vô hiệu hóa chính mình")

    with get_db() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        conn.execute(
            "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if is_active else 0, now_utc(), user_id),
        )
        audit(
            conn,
            actor_id,
            "activate" if is_active else "deactivate",
            "user",
            user_id,
            {"username": row["username"]},
        )


def create_location_record(data: dict, actor_id: int) -> int:
    name = (data.get("name") or "").strip()
    address = (data.get("address") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên cơ sở")

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM locations WHERE name = ?", (name,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Tên cơ sở đã tồn tại")

        conn.execute("INSERT INTO locations (name, address) VALUES (?, ?)", (name, address))
        location_id = conn.lastrowid
        audit(conn, actor_id, "create", "location", location_id, {"name": name})
    return location_id


def update_location_record(location_id: int, data: dict, actor_id: int) -> None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cơ sở")

        name = (data.get("name", row["name"]) or "").strip()
        address = (data.get("address", row["address"]) or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Vui lòng nhập tên cơ sở")

        conn.execute("UPDATE locations SET name = ?, address = ? WHERE id = ?", (name, address, location_id))
        audit(conn, actor_id, "update", "location", location_id, {"name": name, "address": address})


def set_location_active(location_id: int, is_active: bool, actor_id: int) -> None:
    with get_db() as conn:
        row = conn.execute("SELECT id, name FROM locations WHERE id = ?", (location_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cơ sở")

        conn.execute("UPDATE locations SET is_active = ? WHERE id = ?", (1 if is_active else 0, location_id))
        audit(
            conn,
            actor_id,
            "activate" if is_active else "deactivate",
            "location",
            location_id,
            {"name": row["name"]},
        )


# ==================== API Router ====================
router = APIRouter(tags=["auth"])


@router.post("/api/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    row = fetch_login_user(form.username)
    if row is None or not row["is_active"] or not verify_password(form.password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai thông tin đăng nhập")
    return Token(access_token=create_access_token({"sub": row["username"], "role": row["role"]}))


@router.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]}


@router.get("/api/my-locations")
def my_locations(user: dict = Depends(get_current_user)):
    return get_user_locations(user["id"])


@router.get("/api/users")
def list_users(user: dict = Depends(require_role("ADMIN"))):
    return fetch_users_with_locations()


@router.post("/api/users", status_code=201)
def create_user(data: UserCreate, user: dict = Depends(require_role("ADMIN"))):
    user_id = create_user_record(data, user["id"])
    return {"id": user_id, "message": "Người dùng đã được tạo"}


@router.put("/api/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, user: dict = Depends(require_role("ADMIN"))):
    update_user_record(user_id, data, user["id"])
    return {"message": "Người dùng đã được cập nhật"}


@router.put("/api/users/{user_id}/deactivate")
def deactivate_user(user_id: int, user: dict = Depends(require_role("ADMIN"))):
    set_user_active(user_id, False, user["id"])
    return {"message": "Người dùng đã bị vô hiệu hóa"}


@router.get("/api/locations")
def list_locations(user: dict = Depends(require_role("ADMIN"))):
    return fetch_active_locations()


@router.post("/api/locations", status_code=201)
def create_location(data: dict, user: dict = Depends(require_role("ADMIN"))):
    location_id = create_location_record(data, user["id"])
    return {"id": location_id, "message": "Cơ sở đã được tạo"}


@router.put("/api/locations/{location_id}")
def update_location(location_id: int, data: dict, user: dict = Depends(require_role("ADMIN"))):
    update_location_record(location_id, data, user["id"])
    return {"message": "Cơ sở đã được cập nhật"}


# ==================== Shared UI ====================
def render_access_denied(message: str) -> None:
    with ui.element("div").classes("page-container"):
        with ui.card().classes("custom-card p-6 w-full"):
            ui.label("🚫 Không có quyền truy cập").classes("text-xl font-bold text-red-600")
            ui.label(message).classes("text-gray-600 mt-2")


def render_auth_header(icon: str, title: str, subtitle: str) -> None:
    with ui.element("div").classes("login-header"):
        ui.label(icon).classes("logo")
        ui.label(title).classes("title")
        ui.label(subtitle).classes("subtitle")


def render_page_title(icon: str, title: str, subtitle: str = "") -> None:
    with ui.element("div").classes("page-container pb-0"):
        with ui.row().classes("items-center justify-between w-full gap-3"):
            with ui.row().classes("items-center page-title mb-0"):
                ui.label(icon).classes("text-2xl")
                with ui.column().classes("gap-0"):
                    ui.label(title)
                    if subtitle:
                        ui.label(subtitle).classes("text-sm font-normal text-gray-500")


def role_display(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def ui_error_from_exception(exc: Exception, fallback: str) -> None:
    detail = getattr(exc, "detail", None)
    ui.notify(str(detail or fallback), type="negative")


def switch_location(location_id: int, location_name: str):
    app.storage.user.update({"location_id": location_id, "location_name": location_name})
    ui.notify(f"Đã chuyển sang {location_name}", type="positive")
    ui.run_javascript("location.href = '/'")
    # Force page reload so all data refreshes for the new location


def render_location_dialog():
    loc_id = get_current_location_id()
    loc_name = get_current_location_name()
    locations = get_user_locations(app.storage.user.get("user_id", 0))

    with ui.dialog() as dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("📍 Chọn cơ sở làm việc").classes("section-header mt-0 pr-8")
        if loc_id:
            ui.label(f"Đang làm việc tại: {loc_name}").classes("status-chip ok mb-3")

        if not locations:
            ui.label("Bạn chưa được gán vào cơ sở nào.").classes("text-center text-gray-500 py-4")
            ui.label("Vui lòng liên hệ quản lý.").classes("text-center text-sm text-gray-400")
        elif len(locations) == 1 and locations[0]["id"] == loc_id:
            ui.label("Bạn chỉ có một cơ sở làm việc.").classes("text-center text-gray-500 py-4")
        else:
            with ui.column().classes("w-full gap-2"):
                for location in locations:
                    is_current = location["id"] == loc_id
                    with ui.button(
                        on_click=lambda item=location: (dialog.close(), switch_location(item["id"], item["name"])),
                        icon="check" if is_current else "place",
                    ).props("unelevated" if is_current else "outlined").classes("location-choice w-full"):
                        with ui.column().classes("items-start gap-0"):
                            ui.label(location["name"]).classes("font-bold")
                            if location.get("address"):
                                ui.label(location["address"]).classes("text-xs text-gray-500")

        ui.button("Đóng", on_click=dialog.close, icon="close").props("outlined").classes("w-full mt-4")

    return dialog


def render_navbar():
    """Shared responsive navbar with location switcher + mobile bottom bar."""
    load_styles()

    role = app.storage.user.get("role", "TEACHER")
    username = app.storage.user.get("username", "")
    loc_id = get_current_location_id()
    loc_name = get_current_location_name()
    loc_dialog = render_location_dialog()

    # Decide if the badge should be clickable: user has >1 assigned location
    user_locs = get_user_locations(app.storage.user.get("user_id", 0))
    has_multiple_locs = len(user_locs) > 1
    badge_classes = f"location-badge {'active' if loc_id else 'inactive'}"
    if has_multiple_locs:
        badge_classes += " clickable pulse"
    badge_tooltip = (
        f"Đổi sang cơ sở khác ({len(user_locs)} cơ sở)"
        if has_multiple_locs
        else "Cơ sở làm việc hiện tại"
    )

    menu_drawer = ui.left_drawer(fixed=True, value=False).classes("app-drawer")
    with menu_drawer:
        with ui.column().classes("w-full gap-1 p-3"):
            ui.label("Yoga Management").classes("text-lg font-bold px-2 py-2")
            ui.label(f"📍 {loc_name}").classes("location-badge active w-full justify-center mb-2")
            ui.separator()

            ui.label("Vận hành").classes("drawer-section-label")
            menu_items = [
                ("dashboard", "Bảng điều khiển", "/dashboard"),
                ("groups", "Khách hàng", "/customers"),
                ("check_circle", "Check-in", "/checkin"),
                ("point_of_sale", "Bán hàng", "/sales"),
                ("shopping_cart", "Gói trả trước", "/packages"),
                ("fitness_center", "PT", "/pt"),
            ]
            for icon, label, path in menu_items:
                ui.button(label, icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props(
                    "flat no-caps align=left"
                ).classes("drawer-nav-btn w-full")

            ui.separator()
            ui.label("Sản phẩm & tồn kho").classes("drawer-section-label")
            for icon, label, path in [
                ("local_cafe", "Đồ uống", "/drinks"),
                ("science", "Nguyên liệu", "/ingredients"),
                ("inventory_2", "Sản phẩm", "/products"),
            ]:
                ui.button(label, icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props(
                    "flat no-caps align=left"
                ).classes("drawer-nav-btn w-full")

            if role in ("OWNER", "ADMIN"):
                ui.separator()
                ui.label("Quản lý").classes("drawer-section-label")
                for icon, label, path in [
                    ("history", "Nhật ký", "/audit"),
                    ("list_alt", "Mẫu gói", "/package-templates"),
                    ("upgrade", "Nâng cấp gói", "/packages/upgrade"),
                ]:
                    ui.button(label, icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props(
                        "flat no-caps align=left"
                    ).classes("drawer-nav-btn w-full")

            if role == "ADMIN":
                ui.separator()
                ui.label("Quản trị").classes("drawer-section-label")
                ui.button("Người dùng", icon="manage_accounts", on_click=lambda: ui.navigate.to("/users")).props(
                    "flat no-caps align=left"
                ).classes("drawer-nav-btn w-full")
                ui.button("Cơ sở", icon="business", on_click=lambda: ui.navigate.to("/locations")).props(
                    "flat no-caps align=left"
                ).classes("drawer-nav-btn w-full")

            ui.separator()
            ui.button("Đổi cơ sở", icon="place", on_click=loc_dialog.open).props("flat no-caps align=left").classes(
                "drawer-nav-btn w-full"
            )
            ui.button("Đăng xuất", icon="logout", on_click=logout).props("flat no-caps align=left").classes(
                "drawer-nav-btn w-full text-red-600"
            )

    # ═══ TOP HEADER (desktop: full; mobile: brand + menu + logout) ═══
    with ui.header(fixed=True).props("elevated").classes("app-header items-center justify-between"):
        with ui.row().classes("items-center gap-1 md:gap-3"):
            # Mobile brand (compact)
            ui.label("🧘").classes("text-xl")
            ui.label("YM").classes("text-base font-bold md:hidden")
            # Desktop brand
            ui.label("Yoga Management").classes("hidden md:block text-lg font-bold")

        with ui.row().classes("items-center gap-1 md:gap-2"):
            # Location badge (hidden on very small screens, visible sm+)
            badge = ui.element("div").classes(badge_classes + " hidden sm:inline-flex")
            if has_multiple_locs:
                badge.on("click", loc_dialog.open)
            badge.tooltip(badge_tooltip)
            with badge:
                ui.label("📍").classes("text-xs")
                ui.label(loc_name).classes("text-xs font-semibold")
                if has_multiple_locs:
                    ui.label("⇄").classes("badge-swap-icon text-xs")

            # Username (desktop only)
            ui.label(f"👤 {username}").classes("hidden lg:block text-xs text-gray-600")

            # Desktop quick actions
            with ui.row().classes("hidden md:flex items-center gap-1"):
                ui.button("Bán hàng", icon="point_of_sale", on_click=lambda: ui.navigate.to("/sales")).props(
                    "flat dense"
                )
                ui.button("Check-in", icon="check_circle", on_click=lambda: ui.navigate.to("/checkin")).props(
                    "flat dense"
                )
                ui.button("Khách hàng", icon="groups", on_click=lambda: ui.navigate.to("/customers")).props(
                    "flat dense"
                )

            # Drawer menu trigger
            ui.button(icon="menu", on_click=menu_drawer.toggle).props("flat round dense").classes("touch-target").tooltip("Menu")

            # Desktop logout
            ui.button(icon="logout", on_click=logout).props("flat round dense").tooltip("Đăng xuất").classes("hidden md:inline-flex")

    # ═══ MOBILE BOTTOM NAVIGATION BAR ═══
    with ui.footer().classes("md:hidden").props("bordered").style("background: white !important"):
        with ui.row().classes("w-full justify-around items-center py-1"):
            _mb_btn("📊", "Tổng quan", "/dashboard")
            _mb_btn("💰", "Bán hàng", "/sales")
            _mb_btn("🟡", "Check-in", "/checkin")
            _mb_btn("👥", "Khách", "/customers")
            _mb_btn("☰", "Menu", None, loc_dialog.open)


def _mb_btn(icon: str, label: str, path: str | None, on_click=None):
    """Render a mobile bottom-nav button."""
    if path:
        btn = ui.button(icon=icon, on_click=lambda p=path: ui.navigate.to(p))
    else:
        btn = ui.button(icon=icon, on_click=on_click)
    btn.props("flat dense padding-none").classes("mobile-nav-btn flex flex-col items-center gap-0")
    with btn:
        ui.label(label).classes("text-[10px] leading-none mt-1")


# ==================== Login & Location Pages ====================
@ui.page("/login")
def login_page():
    load_styles()
    ui.query("body").classes("login-body")

    with ui.element("div").classes("login-center auth-shell"):
        with ui.card().classes("login-card auth-card p-8 md:p-10 w-full max-w-md"):
            render_auth_header("🧘", "Yoga Management", "Đăng nhập để quản lý phòng tập")

            username = ui.input("Tên đăng nhập").props("outlined dense").classes("w-full mb-3")
            password = ui.input("Mật khẩu", password=True, password_toggle_button=True).props("outlined dense").classes(
                "w-full mb-2"
            )
            error_label = ui.label().classes("text-red-500 text-sm mb-3 min-h-5")

            def handle_login():
                error_label.set_text("")
                user_data = fetch_login_user(username.value or "")

                if user_data is None or not verify_password(password.value or "", user_data["hashed_password"]):
                    error_label.set_text("Sai tên đăng nhập hoặc mật khẩu")
                    return

                if not user_data["is_active"]:
                    error_label.set_text("Tài khoản đã bị vô hiệu hóa")
                    return

                store_login_session(user_data)
                ui.navigate.to("/select-location")

            password.on("keydown.enter", lambda _: handle_login())
            ui.button("Đăng nhập", on_click=handle_login, icon="login").props("unelevated").classes(
                "w-full btn-primary"
            )


@ui.page("/select-location")
def select_location_page():
    if not ensure_logged_in():
        return

    user_id = app.storage.user.get("user_id", 0)
    locations = get_user_locations(user_id)

    if app.storage.user.get("location_id"):
        ui.navigate.to("/")
        return

    if len(locations) == 1:
        location = locations[0]
        app.storage.user.update({"location_id": location["id"], "location_name": location["name"]})
        ui.navigate.to("/")
        return

    load_styles()
    ui.query("body").classes("location-page")

    with ui.element("div").classes("login-center auth-shell"):
        with ui.card().classes("login-card auth-card p-8 md:p-10 w-full max-w-md"):
            render_auth_header("📍", "Chọn cơ sở làm việc", f"Xin chào, {app.storage.user.get('username', '')}")

            if not locations:
                with ui.element("div").classes("empty-state"):
                    ui.label("Bạn chưa được gán vào cơ sở nào.").classes("font-bold")
                    ui.label("Vui lòng liên hệ quản lý để được cấp quyền cơ sở.").classes("text-sm")
                ui.button("Quay lại đăng nhập", on_click=logout, icon="arrow_back").props("outlined").classes(
                    "w-full mt-4"
                )
                return

            with ui.column().classes("w-full gap-2"):
                for location in locations:
                    with ui.button(
                        on_click=lambda item=location: switch_location(item["id"], item["name"]),
                        icon="place",
                    ).props("unelevated").classes("location-choice w-full btn-primary"):
                        with ui.column().classes("items-start gap-0"):
                            ui.label(location["name"]).classes("font-bold")
                            if location.get("address"):
                                ui.label(location["address"]).classes("text-xs opacity-80")

            ui.button("Đăng xuất", on_click=logout, icon="logout").props("outlined").classes("w-full mt-4 text-red-500")


def _pick_location(location_id: int, location_name: str):
    switch_location(location_id, location_name)


# ==================== User Management Page ====================
@ui.page("/users")
def users_page():
    if not ensure_owner_page():
        return

    render_navbar()
    render_page_title("👥", "Quản lý người dùng", "Tạo tài khoản, phân quyền và quản lý quyền truy cập cơ sở")

    users = ui.table(
        columns=[
            {"name": "username", "label": "Tên đăng nhập", "field": "username", "align": "left"},
            {"name": "full_name", "label": "Họ tên", "field": "full_name", "align": "left"},
            {"name": "role_label", "label": "Vai trò", "field": "role_label", "align": "left"},
            {"name": "location_names", "label": "Cơ sở", "field": "location_names", "align": "left"},
            {"name": "status", "label": "Trạng thái", "field": "status", "align": "left"},
            {"name": "action", "label": "Thao tác", "field": "action", "align": "center"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full")

    locations = fetch_active_locations()
    location_options = {location["id"]: location["name"] for location in locations}

    def refresh():
        users.rows = fetch_users_with_locations()
        users.update()

    def reset_create_form():
        c_username.value = ""
        c_password.value = ""
        c_fullname.value = ""
        c_role.value = "TEACHER"
        c_locations.value = []
        c_error.set_text("")

    with ui.dialog() as create_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("👤 Người dùng mới").classes("section-header mt-0 pr-8")
        c_username = ui.input("Tên đăng nhập *").props("outlined").classes("w-full mb-2")
        c_password = ui.input("Mật khẩu *", password=True, password_toggle_button=True).props("outlined").classes(
            "w-full mb-2"
        )
        c_fullname = ui.input("Họ tên").props("outlined").classes("w-full mb-2")
        c_role = ui.select(ROLE_LABELS, label="Vai trò *", value="TEACHER").props("outlined").classes("w-full mb-2")
        c_locations = ui.select(location_options, label="Cơ sở", multiple=True).props("outlined").classes("w-full mb-1")
        ui.label("Có thể để trống: người dùng mới sẽ tự động được gán vào tất cả cơ sở đang hoạt động.").classes(
            "text-xs text-gray-500 mb-3"
        )
        c_error = ui.label().classes("text-red-500 text-sm min-h-5")

        def handle_create():
            try:
                create_user_record(
                    UserCreate(
                        username=c_username.value or "",
                        password=c_password.value or "",
                        full_name=c_fullname.value or "",
                        role=c_role.value or "TEACHER",
                        location_ids=c_locations.value or [],
                    ),
                    app.storage.user.get("user_id", 1),
                )
            except Exception as exc:
                c_error.set_text(str(getattr(exc, "detail", "Không thể tạo người dùng")))
                return

            create_dialog.close()
            reset_create_form()
            refresh()
            ui.notify("Người dùng đã được tạo", type="positive")

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary")

    with ui.dialog() as edit_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("✏️ Sửa người dùng").classes("section-header mt-0 pr-8")
        e_id = ui.label().classes("hidden")
        e_username = ui.input("Tên đăng nhập").props("outlined readonly").classes("w-full mb-2")
        e_fullname = ui.input("Họ tên").props("outlined").classes("w-full mb-2")
        e_role = ui.select(ROLE_LABELS, label="Vai trò").props("outlined").classes("w-full mb-2")
        e_password = ui.input("Mật khẩu mới", password=True, password_toggle_button=True).props("outlined").classes(
            "w-full mb-2"
        )
        e_locations = ui.select(location_options, label="Cơ sở", multiple=True).props("outlined").classes("w-full mb-3")
        e_error = ui.label().classes("text-red-500 text-sm min-h-5")

        def handle_edit():
            if not e_id.text:
                return

            try:
                update_user_record(
                    int(e_id.text),
                    UserUpdate(
                        full_name=e_fullname.value or "",
                        role=e_role.value,
                        password=e_password.value or None,
                        location_ids=e_locations.value or [],
                    ),
                    app.storage.user.get("user_id", 1),
                )
            except Exception as exc:
                e_error.set_text(str(getattr(exc, "detail", "Không thể cập nhật người dùng")))
                return

            edit_dialog.close()
            refresh()
            ui.notify("Người dùng đã được cập nhật", type="positive")

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary")

    with ui.element("div").classes("page-container"):
        with ui.card().classes("auth-admin-card custom-card p-4"):
            with ui.row().classes("admin-toolbar items-center justify-between w-full gap-2 mb-4"):
                with ui.column().classes("gap-0"):
                    ui.label("Danh sách người dùng").classes("font-bold text-lg")
                    ui.label("Người dùng mới được gán mặc định vào tất cả cơ sở đang hoạt động").classes("text-sm text-gray-500")
                with ui.row().classes("gap-2"):
                    ui.button("Người dùng mới", on_click=lambda: (reset_create_form(), create_dialog.open()), icon="add").props(
                        "unelevated"
                    ).classes("btn-success")
                    ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

            users.move()

    def open_edit(row_id):
        data = fetch_user_for_edit(int(row_id))
        if not data:
            ui.notify("Không tìm thấy người dùng", type="warning")
            return

        e_id.set_text(str(data["id"]))
        e_username.value = data["username"]
        e_fullname.value = data["full_name"] or ""
        e_role.value = data["role"]
        e_password.value = ""
        e_locations.value = data["location_ids"]
        e_error.set_text("")
        edit_dialog.open()

    with ui.dialog() as confirm_user_status_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=confirm_user_status_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("Xác nhận đổi trạng thái").classes("section-header mt-0 pr-8")
        confirm_user_status_text = ui.label().classes("text-sm text-gray-600 mb-4")
        confirm_user_status_id = ui.number("confirm_user_status_id").props("hidden")
        confirm_user_status_active = ui.checkbox("active").classes("hidden")

        def confirm_change_user_status():
            confirm_user_status_dialog.close()
            change_user_status(int(confirm_user_status_id.value or 0), bool(confirm_user_status_active.value))

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Hủy", on_click=confirm_user_status_dialog.close, icon="close").props("outlined")
            ui.button("Xác nhận", on_click=confirm_change_user_status, icon="check").props("unelevated color=negative")

    def open_confirm_user_status(row_id, is_active: bool):
        confirm_user_status_id.value = int(row_id)
        confirm_user_status_active.value = is_active
        action_label = "kích hoạt lại" if is_active else "vô hiệu hóa"
        confirm_user_status_text.set_text(f"Bạn có chắc muốn {action_label} người dùng này?")
        confirm_user_status_dialog.open()

    def change_user_status(row_id, is_active: bool):
        try:
            set_user_active(int(row_id), is_active, app.storage.user.get("user_id", 1))
        except Exception as exc:
            ui_error_from_exception(exc, "Không thể đổi trạng thái người dùng")
            return

        refresh()
        ui.notify("Đã cập nhật trạng thái người dùng", type="positive")

    users.add_slot(
        "body-cell-action",
        """
        <q-td :props="props">
            <div class="action-buttons">
                <q-btn flat round dense icon="edit" color="blue" @click="$parent.$emit('edit_user', props.value)">
                    <q-tooltip>Sửa</q-tooltip>
                </q-btn>
                <q-btn flat round dense icon="block" color="red" @click="$parent.$emit('deactivate_user', props.value)">
                    <q-tooltip>Vô hiệu hóa</q-tooltip>
                </q-btn>
                <q-btn flat round dense icon="check_circle" color="green" @click="$parent.$emit('activate_user', props.value)">
                    <q-tooltip>Kích hoạt</q-tooltip>
                </q-btn>
            </div>
        </q-td>
        """,
    )
    users.on("edit_user", lambda e: open_edit(e.args))
    users.on("deactivate_user", lambda e: open_confirm_user_status(e.args, False))
    users.on("activate_user", lambda e: open_confirm_user_status(e.args, True))

    refresh()


# ==================== Location Management Page ====================
@ui.page("/locations")
def locations_page():
    if not ensure_owner_page():
        return

    render_navbar()
    render_page_title("🏢", "Quản lý cơ sở", "Tạo và quản lý các chi nhánh/cơ sở làm việc")

    table = ui.table(
        columns=[
            {"name": "name", "label": "Tên cơ sở", "field": "name", "align": "left"},
            {"name": "address", "label": "Địa chỉ", "field": "address", "align": "left"},
            {"name": "created_at", "label": "Ngày tạo", "field": "created_at", "align": "left"},
            {"name": "action", "label": "Thao tác", "field": "action", "align": "center"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full")

    def refresh_locations():
        rows = fetch_active_locations()
        for row in rows:
            row["action"] = row["id"]
        table.rows = rows
        table.update()

    def reset_location_form():
        l_name.value = ""
        l_address.value = ""
        l_error.set_text("")

    with ui.dialog() as create_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("🏢 Cơ sở mới").classes("section-header mt-0 pr-8")
        l_name = ui.input("Tên cơ sở *").props("outlined").classes("w-full mb-2")
        l_address = ui.input("Địa chỉ").props("outlined").classes("w-full mb-3")
        l_error = ui.label().classes("text-red-500 text-sm min-h-5")

        def handle_create_location():
            try:
                create_location_record(
                    {"name": l_name.value or "", "address": l_address.value or ""},
                    app.storage.user.get("user_id", 1),
                )
            except Exception as exc:
                l_error.set_text(str(getattr(exc, "detail", "Không thể tạo cơ sở")))
                return

            create_dialog.close()
            reset_location_form()
            refresh_locations()
            ui.notify("Cơ sở đã được tạo", type="positive")

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
            ui.button("Lưu", on_click=handle_create_location, icon="save").props("unelevated").classes("btn-primary")

    with ui.dialog() as edit_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("✏️ Sửa cơ sở").classes("section-header mt-0 pr-8")
        le_id = ui.label().classes("hidden")
        le_name = ui.input("Tên cơ sở *").props("outlined").classes("w-full mb-2")
        le_address = ui.input("Địa chỉ").props("outlined").classes("w-full mb-3")
        le_error = ui.label().classes("text-red-500 text-sm min-h-5")

        def handle_edit_location():
            if not le_id.text:
                return

            try:
                update_location_record(
                    int(le_id.text),
                    {"name": le_name.value or "", "address": le_address.value or ""},
                    app.storage.user.get("user_id", 1),
                )
            except Exception as exc:
                le_error.set_text(str(getattr(exc, "detail", "Không thể cập nhật cơ sở")))
                return

            edit_dialog.close()
            refresh_locations()
            ui.notify("Cơ sở đã được cập nhật", type="positive")

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
            ui.button("Lưu", on_click=handle_edit_location, icon="save").props("unelevated").classes("btn-primary")

    with ui.element("div").classes("page-container"):
        with ui.card().classes("auth-admin-card custom-card p-4"):
            with ui.row().classes("admin-toolbar items-center justify-between w-full gap-2 mb-4"):
                with ui.column().classes("gap-0"):
                    ui.label("Danh sách cơ sở").classes("font-bold text-lg")
                    ui.label("Cơ sở bị vô hiệu hóa sẽ không còn xuất hiện trong lựa chọn làm việc").classes(
                        "text-sm text-gray-500"
                    )
                with ui.row().classes("gap-2"):
                    ui.button("Cơ sở mới", on_click=lambda: (reset_location_form(), create_dialog.open()), icon="add").props(
                        "unelevated"
                    ).classes("btn-success")
                    ui.button("Làm mới", on_click=refresh_locations, icon="refresh").props("outlined")

            table.move()

    def open_edit_location(row_id):
        with get_db() as conn:
            row = conn.execute("SELECT id, name, address FROM locations WHERE id = ?", (int(row_id),)).fetchone()

        if not row:
            ui.notify("Không tìm thấy cơ sở", type="warning")
            return

        le_id.set_text(str(row["id"]))
        le_name.value = row["name"]
        le_address.value = row["address"] or ""
        le_error.set_text("")
        edit_dialog.open()

    with ui.dialog() as confirm_location_deactivate_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=confirm_location_deactivate_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("Xác nhận vô hiệu hóa").classes("section-header mt-0 pr-8")
        ui.label("Bạn có chắc muốn vô hiệu hóa cơ sở này? Cơ sở sẽ không còn xuất hiện trong lựa chọn làm việc.").classes(
            "text-sm text-gray-600 mb-4"
        )
        confirm_location_deactivate_id = ui.number("confirm_location_deactivate_id").props("hidden")

        def confirm_deactivate_location():
            confirm_location_deactivate_dialog.close()
            deactivate_location_ui(int(confirm_location_deactivate_id.value or 0))

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Hủy", on_click=confirm_location_deactivate_dialog.close, icon="close").props("outlined")
            ui.button("Vô hiệu hóa", on_click=confirm_deactivate_location, icon="delete").props("unelevated color=negative")

    def open_confirm_deactivate_location(row_id):
        confirm_location_deactivate_id.value = int(row_id)
        confirm_location_deactivate_dialog.open()

    def deactivate_location_ui(row_id):
        try:
            set_location_active(int(row_id), False, app.storage.user.get("user_id", 1))
        except Exception as exc:
            ui_error_from_exception(exc, "Không thể vô hiệu hóa cơ sở")
            return

        refresh_locations()
        ui.notify("Cơ sở đã bị vô hiệu hóa", type="positive")

    table.add_slot(
        "body-cell-action",
        """
        <q-td :props="props">
            <div class="action-buttons">
                <q-btn flat round dense icon="edit" color="blue" @click="$parent.$emit('edit_location', props.value)">
                    <q-tooltip>Sửa</q-tooltip>
                </q-btn>
                <q-btn flat round dense icon="delete" color="red" @click="$parent.$emit('deactivate_location', props.value)">
                    <q-tooltip>Vô hiệu hóa</q-tooltip>
                </q-btn>
            </div>
        </q-td>
        """,
    )
    table.on("edit_location", lambda e: open_edit_location(e.args))
    table.on("deactivate_location", lambda e: open_confirm_deactivate_location(e.args))

    refresh_locations()
