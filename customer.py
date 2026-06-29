"""Customer management and check-in."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar

router = APIRouter(prefix="/api/customers", tags=["customers"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@router.get("")
def list_customers(search: str = "", user: dict = Depends(get_current_user)):
    """List customers with optional search by code/name/phone."""
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """SELECT id, code, full_name, phone, email, notes, is_active, created_at, updated_at
                   FROM customers WHERE is_active = 1 AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?)
                   ORDER BY full_name""",
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, code, full_name, phone, email, notes, is_active, created_at, updated_at
                   FROM customers WHERE is_active = 1 ORDER BY full_name"""
            ).fetchall()
    return [dict(r) for r in rows]

@router.get("/{customer_id}")
def get_customer(customer_id: int, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return dict(row)

@router.post("", status_code=201)
def create_customer(data: CustomerCreate, user: dict = Depends(get_current_user)):
    """Create a new customer. STAFF can also create."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM customers WHERE code = ?", (data.code,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Customer code already exists")
        cur = conn.execute(
            """INSERT INTO customers (code, full_name, phone, email, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (data.code, data.full_name, data.phone, data.email, data.notes, user["id"]),
        )
        conn.execute(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
               VALUES (?, 'create', 'customer', ?, ?)""",
            (user["id"], cur.lastrowid, f'{{ "code": "{data.code}", "name": "{data.full_name}" }}'),
        )
    return {"id": cur.lastrowid, "message": "Customer created"}

@router.put("/{customer_id}")
def update_customer(customer_id: int, data: CustomerUpdate, user: dict = Depends(require_role("MANAGER"))):
    """Update customer. Only MANAGER+ can update."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        updates = {}
        for field in ["full_name", "phone", "email", "notes"]:
            val = getattr(data, field)
            if val is not None:
                updates[field] = val
        if not updates:
            return {"message": "No changes"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [customer_id]
        conn.execute(f"UPDATE customers SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
               VALUES (?, 'update', 'customer', ?, ?)""",
            (user["id"], customer_id, str(updates)),
        )
    return {"message": "Customer updated"}

@router.post("/{customer_id}/checkin")
def checkin_customer(customer_id: int, user: dict = Depends(get_current_user)):
    """Record a check-in for customer."""
    with get_db() as conn:
        row = conn.execute("SELECT id, code, full_name FROM customers WHERE id = ? AND is_active = 1", (customer_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Customer not found or inactive")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
               VALUES (?, 'checkin', 'customer', ?, ?)""",
            (user["id"], customer_id, f'{{ "code": "{row["code"]}", "name": "{row["full_name"]}", "time": "{now}" }}'),
        )
    return {"message": "Check-in recorded", "time": now}

# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
def render():
    """Render the customer management page (tiếng Việt)."""
    role = app.storage.user.get("role", "STAFF")

    render_navbar()
    ui.label("Quản lý khách hàng").classes("text-2xl font-bold mb-4")

    search_input = ui.input("Tìm theo mã, tên, hoặc số điện thoại").props("outlined").classes("w-full mb-4")
    customer_table = ui.table(
        columns=[
            {"name": "code", "label": "Mã KH", "field": "code"},
            {"name": "name", "label": "Họ và tên", "field": "full_name"},
            {"name": "phone", "label": "Số điện thoại", "field": "phone"},
            {"name": "action", "label": "Thao tác", "field": "action"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            search = search_input.value
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    "SELECT id, code, full_name, phone, email, notes FROM customers WHERE is_active = 1 AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?) ORDER BY full_name",
                    (like, like, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, code, full_name, phone, email, notes FROM customers WHERE is_active = 1 ORDER BY full_name"
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["action"] = d["id"]
            result.append(d)
        customer_table.rows = result
        customer_table.update()

    # ---------- Create dialog ----------
    with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
        ui.label("Thêm khách hàng").classes("text-xl font-bold mb-4")
        code = ui.input("Mã KH *").props("outlined").classes("w-full mb-2")
        name = ui.input("Họ và tên *").props("outlined").classes("w-full mb-2")
        phone = ui.input("Số điện thoại").props("outlined").classes("w-full mb-2")
        email = ui.input("Email").props("outlined").classes("w-full mb-2")
        notes = ui.textarea("Ghi chú").props("outlined").classes("w-full mb-4")
        err = ui.label().classes("text-red-500 text-sm")

        def handle_create():
            if not code.value or not name.value:
                err.set_text("Vui lòng nhập mã KH và họ tên")
                return
            user_id = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                existing = conn.execute(
                    "SELECT id FROM customers WHERE code = ?", (code.value,)
                ).fetchone()
                if existing:
                    err.set_text("Mã KH đã tồn tại")
                    return
                conn.execute(
                    """INSERT INTO customers (code, full_name, phone, email, notes, created_by)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (code.value, name.value, phone.value, email.value, notes.value, user_id),
                )
            create_dialog.close()
            refresh()
            ui.notify("Đã thêm khách hàng", type="positive")

        ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    # ---------- Edit dialog ----------
    with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96"):
        ui.label("Sửa khách hàng").classes("text-xl font-bold mb-4")
        edit_id = ui.number("edit_id").props("hidden")
        e_name = ui.input("Họ và tên *").props("outlined").classes("w-full mb-2")
        e_phone = ui.input("Số điện thoại").props("outlined").classes("w-full mb-2")
        e_email = ui.input("Email").props("outlined").classes("w-full mb-2")
        e_notes = ui.textarea("Ghi chú").props("outlined").classes("w-full mb-4")
        edit_err = ui.label().classes("text-red-500 text-sm")

        def handle_edit():
            if not e_name.value:
                edit_err.set_text("Vui lòng nhập họ tên")
                return
            user_id = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                conn.execute(
                    "UPDATE customers SET full_name = ?, phone = ?, email = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
                    (e_name.value, e_phone.value, e_email.value, e_notes.value, int(edit_id.value or 0)),
                )
                conn.execute(
                    """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
                       VALUES (?, 'update', 'customer', ?, ?)""",
                    (user_id, int(edit_id.value or 0), f'{{"name": "{e_name.value}"}}'),
                )
            edit_dialog.close()
            refresh()
            ui.notify("Đã cập nhật khách hàng", type="positive")

        def open_edit(customer: dict):
            edit_id.value = customer["id"]
            e_name.value = customer.get("full_name", "")
            e_phone.value = customer.get("phone", "")
            e_email.value = customer.get("email", "")
            e_notes.value = customer.get("notes", "")
            edit_err.set_text("")
            edit_dialog.open()

        ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    # ---------- Buttons ----------
    with ui.row().classes("gap-2 mb-4"):
        ui.button("Thêm khách hàng", on_click=create_dialog.open, icon="person_add").props("unelevated").classes("bg-green-600 text-white")
        ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

    search_input.on("keyup.enter", refresh)

    # Render edit button in the action column
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

    refresh()