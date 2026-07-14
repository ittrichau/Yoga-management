"""Sales/transaction creation - filtered by location."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id
from product import PRODUCT_TYPE_LABELS

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class TransactionCreate(BaseModel):
    customer_id: int
    drink_id: int | None = None
    product_id: int | None = None
    servings: float = 1
    quantity: int = 1
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
    """Create a new transaction (drink or product)."""
    with get_db() as conn:
        # Validate customer
        customer = conn.execute(
            "SELECT id, code, full_name, location_id FROM customers WHERE id = ? AND is_active = 1",
            (data.customer_id,),
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng hoặc đã bị vô hiệu hóa")

        loc_id = customer["location_id"]

        # Validate: must have either drink_id or product_id
        if not data.drink_id and not data.product_id:
            raise HTTPException(status_code=400, detail="Vui lòng chọn đồ uống hoặc sản phẩm")

        item_name = ""
        amount = data.amount
        package_item_id = data.package_item_id

        # Product transaction
        if data.product_id:
            product = conn.execute(
                "SELECT id, name, price, sale_percent, current_stock FROM products WHERE id = ? AND is_active = 1 AND location_id = ?",
                (data.product_id, loc_id),
            ).fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại hoặc không thuộc cơ sở này")
            item_name = product["name"]
            qty = data.quantity or 1
            if product["current_stock"] < qty:
                raise HTTPException(status_code=400, detail=f"Không đủ hàng trong kho. Còn: {product['current_stock']} cái")

            if amount == 0:
                sale_price = product["price"] * (1 - product["sale_percent"] / 100)
                amount = sale_price * qty

            # Deduct stock
            conn.execute("UPDATE products SET current_stock = current_stock - ?, updated_at = datetime('now','localtime') WHERE id = ?",
                         (qty, data.product_id))
            conn.execute(
                """INSERT INTO product_stock_adjustments (location_id, product_id, adjustment_type, quantity, reason, created_by)
                   VALUES (?, ?, 'remove', ?, ?, ?)""",
                (loc_id, data.product_id, qty, f"Bán cho khách: {customer['full_name']}", user["id"]),
            )

            # Insert transaction
            cur = conn.execute(
                """INSERT INTO transactions (location_id, customer_id, product_id, quantity, amount, notes, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (loc_id, data.customer_id, data.product_id, qty, amount, data.notes, user["id"]),
            )
            tx_id = cur.lastrowid
            payment_type = "cash"

        # Drink transaction (original logic)
        else:
            drink = conn.execute(
                "SELECT id, name, price_per_serving FROM drinks WHERE id = ? AND is_active = 1 AND location_id = ?",
                (data.drink_id, loc_id),
            ).fetchone()
            if drink is None:
                raise HTTPException(status_code=404, detail="Đồ uống không tồn tại hoặc không thuộc cơ sở này")
            item_name = drink["name"]

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

            cur = conn.execute(
                """INSERT INTO transactions (location_id, customer_id, drink_id, package_item_id, servings, amount, notes, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (loc_id, data.customer_id, data.drink_id, package_item_id, data.servings, amount, data.notes, user["id"]),
            )
            tx_id = cur.lastrowid

            if package_item_id:
                conn.execute(
                    "UPDATE package_items SET remaining_servings = remaining_servings - ? WHERE id = ?",
                    (data.servings, package_item_id),
                )
            payment_type = "package" if package_item_id else "cash"

        # Audit log
        is_product = bool(data.product_id)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'transaction', ?, ?)""",
            (loc_id, user["id"], tx_id,
             f'{{"customer": "{customer["full_name"]}", "item": "{item_name}", "type": "{payment_type}", "is_product": {str(is_product).lower()}, "amount": {amount}}}'),
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

    render_navbar()
    render()


def render():
    """Render the sales / transaction creation page."""
    loc_id = get_current_location_id()

    customer_options = {}
    package_item_options = {}
    drink_options = {}
    drink_meta = {}
    product_options = {}
    product_meta = {}
    cart_items = []

    with get_db() as conn:
        all_drinks = conn.execute(
            "SELECT id, name, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()

    for drink in all_drinks:
        drink_options[drink["id"]] = f"{drink['name']} ({drink['price_per_serving']:,.0f}đ/ly)"
        drink_meta[drink["id"]] = {
            "name": drink["name"],
            "price_per_serving": drink["price_per_serving"],
        }

    with ui.element("div").classes("page-container sales-page-container"):
        with ui.row().classes("items-center page-title sales-page-title w-full"):
            ui.icon("point_of_sale").classes("text-2xl")
            with ui.column().classes("gap-0"):
                ui.label("Bán hàng")
                ui.label("Chọn hàng, thêm vào giỏ và thanh toán một lần").classes("text-sm text-gray-500 font-normal")

        with ui.element("div").classes("sales-pos-grid"):
            with ui.element("div").classes("sales-main-column"):
                with ui.element("div").classes("custom-card sales-card"):
                    ui.label("👤 Khách hàng").classes("section-header sales-section-header")
                    with ui.element("div").classes("search-bar sales-search-bar"):
                        search_input = ui.input("Tìm khách hàng theo tên hoặc mã").props("outlined clearable dense").classes("flex-grow")
                        ui.button("Tìm", on_click=lambda: search_customers(), icon="search").props("outlined")
                    customer_select = ui.select({}, label="Chọn khách hàng *").props("outlined dense").classes("w-full")
                    customer_hint = ui.label("").classes("text-xs text-gray-500 mt-1")

                with ui.element("div").classes("custom-card sales-card"):
                    ui.label("🛒 Chọn mặt hàng").classes("section-header sales-section-header")
                    with ui.tabs().classes("w-full sales-tabs") as sale_type:
                        drink_tab = ui.tab("🥤 Đồ uống").props("dense")
                        product_tab = ui.tab("🧺 Sản phẩm").props("dense")

                    with ui.tab_panels(sale_type, value=drink_tab).classes("w-full sales-tab-panels"):
                        with ui.tab_panel(drink_tab).classes("p-0"):
                            package_panel = ui.column().classes("w-full sales-package-panel")
                            with package_panel:
                                pkg_info = ui.label().classes("text-sm font-medium text-primary mb-1")
                                package_select = ui.select({}, label="Thanh toán bằng gói đồ uống").props("outlined dense clearable").classes("w-full")
                                ui.label("Để trống nếu bán lẻ thu tiền.").classes("text-xs text-gray-500 mt-1")
                            if drink_options:
                                drink_select = ui.select(drink_options, label="Đồ uống *").props("outlined dense").classes("w-full mb-2")
                                drink_select.set_value(list(drink_options.keys())[0])
                            else:
                                drink_select = ui.select({}, label="Đồ uống *").props("outlined dense").classes("w-full mb-2")
                                ui.label("Chưa có đồ uống đang hoạt động tại cơ sở này.").classes("text-orange-600 text-sm mb-2")
                            servings = ui.number("Số ly", value=1, min=0.1, step=0.5).props("outlined dense").classes("w-full mb-2")
                            drink_preview = ui.label().classes("sales-product-preview")
                            ui.button("Thêm đồ uống vào giỏ", on_click=lambda: add_drink_to_cart(), icon="add_shopping_cart").props("unelevated").classes("w-full btn-success")

                        with ui.tab_panel(product_tab).classes("p-0"):
                            ui.label("Chọn sản phẩm, nhập số lượng rồi thêm vào giỏ.").classes("sales-product-help")
                            with ui.element("div").classes("search-bar sales-search-bar"):
                                product_search = ui.input("Tìm sản phẩm").props("outlined clearable dense").classes("flex-grow")
                                product_type_filter = ui.select(
                                    {
                                        "": "Tất cả loại",
                                        "mat": "Thảm",
                                        "clothing": "Quần áo",
                                        "accessory": "Phụ kiện",
                                        "other": "Khác",
                                    },
                                    label="Loại",
                                    value="",
                                ).props("outlined dense").classes("sales-type-filter")
                                ui.button("Lọc", on_click=lambda: load_products(), icon="filter_alt").props("outlined")

                            product_select = ui.select({}, label="Sản phẩm *").props("outlined dense").classes("w-full mb-2")
                            product_qty = ui.number("Số lượng", value=1, min=1, step=1).props("outlined dense").classes("w-full mb-2")
                            product_preview = ui.label().classes("sales-product-preview")
                            ui.button("Thêm sản phẩm vào giỏ", on_click=lambda: add_product_to_cart(), icon="add_shopping_cart").props("unelevated").classes("w-full btn-success")

            with ui.element("div").classes("sales-side-column"):
                with ui.element("div").classes("custom-card sales-card sales-payment-card"):
                    ui.label("🧾 Giỏ hàng").classes("section-header sales-section-header")
                    cart_table = ui.table(
                        columns=[
                            {"name": "item", "label": "Món", "field": "item"},
                            {"name": "qty", "label": "SL", "field": "qty"},
                            {"name": "amount", "label": "Tiền", "field": "amount"},
                            {"name": "action", "label": "", "field": "action"},
                        ],
                        rows=[],
                        row_key="cart_id",
                    ).classes("w-full sales-cart-table")
                    cart_total_label = ui.label("Tổng: 0đ").classes("text-lg font-semibold text-primary mt-2")
                    notes = ui.input("Ghi chú đơn hàng").props("outlined dense").classes("w-full mt-2 mb-3")
                    err = ui.label().classes("text-red-500 text-sm mb-2")
                    success = ui.label().classes("text-green-600 text-sm mb-2")
                    ui.button("Thanh toán giỏ hàng", on_click=lambda: checkout_cart(), icon="point_of_sale").props("unelevated").classes("w-full btn-success text-lg py-2")

        with ui.element("div").classes("custom-card sales-card sales-table-card"):
            with ui.row().classes("items-center justify-between w-full sales-table-header"):
                ui.label("🔁 Giao dịch hôm nay").classes("section-header sales-section-header")
                ui.button("Làm mới", on_click=lambda: refresh_today_table(), icon="refresh").props("outlined dense")
            today_table = ui.table(
                columns=[
                    {"name": "time", "label": "Giờ", "field": "time"},
                    {"name": "detail", "label": "Khách / mặt hàng", "field": "detail"},
                    {"name": "qty", "label": "SL", "field": "qty"},
                    {"name": "payment", "label": "Thanh toán", "field": "payment"},
                    {"name": "by", "label": "NV", "field": "by"},
                ],
                rows=[],
                row_key="id",
            ).classes("w-full mt-2 sales-today-table")

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
        for row in rows:
            customer_options[row["id"]] = f"{row['code']} - {row['full_name']}"
        customer_select.set_options(customer_options)

        if customer_options and not customer_select.value:
            customer_select.set_value(list(customer_options.keys())[0])
            customer_hint.set_text("")
        elif not customer_options:
            customer_select.set_value(None)
            customer_hint.set_text("Không tìm thấy khách hàng phù hợp tại cơ sở hiện tại.")
        else:
            customer_hint.set_text("")
        load_packages()

    def load_packages():
        customer_id = customer_select.value
        if not customer_id:
            package_select.set_options({"": "--- Bán lẻ (thu tiền) ---"})
            package_select.set_value("")
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
        for package in packages:
            label = f"{package['name'] or 'Gói'} - {package['drink_name']}: {package['remaining_servings']:.0f}/{package['total_servings']:.0f} ly"
            options[package["pi_id"]] = label
            package_item_options[package["pi_id"]] = dict(package)

        package_select.set_options(options)
        package_select.set_value("")
        pkg_info.set_text(f"Khách hàng có {len(packages)} gói đồ uống đang hoạt động" if packages else "Khách hàng chưa có gói đồ uống còn lượt")

    def load_products():
        search = (product_search.value or "").strip()
        product_type = product_type_filter.value or ""
        where = ["is_active = 1", "location_id = ?", "current_stock > 0"]
        params = [loc_id]
        if search:
            where.append("name LIKE ?")
            params.append(f"%{search}%")
        if product_type:
            where.append("product_type = ?")
            params.append(product_type)

        with get_db() as conn:
            rows = conn.execute(
                f"""SELECT id, name, price, sale_percent, current_stock, product_type
                    FROM products
                    WHERE {' AND '.join(where)}
                    ORDER BY name""",
                params,
            ).fetchall()

        product_options.clear()
        product_meta.clear()
        for product in rows:
            sale_price = product["price"] * (1 - product["sale_percent"] / 100)
            type_label = PRODUCT_TYPE_LABELS.get(product["product_type"], product["product_type"])
            product_options[product["id"]] = f"{product['name']} - {sale_price:,.0f}đ"
            product_meta[product["id"]] = {
                "name": product["name"],
                "type_label": type_label,
                "price": product["price"],
                "sale_percent": product["sale_percent"],
                "sale_price": sale_price,
                "current_stock": product["current_stock"],
            }

        product_select.set_options(product_options)
        if product_options:
            if product_select.value not in product_options:
                product_select.set_value(list(product_options.keys())[0])
            update_product_preview()
        else:
            product_select.set_value(None)
            product_preview.set_text("Không có sản phẩm còn tồn kho phù hợp.")
        refresh_cart_table()

    def update_product_preview():
        product_id = product_select.value
        product = product_meta.get(product_id)
        if not product:
            product_preview.set_text("")
            return

        qty = int(product_qty.value or 1)
        total = product["sale_price"] * qty
        discount = f", giảm {product['sale_percent']:.0f}%" if product["sale_percent"] else ""
        product_preview.set_text(
            f"{product['type_label']} · Tồn {product['current_stock']} cái · "
            f"Giá bán {product['sale_price']:,.0f}đ{discount} · Tạm tính {total:,.0f}đ"
        )

    def update_drink_amount():
        drink_id = drink_select.value
        drink = drink_meta.get(drink_id)
        if not drink:
            drink_preview.set_text("")
            return
        qty = servings.value or 1
        if package_select.value:
            drink_preview.set_text(f"{drink['name']} · {qty:g} ly · Thanh toán bằng gói")
        else:
            drink_preview.set_text(f"{drink['name']} · {qty:g} ly · Tạm tính {drink['price_per_serving'] * qty:,.0f}đ")

    def on_package_change():
        package_item_id = package_select.value
        if package_item_id and package_item_id in package_item_options:
            package = package_item_options[package_item_id]
            drink_select.set_value(package["drink_id"])
            servings.set_value(1)
        update_drink_amount()

    def on_sale_type_change():
        package_panel.set_visibility(sale_type.value != product_tab)
        if sale_type.value == product_tab:
            update_product_preview()
        else:
            update_drink_amount()

    def add_drink_to_cart():
        err.set_text("")
        success.set_text("")
        drink_id = drink_select.value
        if not drink_id:
            err.set_text("Vui lòng chọn đồ uống")
            return

        qty = servings.value or 1
        if qty <= 0:
            err.set_text("Số ly phải lớn hơn 0")
            return

        drink = drink_meta.get(drink_id)
        if not drink:
            err.set_text("Đồ uống không hợp lệ")
            return

        package_item_id = package_select.value or None
        amount = 0 if package_item_id else drink["price_per_serving"] * qty
        cart_items.append(
            {
                "cart_id": len(cart_items) + 1,
                "type": "drink",
                "drink_id": drink_id,
                "package_item_id": package_item_id,
                "name": drink["name"],
                "qty": float(qty),
                "unit": "ly",
                "unit_price": 0 if package_item_id else drink["price_per_serving"],
                "amount": amount,
                "payment": "Gói" if package_item_id else "Tiền mặt",
            }
        )
        refresh_cart_table()
        success.set_text(f"Đã thêm {drink['name']} vào giỏ")

    def add_product_to_cart():
        err.set_text("")
        success.set_text("")
        product_id = product_select.value
        if not product_id:
            err.set_text("Vui lòng chọn sản phẩm còn tồn kho")
            return

        product = product_meta.get(product_id)
        if not product:
            err.set_text("Sản phẩm không hợp lệ")
            return

        qty = int(product_qty.value or 1)
        if qty <= 0:
            err.set_text("Số lượng sản phẩm phải lớn hơn 0")
            return

        qty_in_cart = sum(item["qty"] for item in cart_items if item["type"] == "product" and item["product_id"] == product_id)
        if product["current_stock"] < qty + qty_in_cart:
            err.set_text(f"Không đủ hàng trong kho. Còn: {product['current_stock']} cái")
            return

        cart_items.append(
            {
                "cart_id": len(cart_items) + 1,
                "type": "product",
                "product_id": product_id,
                "name": product["name"],
                "qty": qty,
                "unit": "cái",
                "unit_price": product["sale_price"],
                "amount": product["sale_price"] * qty,
                "payment": "Tiền mặt",
            }
        )
        refresh_cart_table()
        success.set_text(f"Đã thêm {product['name']} vào giỏ")

    def remove_cart_item(cart_id):
        cart_items[:] = [item for item in cart_items if item["cart_id"] != cart_id]
        refresh_cart_table()

    def refresh_cart_table():
        rows = []
        total = 0
        for item in cart_items:
            total += item["amount"]
            rows.append(
                {
                    "cart_id": item["cart_id"],
                    "item": f"{item['name']}\n{item['payment']}",
                    "qty": f"{item['qty']:g} {item['unit']}",
                    "amount": "Gói" if item["amount"] == 0 else f"{item['amount']:,.0f}đ",
                    "action": "Xóa",
                }
            )
        cart_table.rows = rows
        cart_table.update()
        cart_total_label.set_text(f"Tổng: {total:,.0f}đ")

    def checkout_cart():
        err.set_text("")
        success.set_text("")
        customer_id = customer_select.value
        if not customer_id:
            err.set_text("Vui lòng chọn khách hàng trước khi thanh toán")
            return
        if not cart_items:
            err.set_text("Giỏ hàng đang trống")
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

                tx_ids = []
                total_amount = 0
                audit_items = []

                for item in cart_items:
                    if item["type"] == "product":
                        product = conn.execute(
                            "SELECT id, name, price, sale_percent, current_stock FROM products WHERE id = ? AND is_active = 1 AND location_id = ?",
                            (item["product_id"], loc_id),
                        ).fetchone()
                        if product is None:
                            err.set_text(f"Sản phẩm {item['name']} không tồn tại hoặc đã bị vô hiệu hóa")
                            return

                        qty = int(item["qty"])
                        if product["current_stock"] < qty:
                            err.set_text(f"Không đủ hàng {product['name']}. Còn: {product['current_stock']} cái")
                            return

                        amount = item["amount"]
                        conn.execute(
                            "UPDATE products SET current_stock = current_stock - ?, updated_at = datetime('now','localtime') WHERE id = ?",
                            (qty, item["product_id"]),
                        )
                        conn.execute(
                            """INSERT INTO product_stock_adjustments (location_id, product_id, adjustment_type, quantity, reason, created_by)
                               VALUES (?, ?, 'remove', ?, ?, ?)""",
                            (loc_id, item["product_id"], qty, f"Bán cho khách: {customer['full_name']}", user_id),
                        )
                        cur = conn.execute(
                            """INSERT INTO transactions (location_id, customer_id, product_id, quantity, amount, notes, created_by)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (loc_id, customer_id, item["product_id"], qty, amount, notes.value, user_id),
                        )
                        tx_ids.append(cur.lastrowid)
                        total_amount += amount
                        audit_items.append(f"{qty} {item['unit']} {product['name']}")

                    else:
                        drink = conn.execute(
                            "SELECT id, name, price_per_serving FROM drinks WHERE id = ? AND is_active = 1 AND location_id = ?",
                            (item["drink_id"], loc_id),
                        ).fetchone()
                        if drink is None:
                            err.set_text(f"Đồ uống {item['name']} không tồn tại hoặc đã bị vô hiệu hóa")
                            return

                        qty = float(item["qty"])
                        package_item_id = item.get("package_item_id")
                        amount = 0 if package_item_id else item["amount"]

                        if package_item_id:
                            package_item = conn.execute(
                                """SELECT pi.*, p.name as pkg_name, p.id as pkg_id, p.location_id
                                   FROM package_items pi
                                   JOIN packages p ON p.id = pi.package_id
                                   WHERE pi.id = ? AND p.is_active = 1 AND p.customer_id = ? AND p.location_id = ?""",
                                (package_item_id, customer_id, loc_id),
                            ).fetchone()
                            if package_item is None:
                                err.set_text("Gói không hợp lệ hoặc không thuộc khách hàng này")
                                return
                            if package_item["remaining_servings"] < qty:
                                err.set_text(f"Không đủ ly trong gói. Còn {package_item['remaining_servings']:.0f} ly")
                                return
                        else:
                            _deduct_ingredients(conn, item["drink_id"], qty, loc_id)

                        cur = conn.execute(
                            """INSERT INTO transactions (location_id, customer_id, drink_id, package_item_id, servings, amount, notes, created_by)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (loc_id, customer_id, item["drink_id"], package_item_id, qty, amount, notes.value, user_id),
                        )
                        tx_ids.append(cur.lastrowid)

                        if package_item_id:
                            conn.execute(
                                "UPDATE package_items SET remaining_servings = remaining_servings - ? WHERE id = ?",
                                (qty, package_item_id),
                            )

                        total_amount += amount
                        audit_items.append(f"{qty:g} {item['unit']} {drink['name']}")

                first_tx_id = tx_ids[0] if tx_ids else None
                conn.execute(
                    """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                       VALUES (?, ?, 'create', 'transaction', ?, ?)""",
                    (
                        loc_id,
                        user_id,
                        first_tx_id,
                        f'{{"customer": "{customer["full_name"]}", "items": "{", ".join(audit_items)}", "transaction_ids": "{tx_ids}", "amount": {total_amount}, "type": "cart"}}',
                    ),
                )

            item_count = len(cart_items)
            cart_items.clear()
            refresh_cart_table()
            load_packages()
            load_products()
            refresh_today_table()
            success.set_text(f"Đã thanh toán {item_count} món cho {customer['full_name']}. Tổng thu {total_amount:,.0f}đ")
            ui.notify("Thanh toán giỏ hàng thành công!", type="positive")

        except HTTPException as ex:
            err.set_text(f"Lỗi: {ex.detail}")
        except Exception as exc:
            err.set_text(f"Lỗi bán hàng: {exc}")

    def refresh_today_table():
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "%"
        with get_db() as conn:
            rows = conn.execute(
                """SELECT t.*, c.code as customer_code, c.full_name as customer_name,
                           COALESCE(d.name, p.name) as item_name, u.full_name as user_name
                    FROM transactions t
                    JOIN customers c ON c.id = t.customer_id
                    JOIN users u ON u.id = t.created_by
                    LEFT JOIN drinks d ON d.id = t.drink_id
                    LEFT JOIN products p ON p.id = t.product_id
                    WHERE t.created_at LIKE ? AND t.location_id = ?
                    ORDER BY t.created_at DESC LIMIT 50""",
                (today, loc_id),
            ).fetchall()

        today_table.rows = []
        for row in rows:
            is_product = bool(row["product_id"])
            qty = row["quantity"] if is_product and row["quantity"] else row["servings"]
            unit = "cái" if is_product else "ly"
            payment_label = "Sản phẩm" if is_product else ("Gói" if row["package_item_id"] else "Tiền mặt")
            amount_label = f"{row['amount']:,.0f}đ" if row["amount"] > 0 else "📦 Gói"
            today_table.rows.append(
                {
                    "id": row["id"],
                    "time": row["created_at"][11:19],
                    "detail": f"{row['customer_code']} - {row['customer_name']}\n{row['item_name'] or '—'}",
                    "qty": f"{qty:,.0f} {unit}",
                    "payment": f"{amount_label}\n{payment_label}",
                    "by": row["user_name"],
                }
            )
        today_table.update()

    cart_table.add_slot(
        "body-cell-action",
        """
        <q-td :props="props">
          <q-btn flat dense color="negative" icon="delete" size="sm" @click="$parent.$emit('remove', props.row.cart_id)" />
        </q-td>
        """,
    )
    cart_table.on("remove", lambda e: remove_cart_item(e.args))

    customer_select.on("update:model-value", lambda e: load_packages())
    search_input.on("keyup.enter", lambda e: search_customers())
    package_select.on("update:model-value", lambda e: on_package_change())
    drink_select.on("update:model-value", lambda e: update_drink_amount())
    servings.on("update:model-value", lambda e: update_drink_amount())
    sale_type.on("update:model-value", lambda e: on_sale_type_change())
    product_search.on("keyup.enter", lambda e: load_products())
    product_type_filter.on("update:model-value", lambda e: load_products())
    product_select.on("update:model-value", lambda e: update_product_preview())
    product_qty.on("update:model-value", lambda e: update_product_preview())

    search_customers()
    load_products()
    on_sale_type_change()
    update_drink_amount()
    refresh_today_table()