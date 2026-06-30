"""Sales/transaction creation - filtered by location."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class TransactionCreate(BaseModel):
    customer_id: int
    drink_id: int
    servings: float = 1
    amount: float = 0
    notes: str = ""
    package_item_id: int | None = None


class TransactionFilter(BaseModel):
    customer_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@router.get("")
def list_transactions(
    customer_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location_id: int | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List transactions with optional filters and location."""
    with get_db() as conn:
        where = []
        params = []
        if customer_id:
            where.append("t.customer_id = ?")
            params.append(customer_id)
        if date_from:
            where.append("t.created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("t.created_at <= ?")
            params.append(date_to + " 23:59:59")
        if location_id:
            where.append("t.location_id = ?")
            params.append(location_id)
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT t.*, c.code as customer_code, c.full_name as customer_name,
                       d.name as drink_name, u.full_name as user_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN drinks d ON d.id = t.drink_id
                JOIN users u ON u.id = t.created_by
                {where_clause}
                ORDER BY t.created_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/today")
def get_today_transactions(location_id: int | None = None, user: dict = Depends(get_current_user)):
    """Get today's transactions."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "%"
    with get_db() as conn:
        if location_id:
            rows = conn.execute(
                """SELECT t.*, c.code as customer_code, c.full_name as customer_name,
                           d.name as drink_name, u.full_name as user_name
                    FROM transactions t
                    JOIN customers c ON c.id = t.customer_id
                    JOIN drinks d ON d.id = t.drink_id
                    JOIN users u ON u.id = t.created_by
                    WHERE t.created_at LIKE ? AND t.location_id = ?
                    ORDER BY t.created_at DESC""",
                (today, location_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT t.*, c.code as customer_code, c.full_name as customer_name,
                           d.name as drink_name, u.full_name as user_name
                    FROM transactions t
                    JOIN customers c ON c.id = t.customer_id
                    JOIN drinks d ON d.id = t.drink_id
                    JOIN users u ON u.id = t.created_by
                    WHERE t.created_at LIKE ?
                    ORDER BY t.created_at DESC""",
                (today,),
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_transaction(data: TransactionCreate, user: dict = Depends(get_current_user)):
    """Create a new transaction."""
    with get_db() as conn:
        # Validate customer
        customer = conn.execute(
            "SELECT id, code, full_name, location_id FROM customers WHERE id = ? AND is_active = 1",
            (data.customer_id,),
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng hoặc đã bị vô hiệu hóa")

        loc_id = customer["location_id"]

        # Validate drink
        drink = conn.execute(
            "SELECT id, name, price_per_serving FROM drinks WHERE id = ? AND is_active = 1 AND location_id = ?",
            (data.drink_id, loc_id),
        ).fetchone()
        if drink is None:
            raise HTTPException(status_code=404, detail="Đồ uống không tồn tại hoặc không thuộc cơ sở này")

        # Calculate amount if using direct payment
        amount = data.amount
        package_item_id = data.package_item_id

        # If using package, validate and deduct
        if package_item_id:
            package_item = conn.execute(
                """SELECT pi.*, p.id as package_id, p.customer_id, p.location_id
                   FROM package_items pi
                   JOIN packages p ON p.id = pi.package_id
                   WHERE pi.id = ? AND p.is_active = 1""",
                (package_item_id,),
            ).fetchone()
            if package_item is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy gói hoặc gói đã bị vô hiệu hóa")
            if package_item["customer_id"] != data.customer_id:
                raise HTTPException(status_code=400, detail="Gói không thuộc khách hàng này")
            if package_item["remaining_servings"] < data.servings:
                raise HTTPException(status_code=400,
                                    detail=f"Không đủ ly trong gói. Còn lại: {package_item['remaining_servings']:.1f}")
            amount = 0
        else:
            if amount == 0:
                amount = drink["price_per_serving"] * data.servings
            _deduct_ingredients(conn, data.drink_id, data.servings, loc_id)

        # Insert transaction
        cur = conn.execute(
            """INSERT INTO transactions (location_id, customer_id, drink_id, package_item_id, servings, amount, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (loc_id, data.customer_id, data.drink_id, package_item_id, data.servings, amount, data.notes, user["id"]),
        )
        tx_id = cur.lastrowid

        # Deduct from package if using
        if package_item_id:
            conn.execute(
                "UPDATE package_items SET remaining_servings = remaining_servings - ? WHERE id = ?",
                (data.servings, package_item_id),
            )

        # Audit log
        payment_type = "package" if package_item_id else "cash"
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'transaction', ?, ?)""",
            (loc_id, user["id"], tx_id,
             f'{{"customer": "{customer["full_name"]}", "drink": "{drink["name"]}", "servings": {data.servings}, "amount": {amount}, "type": "{payment_type}"}}'),
        )

    return {"id": tx_id, "message": "Giao dịch đã được tạo", "amount": amount, "type": payment_type}


def _deduct_ingredients(conn, drink_id: int, servings: float, loc_id: int):
    """Deduct ingredient stock based on drink recipe."""
    recipe = conn.execute(
        """SELECT dr.*, i.name as ingredient_name, i.current_stock, i.unit
           FROM drink_recipes dr
           JOIN ingredients i ON i.id = dr.ingredient_id
           WHERE dr.drink_id = ? AND i.location_id = ?""",
        (drink_id, loc_id),
    ).fetchall()
    for rec in recipe:
        needed = rec["quantity_per_serving"] * servings
        new_stock = rec["current_stock"] - needed
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE ingredients SET current_stock = ?, updated_at = ? WHERE id = ?",
            (new_stock, now, rec["ingredient_id"]),
        )
        conn.execute(
            """INSERT INTO inventory_adjustments (location_id, ingredient_id, adjustment_type, quantity, reason)
               VALUES (?, ?, 'remove', ?, ?)""",
            (loc_id, rec["ingredient_id"], needed, f"Auto-deduct from transaction: {drink_id}"),
        )
        if new_stock < 0:
            raise HTTPException(status_code=400,
                                detail=f"Không đủ {rec['ingredient_name']} trong kho. Cần {needed:.1f} {rec['unit']}, hiện có {rec['current_stock']:.1f}")


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/sales")
def sales_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return

    render()
    render_navbar()


def render():
    """Render the sales / transaction creation page."""
    role = app.storage.user.get("role", "STAFF")
    loc_id = get_current_location_id()

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.icon("point_of_sale").classes("text-2xl")
            ui.label("Bán hàng")

        # Step 1: Search and select customer
        with ui.element("div").classes("custom-card p-4 mb-3"):
            ui.label("👤 Chọn khách hàng").classes("section-header")
            with ui.element("div").classes("search-bar mt-2"):
                search_input = ui.input("Tìm khách hàng (tên hoặc mã)").props("outlined clearable dense").classes("flex-grow")
                ui.button("Tìm", on_click=lambda: search_customers(), icon="search").props("outlined")

    customer_options = {}
    with ui.element("div").classes("page-container"):
        customer_select = ui.select({}, label="Chọn khách hàng").props("outlined dense").classes("w-full mb-4")

    def search_customers():
        with get_db() as conn:
            search = search_input.value
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    "SELECT id, code, full_name FROM customers WHERE is_active = 1 AND location_id = ? AND (code LIKE ? OR full_name LIKE ?) ORDER BY full_name LIMIT 20",
                    (loc_id, like, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, code, full_name FROM customers WHERE is_active = 1 AND location_id = ? ORDER BY full_name LIMIT 50",
                    (loc_id,),
                ).fetchall()
        customer_options.clear()
        for r in rows:
            customer_options[r["id"]] = f"{r['code']} - {r['full_name']}"
        customer_select.set_options(customer_options)
        if customer_options:
            customer_select.set_value(list(customer_options.keys())[0])
        load_packages()

    # Customer packages info
    pkg_info = ui.label().classes("text-sm font-medium text-primary mt-1")
    package_select = ui.select({}, label="Dùng gói (để trống nếu bán lẻ)").props("outlined dense").classes("w-full mb-2")
    package_item_options = {}

    def load_packages():
        customer_id = customer_select.value
        if not customer_id:
            package_select.set_options({})
            pkg_info.set_text("")
            return
        with get_db() as conn:
            packages = conn.execute(
                """SELECT p.*, pi.id as pi_id, pi.drink_id, pi.total_servings, pi.remaining_servings,
                          d.name as drink_name
                   FROM packages p
                   JOIN package_items pi ON pi.package_id = p.id AND pi.remaining_servings > 0
                   JOIN drinks d ON d.id = pi.drink_id
                   WHERE p.customer_id = ? AND p.is_active = 1 AND p.location_id = ?
                   ORDER BY p.created_at DESC""",
                (customer_id, loc_id),
            ).fetchall()
        package_item_options.clear()
        options = {"": "--- Bán lẻ (thu tiền) ---"}
        for pkg in packages:
            label = f"{pkg['name'] or 'Gói'} - {pkg['drink_name']}: {pkg['remaining_servings']:.0f}/{pkg['total_servings']:.0f} ly"
            options[pkg["pi_id"]] = label
            package_item_options[pkg["pi_id"]] = dict(pkg)
        package_select.set_options(options)
        package_select.set_value("")
        if packages:
            pkg_info.set_text(f"Khách hàng có {len(packages)} gói đang hoạt động")

    customer_select.on("update:model-value", load_packages)

    # Step 2: Select drink
    with get_db() as conn:
        all_drinks = conn.execute(
            "SELECT id, name, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()
    drink_options = {r["id"]: f"{r['name']} ({r['price_per_serving']:,.0f}đ/ly)" for r in all_drinks}
    drink_select = ui.select(drink_options, label="Đồ uống *").props("outlined dense").classes("w-full mb-2")
    if drink_options:
        drink_select.set_value(list(drink_options.keys())[0])

    servings = ui.number("Số ly", value=1, min=0.1, step=0.5).props("outlined dense").classes("w-full mb-2")
    amount = ui.number("Số tiền (VNĐ)", value=0).props("outlined dense").classes("w-full mb-2")
    notes = ui.input("Ghi chú").props("outlined dense").classes("w-full mb-4")

    err = ui.label().classes("text-red-500 text-sm mb-2")
    success = ui.label().classes("text-green-600 text-sm mb-2")

    def on_package_change():
        pkg_id = package_select.value
        if pkg_id and pkg_id in package_item_options:
            pkg = package_item_options[pkg_id]
            drink_select.set_value(pkg["drink_id"])
            servings.set_value(1)
            amount.set_value(0)
            notes.set_value(f"Từ gói: {pkg['name'] or 'Gói'}")
        else:
            amount.set_value(0)
            notes.set_value("")

    package_select.on("update:model-value", on_package_change)

    def on_drink_change():
        if not package_select.value:
            drink_id = drink_select.value
            if drink_id and drink_id in drink_options:
                qty = servings.value or 1
                with get_db() as conn:
                    drink = conn.execute("SELECT price_per_serving FROM drinks WHERE id = ?", (drink_id,)).fetchone()
                if drink:
                    amount.set_value(drink["price_per_serving"] * qty)

    drink_select.on("update:model-value", on_drink_change)
    servings.on("update:model-value", on_drink_change)

    def do_sale():
        err.set_text("")
        success.set_text("")
        customer_id = customer_select.value
        if not customer_id:
            err.set_text("Vui lòng chọn khách hàng")
            return
        drink_id = drink_select.value
        if not drink_id:
            err.set_text("Vui lòng chọn đồ uống")
            return
        qty = servings.value or 1
        amt = amount.value or 0
        pkg_item_id = package_select.value or None

        if not pkg_item_id and amt == 0:
            err.set_text("Vui lòng nhập số tiền hoặc chọn gói trả trước")
            return

        user_id = app.storage.user.get("user_id", 1)

        try:
            with get_db() as conn:
                customer = conn.execute(
                    "SELECT id, full_name FROM customers WHERE id = ? AND is_active = 1 AND location_id = ?",
                    (customer_id, loc_id),
                ).fetchone()
                if customer is None:
                    err.set_text("Khách hàng không tồn tại hoặc đã bị vô hiệu hóa")
                    return

                drink = conn.execute(
                    "SELECT id, name, price_per_serving FROM drinks WHERE id = ? AND is_active = 1 AND location_id = ?",
                    (drink_id, loc_id),
                ).fetchone()
                if drink is None:
                    err.set_text("Đồ uống không tồn tại hoặc đã bị vô hiệu hóa")
                    return

                if pkg_item_id:
                    package_item = conn.execute(
                        """SELECT pi.*, p.name as pkg_name, p.id as pkg_id, p.location_id
                           FROM package_items pi
                           JOIN packages p ON p.id = pi.package_id
                           WHERE pi.id = ? AND p.is_active = 1 AND p.customer_id = ? AND p.location_id = ?""",
                        (pkg_item_id, customer_id, loc_id),
                    ).fetchone()
                    if package_item is None:
                        err.set_text("Gói không hợp lệ hoặc không thuộc khách hàng này")
                        return
                    if package_item["remaining_servings"] < qty:
                        err.set_text(f"Không đủ ly trong gói. Còn {package_item['remaining_servings']:.0f} ly")
                        return
                    amt = 0
                else:
                    if amt == 0:
                        amt = drink["price_per_serving"] * qty
                    _deduct_ingredients(conn, drink_id, qty, loc_id)

                cur = conn.execute(
                    """INSERT INTO transactions (location_id, customer_id, drink_id, package_item_id, servings, amount, notes, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (loc_id, customer_id, drink_id, pkg_item_id, qty, amt, notes.value, user_id),
                )
                tx_id = cur.lastrowid

                if pkg_item_id:
                    conn.execute(
                        "UPDATE package_items SET remaining_servings = remaining_servings - ? WHERE id = ?",
                        (qty, pkg_item_id),
                    )

                payment_type = "gói" if pkg_item_id else "tiền mặt"
                conn.execute(
                    """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                       VALUES (?, ?, 'create', 'transaction', ?, ?)""",
                    (loc_id, user_id, tx_id,
                     f'{{"customer": "{customer["full_name"]}", "drink": "{drink["name"]}", "servings": {qty}, "amount": {amt}, "type": "{payment_type}"}}'),
                )

            success.set_text(f"✅ Đã bán {qty} ly {drink['name']} cho {customer['full_name']}. {'(Gói)' if pkg_item_id else f'Thu {amt:,.0f}đ'}")
            ui.notify("Bán hàng thành công!", type="positive")
            load_packages()
            refresh_today_table()

        except HTTPException as ex:
            err.set_text(f"Lỗi: {ex.detail}")

    ui.button("Bán hàng", on_click=do_sale, icon="point_of_sale").props("unelevated").classes("w-full btn-success text-lg py-2 mb-3")

    # Today's transactions
    with ui.element("div").classes("custom-card p-4 mt-4"):
        ui.label("🔁 Giao dịch hôm nay").classes("section-header")
    today_table = ui.table(
        columns=[
            {"name": "time", "label": "Giờ", "field": "time"},
            {"name": "customer", "label": "Khách hàng", "field": "customer"},
            {"name": "drink", "label": "Đồ uống", "field": "drink"},
            {"name": "qty", "label": "Số ly", "field": "qty"},
            {"name": "amount", "label": "Tiền", "field": "amount"},
            {"name": "type", "label": "Loại", "field": "type"},
            {"name": "by", "label": "Nhân viên", "field": "by"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full mt-2")

    def refresh_today_table():
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "%"
        with get_db() as conn:
            rows = conn.execute(
                """SELECT t.*, c.code as customer_code, c.full_name as customer_name,
                           d.name as drink_name, u.full_name as user_name
                    FROM transactions t
                    JOIN customers c ON c.id = t.customer_id
                    JOIN drinks d ON d.id = t.drink_id
                    JOIN users u ON u.id = t.created_by
                    WHERE t.created_at LIKE ? AND t.location_id = ?
                    ORDER BY t.created_at DESC LIMIT 50""",
                (today, loc_id),
            ).fetchall()
        today_table.rows = [
            {
                "id": r["id"],
                "time": r["created_at"][11:19],
                "customer": f"{r['customer_code']} - {r['customer_name']}",
                "drink": r["drink_name"],
                "qty": f"{r['servings']:.0f}",
                "amount": f"{r['amount']:,.0f}đ" if r["amount"] > 0 else "📦 Gói",
                "type": "Gói" if r["package_item_id"] else "Tiền mặt",
                "by": r["user_name"],
            }
            for r in rows
        ]
        today_table.update()

    ui.button("Làm mới", on_click=refresh_today_table, icon="refresh").props("outlined").classes("mt-2")

    # Initial load
    search_customers()
    refresh_today_table()
