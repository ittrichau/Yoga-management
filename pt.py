"""Personal Trainer (PT) rate and session management.

A PT session records:
- Which trainer
- Which customer
- Date
- Duration in hours
- Whether it includes a free drink (auto-deduct from package)
- PT amount + drink amount = total amount
- Optional link to a package_item if a free drink is consumed

The rate card (pt_rates) supports:
- AT_GYM (in-house) vs OUTSIDE (at customer's home)
- PER_HOUR, PER_SESSION, PER_MONTH pricing models
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/pt", tags=["pt"])


# ---------------------------------------------------------------------------
# PT Rates
# ---------------------------------------------------------------------------
class PTRateCreate(BaseModel):
    name: str
    location_type: str = "AT_GYM"
    rate_type: str = "PER_HOUR"
    price: float


class PTRateUpdate(BaseModel):
    name: str | None = None
    location_type: str | None = None
    rate_type: str | None = None
    price: float | None = None
    is_active: int | None = None


@router.get("/rates")
def list_rates(user: dict = Depends(get_current_user)):
    loc_id = get_current_location_id()
    with get_db() as conn:
        if loc_id:
            rows = conn.execute(
                "SELECT * FROM pt_rates WHERE is_active = 1 AND location_id = ? ORDER BY price",
                (loc_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pt_rates WHERE is_active = 1 ORDER BY price"
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("/rates", status_code=201)
def create_rate(data: PTRateCreate, user: dict = Depends(require_role("OWNER"))):
    loc_id = get_current_location_id()
    if not loc_id:
        raise HTTPException(status_code=400, detail="Chưa chọn cơ sở")
    if data.location_type not in ("AT_GYM", "OUTSIDE"):
        raise HTTPException(status_code=400, detail="location_type không hợp lệ")
    if data.rate_type not in ("PER_HOUR", "PER_SESSION", "PER_MONTH"):
        raise HTTPException(status_code=400, detail="rate_type không hợp lệ")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO pt_rates
               (location_id, name, location_type, rate_type, price)
               VALUES (?, ?, ?, ?, ?)""",
            (loc_id, data.name, data.location_type, data.rate_type, data.price),
        )
        rid = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'pt_rate', ?, ?)""",
            (loc_id, user["id"], rid, f'{{"name":"{data.name}","price":{data.price}}}'),
        )
    return {"id": rid, "message": "Bảng giá PT đã được tạo"}


@router.put("/rates/{rate_id}")
def update_rate(rate_id: int, data: PTRateUpdate, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pt_rates WHERE id = ?", (rate_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy bảng giá")
        updates = {f: getattr(data, f) for f in ["name", "location_type", "rate_type", "price", "is_active"] if getattr(data, f) is not None}
        if not updates:
            return {"message": "Không có thay đổi"}
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rate_id]
        conn.execute(f"UPDATE pt_rates SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'update', 'pt_rate', ?, ?)""",
            (row["location_id"], user["id"], rate_id, str(updates)),
        )
    return {"message": "Bảng giá PT đã được cập nhật"}


# ---------------------------------------------------------------------------
# PT Sessions
# ---------------------------------------------------------------------------
class PTSessionCreate(BaseModel):
    customer_id: int
    pt_rate_id: int
    duration_hours: float = 1.0
    include_nutrition: bool = False
    session_date: str | None = None
    notes: str = ""


def _compute_pt_amount(rate: dict, duration_hours: float) -> float:
    if rate["rate_type"] == "PER_HOUR":
        return float(rate["price"]) * duration_hours
    if rate["rate_type"] == "PER_SESSION":
        return float(rate["price"])
    if rate["rate_type"] == "PER_MONTH":
        return float(rate["price"])
    return 0


@router.get("/sessions")
def list_sessions(customer_id: int | None = None, user: dict = Depends(get_current_user)):
    loc_id = get_current_location_id()
    with get_db() as conn:
        where = "ps.id IS NOT NULL"
        params = []
        if loc_id:
            where += " AND ps.location_id = ?"
            params.append(loc_id)
        if customer_id:
            where += " AND ps.customer_id = ?"
            params.append(customer_id)
        rows = conn.execute(
            f"""SELECT ps.*, c.full_name as customer_name, c.code as customer_code,
                       r.name as rate_name, u.full_name as trainer_name
                FROM pt_sessions ps
                JOIN customers c ON c.id = ps.customer_id
                JOIN pt_rates r ON r.id = ps.pt_rate_id
                LEFT JOIN users u ON u.id = ps.trainer_id
                WHERE {where}
                ORDER BY ps.session_date DESC, ps.id DESC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/sessions", status_code=201)
def create_session(data: PTSessionCreate, user: dict = Depends(get_current_user)):
    loc_id = get_current_location_id()
    with get_db() as conn:
        customer = conn.execute(
            "SELECT * FROM customers WHERE id = ? AND is_active = 1", (data.customer_id,)
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")
        rate = conn.execute(
            "SELECT * FROM pt_rates WHERE id = ? AND is_active = 1", (data.pt_rate_id,)
        ).fetchone()
        if rate is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy bảng giá PT")
        pt_amount = _compute_pt_amount(rate, data.duration_hours)
        drink_amount = 0
        package_item_id = None
        drink_id = None
        if data.include_nutrition:
            # Find an active drink + an active package item with remaining servings
            drink = conn.execute(
                "SELECT id, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY id LIMIT 1",
                (loc_id,),
            ).fetchone()
            if drink is None:
                raise HTTPException(status_code=400, detail="Chưa có đồ uống nào trong hệ thống")
            drink_id = drink["id"]
            # Find an active package_item with remaining_servings > 0
            pi = conn.execute(
                """SELECT pi.id FROM package_items pi
                   JOIN packages p ON p.id = pi.package_id
                   WHERE p.customer_id = ? AND p.is_active = 1 AND pi.remaining_servings > 0
                     AND p.location_id = ?
                   ORDER BY pi.id LIMIT 1""",
                (data.customer_id, loc_id),
            ).fetchone()
            if pi:
                # Free drink from package
                package_item_id = pi["id"]
                conn.execute(
                    "UPDATE package_items SET remaining_servings = remaining_servings - 1 WHERE id = ?",
                    (pi["id"],),
                )
            else:
                # Charge for the drink
                drink_amount = float(drink["price_per_serving"])
        total_amount = pt_amount + drink_amount
        session_date = data.session_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur = conn.execute(
            """INSERT INTO pt_sessions
               (location_id, customer_id, pt_rate_id, trainer_id,
                session_date, duration_hours, include_nutrition, drink_id, package_item_id,
                pt_amount, drink_amount, total_amount, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (loc_id, data.customer_id, data.pt_rate_id, user["id"],
             session_date, data.duration_hours, 1 if data.include_nutrition else 0,
             drink_id, package_item_id, pt_amount, drink_amount, total_amount,
             data.notes, user["id"]),
        )
        sid = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'pt_session', ?, ?)""",
            (loc_id, user["id"], sid,
             f'{{"customer":"{customer["full_name"]}","pt_amount":{pt_amount},"drink_amount":{drink_amount},"total":{total_amount}}}'),
        )
    return {
        "id": sid,
        "pt_amount": pt_amount,
        "drink_amount": drink_amount,
        "total_amount": total_amount,
        "package_item_id": package_item_id,
        "message": f"Buổi PT đã được ghi nhận - Tổng {total_amount:,.0f}đ",
    }


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/pt")
def pt_page():
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
    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("💪").classes("text-2xl")
            ui.label("Quản lý PT (Personal Trainer)")

    with ui.tabs().classes("w-full") as tabs:
        tab_sessions = ui.tab("Buổi PT", icon="event")
        tab_rates = ui.tab("Bảng giá", icon="attach_money")
    with ui.tab_panels(tabs).classes("w-full"):
        with ui.tab_panel(tab_sessions):
            render_sessions_tab(loc_id)
        with ui.tab_panel(tab_rates):
            render_rates_tab(loc_id)


def render_sessions_tab(loc_id: int):
    ui.label("📝 Ghi nhận buổi PT").classes("section-header")

    with ui.element("div").classes("search-bar"):
        search_input = ui.input("Tìm khách hàng (mã, tên, SĐT)").props("outlined clearable dense").classes("flex-grow")
        ui.button("Tìm", on_click=lambda: do_search(), icon="search").props("outlined")

    customer_options = {}
    customer_select = ui.select({}, label="Chọn khách hàng").props("outlined").classes("w-full mb-4")

    with get_db() as conn:
        rates = conn.execute(
            "SELECT id, name, price, rate_type FROM pt_rates WHERE is_active = 1 AND location_id = ? ORDER BY price",
            (loc_id,),
        ).fetchall()
    rate_options = {r["id"]: f"{r['name']} ({r['price']:,.0f}đ/{r['rate_type']})" for r in rates}

    rate_select = ui.select(rate_options, label="Bảng giá PT").props("outlined").classes("w-full mb-2")
    hours_input = ui.number("Số giờ", value=1.0, step=0.5).props("outlined").classes("w-full mb-2")
    date_input = ui.input("Ngày tập (YYYY-MM-DD)", value=datetime.now(timezone.utc).strftime("%Y-%m-%d")).props("outlined").classes("w-full mb-2")
    nutrition_switch = ui.switch("Kèm đồ uống dinh dưỡng (1 ly)").classes("mb-2")
    notes_input = ui.input("Ghi chú").props("outlined").classes("w-full mb-4")

    total_label = ui.label("Tổng: 0đ").classes("text-xl font-bold text-green-600 mb-2")
    err_label = ui.label().classes("text-red-500 text-sm mb-2")

    def update_total():
        if not rate_select.value or not hours_input.value:
            total_label.set_text("Tổng: 0đ")
            return
        rate = next((r for r in rates if r["id"] == rate_select.value), None)
        if rate is None:
            return
        pt_amount = _compute_pt_amount(rate, float(hours_input.value or 0))
        total_label.set_text(f"PT: {pt_amount:,.0f}đ + Đồ uống: 0đ = Tổng: {pt_amount:,.0f}đ")

    rate_select.on("update:model-value", update_total)
    hours_input.on("update:model-value", update_total)

    def do_search():
        with get_db() as conn:
            search = (search_input.value or "").strip()
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    """SELECT id, code, full_name, phone FROM customers
                       WHERE is_active = 1 AND location_id = ?
                         AND (code LIKE ? OR full_name LIKE ? OR phone LIKE ?)
                       ORDER BY full_name LIMIT 30""",
                    (loc_id, like, like, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, code, full_name, phone FROM customers
                       WHERE is_active = 1 AND location_id = ?
                       ORDER BY full_name LIMIT 50""",
                    (loc_id,),
                ).fetchall()
        customer_options.clear()
        for r in rows:
            customer_options[r["id"]] = f"{r['code']} - {r['full_name']}"
        customer_select.set_options(customer_options)
    search_input.on("keyup.enter", do_search)

    def handle_create():
        if not customer_select.value or not rate_select.value:
            err_label.set_text("Vui lòng chọn khách hàng và bảng giá PT")
            return
        user_id = app.storage.user.get("user_id", 1)
        rate = next((r for r in rates if r["id"] == rate_select.value), None)
        if rate is None:
            err_label.set_text("Bảng giá không hợp lệ")
            return
        pt_amount = _compute_pt_amount(rate, float(hours_input.value or 0))
        drink_amount = 0
        package_item_id = None
        drink_id = None
        if nutrition_switch.value:
            with get_db() as conn:
                drink = conn.execute(
                    "SELECT id, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY id LIMIT 1",
                    (loc_id,),
                ).fetchone()
                if drink is None:
                    err_label.set_text("Chưa có đồ uống nào trong hệ thống")
                    return
                drink_id = drink["id"]
                pi = conn.execute(
                    """SELECT pi.id FROM package_items pi
                       JOIN packages p ON p.id = pi.package_id
                       WHERE p.customer_id = ? AND p.is_active = 1 AND pi.remaining_servings > 0
                         AND p.location_id = ?
                       ORDER BY pi.id LIMIT 1""",
                    (customer_select.value, loc_id),
                ).fetchone()
                if pi:
                    package_item_id = pi["id"]
                    conn.execute(
                        "UPDATE package_items SET remaining_servings = remaining_servings - 1 WHERE id = ?",
                        (pi["id"],),
                    )
                else:
                    drink_amount = float(drink["price_per_serving"])
        total_amount = pt_amount + drink_amount
        with get_db() as conn:
            cur = conn.execute(
                """INSERT INTO pt_sessions
                   (location_id, customer_id, pt_rate_id, trainer_id,
                    session_date, duration_hours, include_nutrition, drink_id, package_item_id,
                    pt_amount, drink_amount, total_amount, notes, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (loc_id, customer_select.value, rate_select.value, user_id,
                 date_input.value, float(hours_input.value or 0),
                 1 if nutrition_switch.value else 0, drink_id, package_item_id,
                 pt_amount, drink_amount, total_amount, notes_input.value, user_id),
            )
            sid = cur.lastrowid
            conn.execute(
                """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                   VALUES (?, ?, 'create', 'pt_session', ?, ?)""",
                (loc_id, user_id, sid,
                 f'{{"pt_amount":{pt_amount},"drink_amount":{drink_amount},"total":{total_amount}}}'),
            )
        msg = f"Đã ghi nhận buổi PT - Tổng {total_amount:,.0f}đ"
        if package_item_id:
            msg += " (dùng 1 ly từ gói)"
        elif drink_amount > 0:
            msg += f" (thu {drink_amount:,.0f}đ tiền ly)"
        ui.notify(msg, type="positive")
        refresh_table()
        err_label.set_text("")

    ui.button("Ghi nhận", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary w-full mt-2 mb-6")

    session_table = ui.table(
        columns=[
            {"name": "date", "label": "Ngày", "field": "date"},
            {"name": "customer", "label": "Khách hàng", "field": "customer"},
            {"name": "rate", "label": "Loại PT", "field": "rate"},
            {"name": "hours", "label": "Giờ", "field": "hours"},
            {"name": "nutrition", "label": "Uống", "field": "nutrition"},
            {"name": "total", "label": "Thành tiền", "field": "total"},
            {"name": "trainer", "label": "HLV", "field": "trainer"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh_table():
        with get_db() as conn:
            rows = conn.execute(
                """SELECT ps.*, c.full_name as customer_name, c.code as customer_code,
                           r.name as rate_name, u.full_name as trainer_name
                    FROM pt_sessions ps
                    JOIN customers c ON c.id = ps.customer_id
                    JOIN pt_rates r ON r.id = ps.pt_rate_id
                    LEFT JOIN users u ON u.id = ps.trainer_id
                    WHERE ps.location_id = ?
                    ORDER BY ps.session_date DESC, ps.id DESC LIMIT 50""",
                (loc_id,),
            ).fetchall()
        session_table.rows = [
            {
                "id": r["id"],
                "date": r["session_date"],
                "customer": f"{r['customer_code']} - {r['customer_name']}",
                "rate": r["rate_name"],
                "hours": f"{r['duration_hours']:.1f}",
                "nutrition": "🍹" if r.get("include_nutrition") else "-",
                "total": f"{r['total_amount']:,.0f}đ",
                "trainer": r.get("trainer_name") or "",
            }
            for r in rows
        ]
        session_table.update()

    ui.button("Làm mới", on_click=refresh_table, icon="refresh").props("outlined").classes("mb-2")
    do_search()
    refresh_table()


def render_rates_tab(loc_id: int):
    role = app.storage.user.get("role", "TEACHER")
    if role not in ("OWNER", "ADMIN"):
        ui.label("Chỉ OWNER trở lên mới quản lý được bảng giá PT.").classes("text-orange-600 italic")
        return

    ui.label("💰 Bảng giá PT").classes("section-header")

    rate_table = ui.table(
        columns=[
            {"name": "name", "label": "Tên", "field": "name"},
            {"name": "location_type", "label": "Loại", "field": "location_type"},
            {"name": "rate_type", "label": "Đơn vị", "field": "rate_type"},
            {"name": "price", "label": "Giá", "field": "price"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM pt_rates WHERE is_active = 1 AND location_id = ? ORDER BY price",
                (loc_id,),
            ).fetchall()
        rate_table.rows = [
            {
                "id": r["id"],
                "name": r["name"],
                "location_type": "Tại phòng" if r["location_type"] == "AT_GYM" else "Tại nhà",
                "rate_type": r["rate_type"].replace("PER_", "").lower(),
                "price": f"{r['price']:,.0f}đ",
            }
            for r in rows
        ]
        rate_table.update()

    with ui.dialog() as rate_dialog, ui.card().classes("p-6 w-96 max-w-full"):
        ui.label("💰 Thêm bảng giá PT").classes("section-header")
        rt_name = ui.input("Tên * (VD: PT Yoga 1-1 tại phòng)").props("outlined").classes("w-full mb-2")
        rt_loc = ui.select({"AT_GYM": "Tại phòng", "OUTSIDE": "Tại nhà KH"}, label="Loại", value="AT_GYM").props("outlined").classes("w-full mb-2")
        rt_type = ui.select({"PER_HOUR": "Theo giờ", "PER_SESSION": "Theo buổi", "PER_MONTH": "Theo tháng"}, label="Đơn vị", value="PER_HOUR").props("outlined").classes("w-full mb-2")
        rt_price = ui.number("Giá (VNĐ)", value=200000).props("outlined").classes("w-full mb-4")
        err = ui.label().classes("text-red-500 text-sm")

        def save():
            if not rt_name.value:
                err.set_text("Vui lòng nhập tên")
                return
            uid = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO pt_rates
                       (location_id, name, location_type, rate_type, price)
                       VALUES (?, ?, ?, ?, ?)""",
                    (loc_id, rt_name.value, rt_loc.value, rt_type.value, float(rt_price.value or 0)),
                )
                conn.execute(
                    """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                       VALUES (?, ?, 'create', 'pt_rate', ?, ?)""",
                    (loc_id, uid, conn.lastrowid, f'{{"name":"{rt_name.value}"}}'),
                )
            rate_dialog.close()
            refresh()
            ui.notify("Bảng giá đã được tạo", type="positive")

        with ui.row().classes("gap-2"):
            ui.button("Lưu", on_click=save, icon="save").props("unelevated").classes("btn-primary")
            ui.button("Đóng", on_click=rate_dialog.close, icon="close").props("outlined")

    with ui.element("div").classes("page-container"):
        with ui.row().classes("gap-2 mb-3"):
            ui.button("Thêm bảng giá", on_click=rate_dialog.open, icon="add").props("unelevated").classes("btn-success")
            ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")
    refresh()
