"""Package template management - catalog of package presets for fast selling."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/package-templates", tags=["package-templates"])

PACKAGE_TYPES = [
    ("BASIC", "Gói cơ bản (tập + uống theo buổi)"),
    ("FAT_LOSS", "Gói giảm mỡ (uống nhiều ly)"),
    ("COMBO", "Gói combo (tập + uống nhiều)"),
]


class PackageTemplateCreate(BaseModel):
    name: str
    package_type: str
    duration_days: int = 90
    total_sessions: int = 0
    total_drinks: int = 0
    total_amount: float = 0


class PackageTemplateUpdate(BaseModel):
    name: str | None = None
    package_type: str | None = None
    duration_days: int | None = None
    total_sessions: int | None = None
    total_drinks: int | None = None
    total_amount: float | None = None
    is_active: int | None = None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.get("")
def list_templates(location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if location_id:
            rows = conn.execute(
                "SELECT * FROM package_templates WHERE is_active = 1 AND location_id = ? ORDER BY total_amount",
                (location_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM package_templates WHERE is_active = 1 ORDER BY total_amount"
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_template(data: PackageTemplateCreate, user: dict = Depends(require_role("MANAGER"))):
    if data.package_type not in [t[0] for t in PACKAGE_TYPES]:
        raise HTTPException(status_code=400, detail="Loại gói không hợp lệ")
    loc_id = get_current_location_id()
    if not loc_id:
        raise HTTPException(status_code=400, detail="Chưa chọn cơ sở")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO package_templates
               (location_id, name, package_type, duration_days,
                total_sessions, total_drinks, total_amount, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (loc_id, data.name, data.package_type, data.duration_days,
             data.total_sessions, data.total_drinks, data.total_amount, user["id"]),
        )
        tid = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'package_template', ?, ?)""",
            (loc_id, user["id"], tid, f'{{"name":"{data.name}","amount":{data.total_amount}}}'),
        )
    return {"id": tid, "message": "Mẫu gói đã được tạo"}


@router.put("/{template_id}")
def update_template(template_id: int, data: PackageTemplateUpdate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM package_templates WHERE id = ?", (template_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mẫu gói")
        updates = {}
        for f in ["name", "package_type", "duration_days", "total_sessions", "total_drinks", "total_amount", "is_active"]:
            v = getattr(data, f)
            if v is not None:
                updates[f] = v
        if not updates:
            return {"message": "Không có thay đổi"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [template_id]
        conn.execute(f"UPDATE package_templates SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'update', 'package_template', ?, ?)""",
            (row["location_id"], user["id"], template_id, str(updates)),
        )
    return {"message": "Mẫu gói đã được cập nhật"}


@router.delete("/{template_id}")
def deactivate_template(template_id: int, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM package_templates WHERE id = ?", (template_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mẫu gói")
        conn.execute("UPDATE package_templates SET is_active = 0 WHERE id = ?", (template_id,))
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'deactivate', 'package_template', ?, ?)""",
            (row["location_id"], user["id"], template_id, f'{{"name":"{row["name"]}"}}'),
        )
    return {"message": "Mẫu gói đã bị vô hiệu hóa"}


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/package-templates")
def package_templates_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return
    render()
    render_navbar()


def render():
    role = app.storage.user.get("role", "STAFF")
    loc_id = get_current_location_id()

    ui.label("Mẫu gói tập").classes("text-2xl font-bold mb-4")

    type_label = {k: v for k, v in PACKAGE_TYPES}

    template_table = ui.table(
        columns=[
            {"name": "name", "label": "Tên mẫu", "field": "name"},
            {"name": "type", "label": "Loại", "field": "type"},
            {"name": "duration", "label": "Thời hạn (ngày)", "field": "duration"},
            {"name": "sessions", "label": "Số buổi", "field": "sessions"},
            {"name": "drinks", "label": "Số ly", "field": "drinks"},
            {"name": "amount", "label": "Giá bán", "field": "amount"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM package_templates WHERE is_active = 1 AND location_id = ? ORDER BY total_amount",
                (loc_id,),
            ).fetchall()
        template_table.rows = [
            {
                "id": r["id"],
                "name": r["name"],
                "type": type_label.get(r["package_type"], r["package_type"]),
                "duration": r["duration_days"],
                "sessions": r["total_sessions"],
                "drinks": r["total_drinks"],
                "amount": f"{r['total_amount']:,.0f}đ",
            }
            for r in rows
        ]
        template_table.update()

    # Create dialog
    with ui.dialog() as create_dialog, ui.card().classes("p-6 w-full max-w-lg"):
        ui.label("Tạo mẫu gói mới").classes("text-xl font-bold mb-4")
        t_name = ui.input("Tên mẫu *").props("outlined").classes("w-full mb-2")
        t_type = ui.select({k: v for k, v in PACKAGE_TYPES}, label="Loại gói *").props("outlined").classes("w-full mb-2")
        t_duration = ui.number("Thời hạn (ngày)", value=90).props("outlined").classes("w-full mb-2")
        t_sessions = ui.number("Số buổi tập", value=0).props("outlined").classes("w-full mb-2")
        t_drinks = ui.number("Số ly đồ uống", value=0).props("outlined").classes("w-full mb-2")
        t_amount = ui.number("Giá bán (VNĐ)", value=0).props("outlined").classes("w-full mb-4")
        err = ui.label().classes("text-red-500 text-sm")

        def handle_create():
            if not t_name.value or not t_type.value:
                err.set_text("Vui lòng nhập tên và chọn loại gói")
                return
            user_id = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO package_templates
                       (location_id, name, package_type, duration_days,
                        total_sessions, total_drinks, total_amount, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (loc_id, t_name.value, t_type.value, int(t_duration.value or 0),
                     int(t_sessions.value or 0), int(t_drinks.value or 0),
                     float(t_amount.value or 0), user_id),
                )
                conn.execute(
                    """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                       VALUES (?, ?, 'create', 'package_template', ?, ?)""",
                    (loc_id, user_id, conn.lastrowid, f'{{"name":"{t_name.value}"}}'),
                )
            create_dialog.close()
            refresh()
            ui.notify("Đã tạo mẫu gói", type="positive")

        ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    if role in ("MANAGER", "OWNER"):
        with ui.row().classes("gap-2 mb-4"):
            ui.button("Tạo mẫu gói", on_click=create_dialog.open, icon="add").props("unelevated").classes("bg-green-600 text-white")
            ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

    refresh()