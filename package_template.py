"""Membership package template management: catalog of reusable packages."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from auth import get_current_location_id, render_navbar, require_role
from database import get_db


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------
PACKAGE_TYPES = [
    ("BASIC", "Cơ bản"),
    ("FAT_LOSS", "Giảm mỡ"),
    ("COMBO", "Combo"),
]

TYPE_LABELS = dict(PACKAGE_TYPES)

router = APIRouter(prefix="/api/package-templates", tags=["package-templates"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class PackageTemplateCreate(BaseModel):
    name: str
    package_type: str
    duration_days: int = 90
    total_sessions: int = 0
    total_drinks: int = 0
    total_amount: float = 0
    description: str = ""


class PackageTemplateUpdate(BaseModel):
    name: str | None = None
    package_type: str | None = None
    duration_days: int | None = None
    total_sessions: int | None = None
    total_drinks: int | None = None
    total_amount: float | None = None
    description: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@router.get("")
def list_templates(user: dict = Depends(require_role("TEACHER"))):
    loc_id = get_current_location_id()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM package_templates WHERE is_active = 1 AND location_id = ? ORDER BY total_amount",
            (loc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_template(data: PackageTemplateCreate, user: dict = Depends(require_role("OWNER"))):
    if data.package_type not in TYPE_LABELS:
        raise HTTPException(status_code=400, detail="Loại gói không hợp lệ")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên gói")
    loc_id = get_current_location_id()
    if not loc_id:
        raise HTTPException(status_code=400, detail="Chưa chọn cơ sở")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO package_templates
               (location_id, name, description, package_type, duration_days,
                total_sessions, total_drinks, total_amount, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                loc_id,
                data.name.strip(),
                data.description or "",
                data.package_type,
                data.duration_days,
                data.total_sessions,
                data.total_drinks,
                data.total_amount,
                user["id"],
            ),
        )
        tid = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'package_template', ?, ?)""",
            (
                loc_id,
                user["id"],
                tid,
                f'{{"name":"{data.name.strip()}","amount":{data.total_amount}}}',
            ),
        )
    return {"id": tid, "message": "Mẫu gói đã được tạo"}


@router.put("/{template_id}")
def update_template(template_id: int, data: PackageTemplateUpdate, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM package_templates WHERE id = ?", (template_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mẫu gói")
        updates = {}
        for f in [
            "name",
            "package_type",
            "duration_days",
            "total_sessions",
            "total_drinks",
            "total_amount",
            "description",
            "is_active",
        ]:
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
def deactivate_template(template_id: int, user: dict = Depends(require_role("OWNER"))):
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
    role = app.storage.user.get("role", "TEACHER")
    loc_id = get_current_location_id()

    # Page title
    with ui.element("div").classes("page-container pb-0"):
        with ui.row().classes("items-center page-title w-full gap-2"):
            ui.label("🔧").classes("text-2xl")
            with ui.column().classes("gap-0"):
                ui.label("Quản lý gói tập")
                ui.label("Danh mục các mẫu gói tập dùng để gán cho khách hàng").classes(
                    "text-sm font-normal text-gray-500"
                )

    template_table = ui.table(
        columns=[
            {"name": "name", "label": "Tên gói", "field": "name", "align": "left"},
            {"name": "type", "label": "Loại", "field": "type", "align": "left"},
            {"name": "duration", "label": "Thời hạn (ngày)", "field": "duration", "align": "right"},
            {"name": "sessions", "label": "Số buổi", "field": "sessions", "align": "right"},
            {"name": "drinks", "label": "Số ly", "field": "drinks", "align": "right"},
            {"name": "amount", "label": "Giá bán", "field": "amount", "align": "right"},
            {"name": "action", "label": "Thao tác", "field": "action", "align": "center"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full")

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
                "type": TYPE_LABELS.get(r["package_type"], r["package_type"]),
                "duration": r["duration_days"],
                "sessions": r["total_sessions"],
                "drinks": r["total_drinks"],
                "amount": f"{r['total_amount']:,.0f}đ",
                "action": r["id"],
            }
            for r in rows
        ]
        template_table.update()

    def reset_create_form():
        t_name.value = ""
        t_type.value = None
        t_duration.value = 90
        t_sessions.value = 0
        t_drinks.value = 0
        t_amount.value = 0
        t_description.value = ""
        t_error.set_text("")

    # Create dialog
    with ui.dialog() as create_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("📦 Tạo mẫu gói mới").classes("section-header mt-0 pr-8")
        t_name = ui.input("Tên mẫu *").props("outlined").classes("w-full mb-2")
        t_type = ui.select({k: v for k, v in PACKAGE_TYPES}, label="Loại gói *").props("outlined").classes("w-full mb-2")
        t_description = ui.input("Mô tả").props("outlined").classes("w-full mb-2")
        with ui.row().classes("w-full gap-2 mb-2"):
            t_duration = ui.number("Thời hạn (ngày)", value=90, min=1).props("outlined").classes("flex-1")
            t_sessions = ui.number("Số buổi tập", value=0, min=0).props("outlined").classes("flex-1")
        with ui.row().classes("w-full gap-2 mb-3"):
            t_drinks = ui.number("Số ly đồ uống", value=0, min=0).props("outlined").classes("flex-1")
            t_amount = ui.number("Giá bán (VNĐ)", value=0, min=0).props("outlined").classes("flex-1")
        t_error = ui.label().classes("text-red-500 text-sm min-h-5")

        def handle_create():
                    t_error.set_text("")
                    if not t_name.value or not t_type.value:
                        t_error.set_text("Vui lòng nhập tên và chọn loại gói")
                        return
                    user_id = app.storage.user.get("user_id", 1)
                    try:
                        with get_db() as conn:
                            cur = conn.execute(
                                """INSERT INTO package_templates
                                   (location_id, name, description, package_type, duration_days,
                                    total_sessions, total_drinks, total_amount, created_by)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    loc_id,
                                    t_name.value,
                                    t_description.value or "",
                                    t_type.value,
                                    int(t_duration.value or 0),
                                    int(t_sessions.value or 0),
                                    int(t_drinks.value or 0),
                                    float(t_amount.value or 0),
                                    user_id,
                                ),
                            )
                            template_id = cur.lastrowid
                            conn.execute(
                                """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                                   VALUES (?, ?, 'create', 'package_template', ?, ?)""",
                                (loc_id, user_id, template_id, f'{{"name":"{t_name.value}"}}'),
                            )
                    except Exception as exc:
                        t_error.set_text(f"Lỗi: {exc}")
                        return
                    create_dialog.close()
                    refresh()
                    ui.notify("Đã tạo mẫu gói", type="positive")

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary")

    # Edit dialog
    with ui.dialog() as edit_dialog, ui.card().classes("responsive-dialog-card"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("✏️ Sửa mẫu gói").classes("section-header mt-0 pr-8")
        e_id = ui.label().classes("hidden")
        e_name = ui.input("Tên mẫu *").props("outlined").classes("w-full mb-2")
        e_type = ui.select({k: v for k, v in PACKAGE_TYPES}, label="Loại gói *").props("outlined").classes("w-full mb-2")
        e_description = ui.input("Mô tả").props("outlined").classes("w-full mb-2")
        with ui.row().classes("w-full gap-2 mb-2"):
            e_duration = ui.number("Thời hạn (ngày)", value=90, min=1).props("outlined").classes("flex-1")
            e_sessions = ui.number("Số buổi tập", value=0, min=0).props("outlined").classes("flex-1")
        with ui.row().classes("w-full gap-2 mb-3"):
            e_drinks = ui.number("Số ly đồ uống", value=0, min=0).props("outlined").classes("flex-1")
            e_amount = ui.number("Giá bán (VNĐ)", value=0, min=0).props("outlined").classes("flex-1")
        e_error = ui.label().classes("text-red-500 text-sm min-h-5")

        def handle_edit():
            e_error.set_text("")
            if not e_id.text:
                return
            if not e_name.value or not e_type.value:
                e_error.set_text("Vui lòng nhập tên và chọn loại gói")
                return
            user_id = app.storage.user.get("user_id", 1)
            try:
                with get_db() as conn:
                    conn.execute(
                        """UPDATE package_templates
                           SET name=?, description=?, package_type=?, duration_days=?,
                               total_sessions=?, total_drinks=?, total_amount=?,
                               updated_at=datetime('now','localtime')
                           WHERE id=?""",
                        (
                            e_name.value,
                            e_description.value or "",
                            e_type.value,
                            int(e_duration.value or 0),
                            int(e_sessions.value or 0),
                            int(e_drinks.value or 0),
                            float(e_amount.value or 0),
                            int(e_id.text),
                        ),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'update', 'package_template', ?, ?)""",
                        (loc_id, user_id, int(e_id.text), f'{{"name":"{e_name.value}"}}'),
                    )
            except Exception as exc:
                e_error.set_text(f"Lỗi: {exc}")
                return
            edit_dialog.close()
            refresh()
            ui.notify("Đã cập nhật mẫu gói", type="positive")

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary")

    with ui.element("div").classes("page-container"):
        with ui.card().classes("custom-card p-4"):
            with ui.row().classes("items-center justify-between w-full gap-2 mb-4"):
                with ui.column().classes("gap-0"):
                    ui.label("Danh sách gói tập").classes("font-bold text-lg")
                    ui.label("Sử dụng để gán nhanh cho khách hàng").classes("text-sm text-gray-500")
                with ui.row().classes("gap-2"):
                    if role in ("OWNER", "ADMIN"):
                        ui.button(
                            "Tạo mẫu gói",
                            on_click=lambda: (reset_create_form(), create_dialog.open()),
                            icon="add",
                        ).props("unelevated").classes("btn-success")
                    ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

            template_table.move()

    def open_edit(template_id):
        with get_db() as conn:
            row = conn.execute("SELECT * FROM package_templates WHERE id = ?", (template_id,)).fetchone()
        if not row:
            ui.notify("Không tìm thấy mẫu gói", type="warning")
            return
        e_id.set_text(str(row["id"]))
        e_name.value = row["name"]
        e_type.value = row["package_type"]
        e_description.value = row["description"] if "description" in row.keys() else ""
        e_duration.value = row["duration_days"]
        e_sessions.value = row["total_sessions"]
        e_drinks.value = row["total_drinks"]
        e_amount.value = row["total_amount"]
        e_error.set_text("")
        edit_dialog.open()

    with ui.dialog() as confirm_deactivate_dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
        with ui.element("div").classes("absolute top-2 right-2"):
            ui.button(icon="close", on_click=confirm_deactivate_dialog.close).props("flat round dense").tooltip("Đóng")
        ui.label("Xác nhận vô hiệu hóa").classes("text-xl font-bold mb-2 pr-8")
        confirm_deactivate_text = ui.label().classes("text-sm text-gray-600 mb-4")
        confirm_deactivate_id = ui.number("confirm_deactivate_id").props("hidden")

        def confirm_deactivate():
            confirm_deactivate_dialog.close()
            deactivate(int(confirm_deactivate_id.value or 0))

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Hủy", on_click=confirm_deactivate_dialog.close, icon="close").props("outlined")
            ui.button("Vô hiệu hóa", on_click=confirm_deactivate, icon="block").props("unelevated color=negative")

    def open_confirm_deactivate(template_id):
        confirm_deactivate_id.value = int(template_id)
        confirm_deactivate_text.set_text("Bạn có chắc muốn vô hiệu hóa mẫu gói này? Mẫu gói sẽ không còn dùng để gán nhanh cho khách hàng.")
        confirm_deactivate_dialog.open()

    def deactivate(template_id):
        try:
            with get_db() as conn:
                conn.execute("UPDATE package_templates SET is_active = 0 WHERE id = ?", (template_id,))
                conn.execute(
                    """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                       VALUES (?, ?, 'deactivate', 'package_template', ?, ?)""",
                    (loc_id, app.storage.user.get("user_id", 1), template_id, ""),
                )
        except Exception as exc:
            ui.notify(f"Lỗi: {exc}", type="negative")
            return
        refresh()
        ui.notify("Đã vô hiệu hóa mẫu gói", type="positive")

    if role in ("OWNER", "ADMIN"):
        template_table.add_slot(
            "body-cell-action",
            """
            <q-td :props="props">
                <div class="action-buttons">
                    <q-btn flat round dense icon="edit" color="blue" @click="$parent.$emit('edit_tpl', props.value)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense icon="block" color="red" @click="$parent.$emit('deactivate_tpl', props.value)">
                        <q-tooltip>Vô hiệu hóa</q-tooltip>
                    </q-btn>
                </div>
            </q-td>
            """,
        )
        template_table.on("edit_tpl", lambda e: open_edit(int(e.args)))
        template_table.on("deactivate_tpl", lambda e: open_confirm_deactivate(int(e.args)))

    refresh()