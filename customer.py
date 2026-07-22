"""Customer management and check-in - filtered by location."""
import re
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/customers", tags=["customers"])

class CustomerCreate(BaseModel):
    code: str | None = None  # Auto-generated when omitted
    full_name: str
    phone: str = ""
    birth_date: str | None = None
    notes: str = ""

class CustomerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    birth_date: str | None = None
    notes: str | None = None


def _generate_next_customer_code(conn, location_id: int) -> str:
    """Generate the next unique customer code for the given location.

    Format: HV000001, HV000002, ... (zero-padded 6 digits).
    The numeric suffix is taken from the highest existing code that matches
    the same format; if none exist, starts at 1. Soft-deleted customers are
    ignored so a new customer is never assigned a code in use.
    """
    rows = conn.execute(
        "SELECT code FROM customers WHERE location_id = ? AND is_active = 1",
        (location_id,),
    ).fetchall()
    max_n = 0
    for r in rows:
        m = re.match(r"^HV(\d+)$", (r["code"] or "").strip().upper())
        if m:
            try:
                max_n = max(max_n, int(m.group(1)))
            except ValueError:
                pass
    return f"HV{max_n + 1:06d}"


@router.get("/next-code")
def get_next_code(user: dict = Depends(get_current_user)):
    """Preview the next auto-generated customer code for the current location."""
    location_id = get_current_location_id()
    if not location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")
    with get_db() as conn:
        return {"code": _generate_next_customer_code(conn, location_id)}


@router.get("")
def list_customers(search: str = "", location_id: int | None = None, user: dict = Depends(get_current_user)):
    location_id = location_id or get_current_location_id()
    if not location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """SELECT id, code, full_name, phone, birth_date, notes, is_active, created_at, updated_at, location_id
                   FROM customers
                   WHERE is_active = 1
                     AND location_id = ?
                     AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?)
                   ORDER BY full_name""",
                (location_id, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, code, full_name, phone, birth_date, notes, is_active, created_at, updated_at, location_id
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
        # If client didn't supply a code, auto-generate one. If a code was
        # supplied, validate it doesn't conflict with another active customer
        # at the same location.
        code = (data.code or "").strip() or _generate_next_customer_code(conn, location_id)
        existing = conn.execute(
            "SELECT id FROM customers WHERE code = ? AND location_id = ?",
            (code, location_id),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Mã KH đã tồn tại tại cơ sở này")
        cur = conn.execute(
            """INSERT INTO customers (location_id, code, full_name, phone, birth_date, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (location_id, code, data.full_name, data.phone, data.birth_date, data.notes, user["id"]),
        )
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'customer', ?, ?)""",
            (location_id, user["id"], cur.lastrowid, f'{{"code":"{code}","name":"{data.full_name}"}}'),
        )
    return {"id": cur.lastrowid, "code": code, "message": "Khách hàng đã được tạo"}


@router.delete("/{customer_id}")
def delete_customer(customer_id: int, user: dict = Depends(require_role("OWNER"))):
    """Soft-delete a customer at the current location."""
    current_location_id = get_current_location_id()
    if not current_location_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        row = conn.execute(
            """SELECT id, code, full_name, location_id
               FROM customers
               WHERE id = ? AND location_id = ? AND is_active = 1""",
            (customer_id, current_location_id),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy khách hàng tại cơ sở hiện tại hoặc khách hàng đã bị xóa",
            )

        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE customers SET is_active = 0, updated_at = ? WHERE id = ? AND location_id = ?",
            (updated_at, customer_id, current_location_id),
        )
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'deactivate', 'customer', ?, ?)""",
            (
                current_location_id,
                user["id"],
                customer_id,
                f'{{"code":"{row["code"]}","name":"{row["full_name"]}"}}',
            ),
        )

    return {"message": "Khách hàng đã được xóa"}


@router.put("/{customer_id}")
def update_customer(customer_id: int, data: CustomerUpdate, user: dict = Depends(require_role("OWNER"))):
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
        for field in ["full_name", "phone", "birth_date", "notes"]:
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


# ==================== Birthday alerts API ====================
@router.get("/upcoming-birthdays")
def upcoming_birthdays(user: dict = Depends(get_current_user)):
    """Return customers with birthdays in the next 3 days, for the current location."""
    loc_id = get_current_location_id()
    if not loc_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn cơ sở")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, code, full_name, phone, birth_date
               FROM customers
               WHERE is_active = 1 AND location_id = ? AND birth_date IS NOT NULL AND birth_date != ''
               ORDER BY full_name""",
            (loc_id,),
        ).fetchall()

    today = datetime.now(timezone.utc).date()
    upcoming = []
    for r in rows:
        bd_str = r["birth_date"]
        if not bd_str:
            continue
        try:
            bd = datetime.strptime(bd_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        # Calculate next birthday (this year or next)
        try:
            next_bd = bd.replace(year=today.year)
        except ValueError:
            # Feb 29 on non-leap year → use Feb 28
            next_bd = bd.replace(year=today.year, day=28)
        if next_bd < today:
            try:
                next_bd = bd.replace(year=today.year + 1)
            except ValueError:
                next_bd = bd.replace(year=today.year + 1, day=28)
        days_until = (next_bd - today).days
        if 0 <= days_until <= 3:
            upcoming.append({
                "id": r["id"],
                "code": r["code"],
                "full_name": r["full_name"],
                "phone": r["phone"],
                "birth_date": bd.strftime("%d/%m/%Y"),
                "days_until": days_until,
                "age": today.year - bd.year if next_bd.year == today.year else today.year - bd.year + 1,
            })

    # Sort by days_until (closest first)
    upcoming.sort(key=lambda x: x["days_until"])
    return upcoming


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

        search_input = ui.input("Tìm theo mã, tên hoặc số điện thoại").props(
            "outlined clearable dense"
        ).classes("customer-search-input")
        with ui.element("div").classes("customer-search-toolbar"):
            search_input.move()
            ui.button(
                "Tìm",
                icon="search",
                on_click=lambda: refresh_customers(),
            ).props("unelevated").classes("btn-primary customer-search-button")
            ui.button(
                "Thêm khách hàng",
                icon="person_add",
                on_click=lambda: create_dialog.open(),
            ).props("unelevated").classes("btn-success customer-add-button")

        customer_list = ui.element("div").classes("customer-card-grid")

        def _fmt_birth_date(bd):
            """Convert YYYY-MM-DD to DD/MM/YYYY for display."""
            if not bd:
                return ""
            try:
                return datetime.strptime(bd, "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                return bd

        def _create_birth_date_picker(label: str):
            """Create a Vietnamese date picker displaying DD/MM/YYYY but storing YYYY-MM-DD."""
            with ui.input(label).props("outlined dense readonly").classes(
                "w-full mb-2 cursor-pointer"
            ) as date_input:
                with ui.menu().props("no-parent-event") as menu:
                    date_picker = ui.date(mask="YYYY-MM-DD").props("minimal")
                    with ui.row().classes("justify-end w-full p-2"):
                        ui.button(
                            "Xóa",
                            on_click=lambda: (
                                setattr(date_input, "value", ""),
                                setattr(date_picker, "value", None),
                                menu.close(),
                            ),
                        ).props("flat")
                        ui.button("Chọn", on_click=menu.close).props("flat")

                with date_input.add_slot("append"):
                    ui.icon("event").classes("cursor-pointer").on(
                        "click", menu.open
                    )

            date_input.on("click", menu.open)

            def sync_date(e):
                if e.value:
                    date_input.value = _fmt_birth_date(e.value)

            date_picker.on_value_change(sync_date)
            date_input.date_picker = date_picker
            return date_input

        def _set_birth_date_picker_value(date_input, raw_value: str | None):
            """Set date picker value from either DD/MM/YYYY or YYYY-MM-DD."""
            raw_value = (raw_value or "").strip()
            if not raw_value:
                date_input.value = ""
                date_input.date_picker.value = None
                return
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    db_value = datetime.strptime(raw_value, fmt).strftime("%Y-%m-%d")
                    date_input.value = _fmt_birth_date(db_value)
                    date_input.date_picker.value = db_value
                    return
                except ValueError:
                    pass
            date_input.value = raw_value
            date_input.date_picker.value = None

        def refresh_customers():
            with get_db() as conn:
                search = (search_input.value or "").strip()
                if search:
                    like = f"%{search}%"
                    rows = conn.execute(
                        "SELECT id, code, full_name, phone, birth_date, notes FROM customers WHERE is_active = 1 AND location_id = ? AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?) ORDER BY full_name",
                        (loc_id, like, like, like),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, code, full_name, phone, birth_date, notes FROM customers WHERE is_active = 1 AND location_id = ? ORDER BY full_name",
                        (loc_id,),
                    ).fetchall()

            customers = [dict(row) for row in rows]
            customer_list.clear()
            with customer_list:
                if not customers:
                    with ui.column().classes("customer-empty-state"):
                        ui.icon("person_search").classes("customer-empty-icon")
                        ui.label(
                            "Không tìm thấy khách hàng phù hợp"
                            if search
                            else "Chưa có khách hàng tại cơ sở này"
                        ).classes("customer-empty-title")
                        ui.label(
                            "Hãy thử từ khóa khác"
                            if search
                            else "Nhấn “Thêm khách hàng” để tạo khách hàng đầu tiên"
                        ).classes("customer-empty-description")
                    return

                can_manage = app.storage.user.get("role") in {"OWNER", "ADMIN"}
                for index, customer in enumerate(customers, start=1):
                    with ui.card().classes("customer-card"):
                        with ui.row().classes("customer-card-heading"):
                            with ui.element("div").classes("customer-order"):
                                ui.label(str(index))
                            with ui.column().classes("customer-name-wrap"):
                                ui.label(customer["full_name"]).classes("customer-name")
                                ui.label("Khách hàng").classes("customer-type-label")

                        with ui.column().classes("customer-info-list"):
                            with ui.row().classes("customer-info-row"):
                                ui.icon("phone").classes("customer-info-icon")
                                ui.label(customer.get("phone") or "Chưa có số điện thoại")
                            if customer.get("birth_date"):
                                with ui.row().classes("customer-info-row"):
                                    ui.icon("cake").classes("customer-info-icon")
                                    ui.label(_fmt_birth_date(customer["birth_date"]))
                            if (customer.get("notes") or "").strip():
                                with ui.row().classes("customer-info-row customer-notes-row"):
                                    ui.icon("notes").classes("customer-info-icon")
                                    ui.label(customer["notes"]).classes("customer-notes")

                        if can_manage:
                            with ui.row().classes("customer-card-actions"):
                                ui.button(
                                    "Sửa",
                                    icon="edit",
                                    on_click=lambda row=customer: open_edit(row),
                                ).props("flat no-caps").classes("customer-edit-button")
                                ui.button(
                                    "Xóa",
                                    icon="delete_outline",
                                    on_click=lambda row=customer: open_delete(row),
                                ).props("flat no-caps").classes("customer-delete-button")

        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Thêm khách hàng").classes("text-xl font-bold mb-4 pr-8")
            ui.label(f"Khách hàng sẽ thuộc: {location_name}").classes("text-sm text-gray-500 mb-3")
            name = ui.input("Họ và tên *").props("outlined dense").classes("w-full mb-2")
            phone = ui.input("Số điện thoại").props("outlined dense").classes("w-full mb-2")
            birth_date = _create_birth_date_picker("Ngày sinh")
            notes = ui.textarea("Ghi chú").props("outlined dense").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def _parse_birth_date(raw: str) -> str | None:
                """Parse DD/MM/YYYY and return YYYY-MM-DD or None."""
                raw = (raw or "").strip()
                if not raw:
                    return None
                try:
                    dt = datetime.strptime(raw, "%d/%m/%Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    return None

            def handle_create():
                err.set_text("")
                if not loc_id:
                    err.set_text("Vui lòng chọn cơ sở trước khi thêm khách hàng")
                    return
                if not name.value:
                    err.set_text("Vui lòng nhập họ tên")
                    return

                parsed_bd = _parse_birth_date(birth_date.value)

                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    # Always auto-generate a fresh, unique code on save.
                    cur_max = conn.execute(
                        "SELECT code FROM customers WHERE location_id = ? AND is_active = 1",
                        (loc_id,),
                    ).fetchall()
                    import re as _re
                    max_n = 0
                    for r in cur_max:
                        m = _re.match(r"^HV(\d+)$", (r["code"] or "").strip().upper())
                        if m:
                            try:
                                max_n = max(max_n, int(m.group(1)))
                            except ValueError:
                                pass
                    new_code = f"HV{max_n + 1:06d}"
                    while conn.execute(
                        "SELECT id FROM customers WHERE code = ? AND location_id = ?",
                        (new_code, loc_id),
                    ).fetchone():
                        max_n += 1
                        new_code = f"HV{max_n + 1:06d}"

                    cur = conn.execute(
                        """INSERT INTO customers (location_id, code, full_name, phone, birth_date, notes, created_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (loc_id, new_code, name.value, phone.value, parsed_bd, notes.value, user_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'create', 'customer', ?, ?)""",
                        (loc_id, user_id, cur.lastrowid, f'{{"code":"{new_code}","name":"{name.value}"}}'),
                    )

                name.value = ""
                phone.value = ""
                _set_birth_date_picker_value(birth_date, "")
                notes.value = ""
                create_dialog.close()
                refresh_customers()
                ui.notify(f"Đã thêm khách hàng với mã {new_code}", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary")


        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Sửa khách hàng").classes("text-xl font-bold mb-4 pr-8")
            ui.label(f"Cơ sở: {location_name}").classes("text-sm text-gray-500 mb-3")
            edit_id = ui.number("edit_id").props("hidden")
            e_name = ui.input("Họ và tên *").props("outlined dense").classes("w-full mb-2")
            e_phone = ui.input("Số điện thoại").props("outlined dense").classes("w-full mb-2")
            e_birth_date = _create_birth_date_picker("Ngày sinh")
            e_notes = ui.textarea("Ghi chú").props("outlined dense").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def _parse_birth_date_edit(raw: str) -> str | None:
                """Parse DD/MM/YYYY and return YYYY-MM-DD or None."""
                raw = (raw or "").strip()
                if not raw:
                    return None
                try:
                    dt = datetime.strptime(raw, "%d/%m/%Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    return None

            def handle_edit():
                edit_err.set_text("")
                if not loc_id:
                    edit_err.set_text("Vui lòng chọn cơ sở")
                    return
                if not e_name.value:
                    edit_err.set_text("Vui lòng nhập họ tên")
                    return

                parsed_bd = _parse_birth_date_edit(e_birth_date.value)
                user_id = app.storage.user.get("user_id", 1)
                customer_id = int(edit_id.value or 0)
                with get_db() as conn:
                    conn.execute(
                        "UPDATE customers SET full_name = ?, phone = ?, birth_date = ?, notes = ?, updated_at = datetime('now','localtime') WHERE id = ? AND location_id = ?",
                        (e_name.value, e_phone.value, parsed_bd, e_notes.value, customer_id, loc_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'update', 'customer', ?, ?)""",
                        (loc_id, user_id, customer_id, f'{{"name":"{e_name.value}"}}'),
                    )

                edit_dialog.close()
                refresh_customers()
                ui.notify("Đã cập nhật khách hàng", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary")

        def open_edit(row):
            edit_id.value = row.get("id")
            e_name.value = row.get("full_name", "")
            e_phone.value = row.get("phone", "")
            _set_birth_date_picker_value(e_birth_date, row.get("birth_date", ""))
            e_notes.value = row.get("notes", "")
            edit_err.set_text("")
            edit_dialog.open()

        selected_customer = {"id": None, "name": ""}

        with ui.dialog() as delete_dialog, ui.card().classes(
            "responsive-dialog-card customer-delete-dialog"
        ):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=delete_dialog.close).props(
                    "flat round dense"
                ).tooltip("Đóng")
            ui.icon("warning_amber").classes("customer-delete-dialog-icon")
            ui.label("Xóa khách hàng?").classes("text-xl font-bold pr-8")
            delete_message = ui.label().classes("text-gray-600")
            ui.label(
                "Khách hàng sẽ không còn xuất hiện trong danh sách, nhưng lịch sử liên quan vẫn được giữ lại."
            ).classes("text-sm text-gray-500")
            delete_error = ui.label().classes("text-red-500 text-sm")

            def handle_delete():
                delete_error.set_text("")
                if app.storage.user.get("role") not in {"OWNER", "ADMIN"}:
                    delete_error.set_text("Bạn không có quyền xóa khách hàng")
                    return

                customer_id = selected_customer["id"]
                user_id = app.storage.user.get("user_id")
                with get_db() as conn:
                    row = conn.execute(
                        """SELECT id, code, full_name FROM customers
                           WHERE id = ? AND location_id = ? AND is_active = 1""",
                        (customer_id, loc_id),
                    ).fetchone()
                    if row is None:
                        delete_error.set_text(
                            "Không tìm thấy khách hàng hoặc khách hàng đã được xóa"
                        )
                        return

                    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        "UPDATE customers SET is_active = 0, updated_at = ? WHERE id = ? AND location_id = ?",
                        (updated_at, customer_id, loc_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'deactivate', 'customer', ?, ?)""",
                        (
                            loc_id,
                            user_id,
                            customer_id,
                            f'{{"code":"{row["code"]}","name":"{row["full_name"]}"}}',
                        ),
                    )

                delete_dialog.close()
                refresh_customers()
                ui.notify("Đã xóa khách hàng", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-3"):
                ui.button("Hủy", on_click=delete_dialog.close).props("outlined")
                ui.button(
                    "Xóa khách hàng",
                    icon="delete_outline",
                    on_click=handle_delete,
                ).props("unelevated").classes("btn-danger")

        def open_delete(row):
            selected_customer["id"] = row.get("id")
            selected_customer["name"] = row.get("full_name", "")
            delete_message.set_text(
                f'Bạn có chắc muốn xóa khách hàng “{selected_customer["name"]}”?'
            )
            delete_error.set_text("")
            delete_dialog.open()

        search_input.on("keyup.enter", refresh_customers)
        search_input.on("clear", refresh_customers)

        refresh_customers()
