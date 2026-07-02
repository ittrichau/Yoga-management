"""Customer management and check-in - filtered by location."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/customers", tags=["customers"])

class CustomerCreate(BaseModel):
    code: str
    full_name: str
    phone: str = ""
    email: str = ""
    notes: str = ""

class CustomerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


@router.get("")
def list_customers(search: str = "", location_id: int | None = None, user: dict = Depends(get_current_user)):
    location_id = location_id or get_current_location_id()
    if not location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """SELECT id, code, full_name, phone, email, notes, is_active, created_at, updated_at, location_id
                   FROM customers
                   WHERE is_active = 1
                     AND location_id = ?
                     AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?)
                   ORDER BY full_name""",
                (location_id, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, code, full_name, phone, email, notes, is_active, created_at, updated_at, location_id
                   FROM customers
                   WHERE is_active = 1
                     AND location_id = ?
                   ORDER BY full_name""",
                (location_id,),
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{customer_id}")
def get_customer(customer_id: int, user: dict = Depends(get_current_user)):
    current_location_id = get_current_location_id()
    if not current_location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ? AND location_id = ?",
            (customer_id, current_location_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng tại cơ sở hiện tại")
    return dict(row)


@router.post("", status_code=201)
def create_customer(data: CustomerCreate, user: dict = Depends(get_current_user)):
    location_id = get_current_location_id()
    if not location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở trước khi thêm khách hàng")

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM customers WHERE code = ? AND location_id = ?", (data.code, location_id)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Mã KH đã tồn tại tại cơ sở này")
        cur = conn.execute(
            """INSERT INTO customers (location_id, code, full_name, phone, email, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (location_id, data.code, data.full_name, data.phone, data.email, data.notes, user["id"]),
        )
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'customer', ?, ?)""",
            (location_id, user["id"], cur.lastrowid, f'{{"code":"{data.code}","name":"{data.full_name}"}}'),
        )
    return {"id": cur.lastrowid, "message": "Khách hàng đã được tạo"}


@router.put("/{customer_id}")
def update_customer(customer_id: int, data: CustomerUpdate, user: dict = Depends(require_role("MANAGER"))):
    current_location_id = get_current_location_id()
    if not current_location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ? AND location_id = ?",
            (customer_id, current_location_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng tại cơ sở hiện tại")
        updates = {}
        for field in ["full_name", "phone", "email", "notes"]:
            val = getattr(data, field)
            if val is not None:
                updates[field] = val
        if not updates:
            return {"message": "Không có thay đổi"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [customer_id, current_location_id]
        conn.execute(f"UPDATE customers SET {set_clause} WHERE id = ? AND location_id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'update', 'customer', ?, ?)""",
            (row["location_id"], user["id"], customer_id, str(updates)),
        )
    return {"message": "Khách hàng đã được cập nhật"}


@router.post("/{customer_id}/checkin")
def checkin_customer(customer_id: int, user: dict = Depends(get_current_user)):
    current_location_id = get_current_location_id()
    if not current_location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, code, full_name, location_id FROM customers WHERE id = ? AND location_id = ? AND is_active = 1",
            (customer_id, current_location_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng tại cơ sở hiện tại hoặc đã bị vô hiệu hóa")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'checkin', 'customer', ?, ?)""",
            (row["location_id"], user["id"], customer_id, f'{{"code":"{row["code"]}","name":"{row["full_name"]}","time":"{now}"}}'),
        )
    return {"message": "Check-in đã được ghi nhận", "time": now}


# ==================== NiceGUI UI ====================
@ui.page("/customers")
def customers_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return

    render()
    render_navbar()


def render():
    loc_id = get_current_location_id()

    with get_db() as conn:
        location = conn.execute(
            "SELECT name FROM locations WHERE id = ? AND is_active = 1",
            (loc_id,),
        ).fetchone()
    location_name = location["name"] if location else "Chưa chọn cơ sở"

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("👥").classes("text-2xl")
            ui.label("Quản lý khách hàng")
            ui.label(f"Cơ sở: {location_name}").classes("text-sm text-gray-500 ml-auto")

        search_input = ui.input("Tìm theo mã, tên, hoặc số điện thoại").props("outlined clearable dense").classes("flex-grow")

        customer_table = ui.table(
            columns=[
                {"name": "code", "label": "Mã KH", "field": "code"},
                {"name": "name", "label": "Họ và tên", "field": "full_name"},
                {"name": "phone", "label": "Số điện thoại", "field": "phone"},
                {"name": "action", "label": "Thao tác", "field": "action"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

        def refresh_customers():
            with get_db() as conn:
                search = search_input.value
                if search:
                    like = f"%{search}%"
                    rows = conn.execute(
                        "SELECT id, code, full_name, phone, email, notes FROM customers WHERE is_active = 1 AND location_id = ? AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?) ORDER BY full_name",
                        (loc_id, like, like, like),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, code, full_name, phone, email, notes FROM customers WHERE is_active = 1 AND location_id = ? ORDER BY full_name",
                        (loc_id,),
                    ).fetchall()

            customer_table.rows = [{**dict(r), "action": r["id"]} for r in rows]
            customer_table.update()

        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Thêm khách hàng").classes("text-xl font-bold mb-4")
            ui.label(f"Khách hàng sẽ thuộc: {location_name}").classes("text-sm text-gray-500 mb-3")
            code = ui.input("Mã KH *").props("outlined dense").classes("w-full mb-2")
            name = ui.input("Họ và tên *").props("outlined dense").classes("w-full mb-2")
            phone = ui.input("Số điện thoại").props("outlined dense").classes("w-full mb-2")
            email = ui.input("Email").props("outlined dense").classes("w-full mb-2")
            notes = ui.textarea("Ghi chú").props("outlined dense").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def handle_create():
                err.set_text("")
                if not loc_id:
                    err.set_text("Vui lòng chọn cơ sở trước khi thêm khách hàng")
                    return
                if not code.value or not name.value:
                    err.set_text("Vui lòng nhập mã KH và họ tên")
                    return

                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM customers WHERE code = ? AND location_id = ?",
                        (code.value, loc_id),
                    ).fetchone()
                    if existing:
                        err.set_text("Mã KH đã tồn tại tại cơ sở này")
                        return

                    cur = conn.execute(
                        """INSERT INTO customers (location_id, code, full_name, phone, email, notes, created_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (loc_id, code.value, name.value, phone.value, email.value, notes.value, user_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'create', 'customer', ?, ?)""",
                        (loc_id, user_id, cur.lastrowid, f'{{"code":"{code.value}","name":"{name.value}"}}'),
                    )

                code.value = ""
                name.value = ""
                phone.value = ""
                email.value = ""
                notes.value = ""
                create_dialog.close()
                refresh_customers()
                ui.notify("Đã thêm khách hàng vào cơ sở hiện tại", type="positive")

            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary w-full mt-2")

        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Sửa khách hàng").classes("text-xl font-bold mb-4")
            ui.label(f"Cơ sở: {location_name}").classes("text-sm text-gray-500 mb-3")
            edit_id = ui.number("edit_id").props("hidden")
            e_name = ui.input("Họ và tên *").props("outlined dense").classes("w-full mb-2")
            e_phone = ui.input("Số điện thoại").props("outlined dense").classes("w-full mb-2")
            e_email = ui.input("Email").props("outlined dense").classes("w-full mb-2")
            e_notes = ui.textarea("Ghi chú").props("outlined dense").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def handle_edit():
                edit_err.set_text("")
                if not loc_id:
                    edit_err.set_text("Vui lòng chọn cơ sở")
                    return
                if not e_name.value:
                    edit_err.set_text("Vui lòng nhập họ tên")
                    return

                user_id = app.storage.user.get("user_id", 1)
                customer_id = int(edit_id.value or 0)
                with get_db() as conn:
                    conn.execute(
                        "UPDATE customers SET full_name = ?, phone = ?, email = ?, notes = ?, updated_at = datetime('now','localtime') WHERE id = ? AND location_id = ?",
                        (e_name.value, e_phone.value, e_email.value, e_notes.value, customer_id, loc_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'update', 'customer', ?, ?)""",
                        (loc_id, user_id, customer_id, f'{{"name":"{e_name.value}"}}'),
                    )

                edit_dialog.close()
                refresh_customers()
                ui.notify("Đã cập nhật khách hàng", type="positive")

            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary w-full mt-2")

        def open_edit(row):
            edit_id.value = row.get("id")
            e_name.value = row.get("full_name", "")
            e_phone.value = row.get("phone", "")
            e_email.value = row.get("email", "")
            e_notes.value = row.get("notes", "")
            edit_err.set_text("")
            edit_dialog.open()

        with ui.element("div").classes("search-bar"):
            search_input.move()
            ui.button("Tìm", icon="search", on_click=refresh_customers).props("outlined")
            ui.button("Thêm khách hàng", icon="person_add", on_click=create_dialog.open).props("unelevated").classes("btn-success")

        with ui.row().classes("gap-2 mb-4"):
            ui.button("Thêm khách hàng", on_click=create_dialog.open, icon="person_add").props("unelevated").classes("btn-success")
            ui.button("Làm mới", on_click=refresh_customers, icon="refresh").props("outlined")

        search_input.on("keyup.enter", refresh_customers)

        customer_table.add_slot(
            "body-cell-action",
            """
            <q-td :props="props">
                <q-btn flat color="primary" icon="edit" @click="$parent.$emit('edit_customer', props.row)">
                    <q-tooltip>Sửa</q-tooltip>
                </q-btn>
            </q-td>
            """,
        )
        customer_table.on("edit_customer", lambda e: open_edit(e.args))

        refresh_customers()