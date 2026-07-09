"""Product management for non-drink items (mats, clothing, accessories, etc.) - location-filtered."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/products", tags=["products"])

PRODUCT_TYPE_LABELS = {
    "mat": "Thảm",
    "clothing": "Quần áo",
    "accessory": "Phụ kiện",
    "other": "Khác",
}


class ProductCreate(BaseModel):
    name: str
    product_type: str = "other"
    price: float = 0
    sale_percent: float = 0
    current_stock: int = 0
    min_stock: int = 0


class ProductUpdate(BaseModel):
    name: str | None = None
    product_type: str | None = None
    price: float | None = None
    sale_percent: float | None = None
    current_stock: int | None = None
    min_stock: int | None = None


@router.get("")
def list_products(
    product_type: str | None = None,
    search: str | None = None,
    location_id: int | None = None,
    user: dict = Depends(get_current_user),
):
    with get_db() as conn:
        where = ["p.is_active = 1"]
        params = []
        if location_id:
            where.append("p.location_id = ?")
            params.append(location_id)
        if product_type:
            where.append("p.product_type = ?")
            params.append(product_type)
        if search:
            where.append("p.name LIKE ?")
            params.append(f"%{search}%")
        where_clause = " AND ".join(where)
        rows = conn.execute(
            f"SELECT * FROM products p WHERE {where_clause} ORDER BY p.name",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/low-stock")
def get_low_stock_products(location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if location_id:
            rows = conn.execute(
                "SELECT * FROM products WHERE is_active = 1 AND location_id = ? AND current_stock <= min_stock ORDER BY name",
                (location_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products WHERE is_active = 1 AND current_stock <= min_stock ORDER BY name"
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_product(data: ProductCreate, user: dict = Depends(require_role("MANAGER"))):
    loc_id = get_current_location_id()
    if not loc_id:
        raise HTTPException(status_code=400, detail="Chưa chọn chi nhánh")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO products (location_id, name, product_type, price, sale_percent,
               current_stock, min_stock, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (loc_id, data.name, data.product_type, data.price, data.sale_percent,
             data.current_stock, data.min_stock, user["id"]),
        )
        product_id = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'product', ?, ?)""",
            (loc_id, user["id"], product_id,
             f'{{"name":"{data.name}","type":"{data.product_type}","price":{data.price}}}'),
        )
    return {"id": product_id, "message": "Sản phẩm đã được tạo"}


@router.put("/{product_id}")
def update_product(product_id: int, data: ProductUpdate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
        updates = {}
        for field in ["name", "product_type", "price", "sale_percent", "current_stock", "min_stock"]:
            val = getattr(data, field)
            if val is not None:
                updates[field] = val
        if not updates:
            return {"message": "Không có thay đổi"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [product_id]
        conn.execute(f"UPDATE products SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'update', 'product', ?, ?)""",
            (row["location_id"], user["id"], product_id, str(updates)),
        )
    return {"message": "Sản phẩm đã được cập nhật"}


@router.delete("/{product_id}")
def soft_delete_product(product_id: int, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
        conn.execute("UPDATE products SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?", (product_id,))
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'soft_delete', 'product', ?, ?)""",
            (row["location_id"], user["id"], product_id, f'{{"name":"{row["name"]}"}}'),
        )
    return {"message": "Sản phẩm đã bị vô hiệu hóa"}


# ==================== NiceGUI UI ====================
@ui.page("/products")
def products_page():
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

    def refresh():
        search = search_input.value or ""
        type_filter = type_select.value or ""
        with get_db() as conn:
            where = ["p.is_active = 1", "p.location_id = ?"]
            params = [loc_id]
            if search:
                where.append("p.name LIKE ?")
                params.append(f"%{search}%")
            if type_filter:
                where.append("p.product_type = ?")
                params.append(type_filter)
            where_clause = " AND ".join(where)
            rows = conn.execute(
                f"SELECT * FROM products p WHERE {where_clause} ORDER BY p.name",
                params,
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            sale_price = d["price"] * (1 - d["sale_percent"] / 100)
            d["type_label"] = PRODUCT_TYPE_LABELS.get(d["product_type"], d["product_type"])
            d["price_display"] = f"{d['price']:,.0f}đ"
            d["sale_display"] = f"{d['sale_percent']:.0f}%" if d["sale_percent"] > 0 else "-"
            d["final_price"] = f"{sale_price:,.0f}đ"
            d["stock_status"] = "🔴 THIẾU" if d["current_stock"] <= d["min_stock"] else ("🟡 Thấp" if d["current_stock"] <= d["min_stock"] * 2 else "🟢 OK")
            d["action"] = d["id"]
            result.append(d)
        product_table.rows = result
        product_table.update()

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("🧺").classes("text-2xl")
            ui.label("Quản lý sản phẩm")

        # Search + Filter + Add
        with ui.element("div").classes("search-bar"):
            search_input = ui.input("Tìm kiếm sản phẩm").props("outlined clearable dense").classes("flex-grow")
            type_select = ui.select(
                {"": "Tất cả loại", "mat": "Thảm", "clothing": "Quần áo", "accessory": "Phụ kiện", "other": "Khác"},
                label="Loại",
            ).props("outlined dense").classes("w-40")
            ui.button("Tìm", icon="search", on_click=refresh).props("outlined")
            if role in ("MANAGER", "OWNER"):
                ui.button("Thêm sản phẩm", icon="add", on_click=lambda: create_dialog.open()).props("unelevated").classes("btn-success")

        product_table = ui.table(
            columns=[
                {"name": "name", "label": "Tên sản phẩm", "field": "name"},
                {"name": "type_label", "label": "Loại", "field": "type_label"},
                {"name": "price_display", "label": "Giá gốc", "field": "price_display"},
                {"name": "sale_display", "label": "Giảm giá", "field": "sale_display"},
                {"name": "final_price", "label": "Giá bán", "field": "final_price"},
                {"name": "current_stock", "label": "Tồn kho", "field": "current_stock"},
                {"name": "stock_status", "label": "Trạng thái", "field": "stock_status"},
                {"name": "action", "label": "Thao tác", "field": "action"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

        # ── Create Dialog ──
        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96 relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Thêm sản phẩm").classes("text-xl font-bold mb-4 pr-8")
            c_name = ui.input("Tên sản phẩm *").props("outlined dense").classes("w-full mb-2")
            c_type = ui.select(
                {"mat": "Thảm", "clothing": "Quần áo", "accessory": "Phụ kiện", "other": "Khác"},
                label="Loại sản phẩm *",
                value="other",
            ).props("outlined dense").classes("w-full mb-2")
            c_price = ui.number("Giá gốc (VNĐ) *", value=0, format="%.0f").props("outlined dense").classes("w-full mb-2")
            c_sale = ui.number("Giảm giá (%)", value=0, min=0, max=100, format="%.0f").props("outlined dense").classes("w-full mb-2")
            c_stock = ui.number("Tồn kho hiện tại", value=0, format="%.0f").props("outlined dense").classes("w-full mb-2")
            c_min = ui.number("Tồn kho tối thiểu", value=0, format="%.0f").props("outlined dense").classes("w-full mb-4")
            create_err = ui.label().classes("text-red-500 text-sm")

            def handle_create():
                if not c_name.value or c_price.value is None:
                    create_err.set_text("Vui lòng nhập tên và giá")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    cur = conn.execute(
                        """INSERT INTO products (location_id, name, product_type, price, sale_percent,
                           current_stock, min_stock, created_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (loc_id, c_name.value, c_type.value, c_price.value or 0,
                         c_sale.value or 0, int(c_stock.value or 0), int(c_min.value or 0), user_id),
                    )
                    product_id = cur.lastrowid
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'create', 'product', ?, ?)""",
                        (loc_id, user_id, product_id,
                         f'{{"name":"{c_name.value}","type":"{c_type.value}","price":{c_price.value or 0}}}'),
                    )
                create_dialog.close()
                refresh()
                ui.notify("Đã thêm sản phẩm", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary")

        # ── Edit Dialog ──
        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96 relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Sửa sản phẩm").classes("text-xl font-bold mb-4 pr-8")
            edit_id = ui.number("edit_id").props("hidden")
            e_name = ui.input("Tên sản phẩm *").props("outlined dense").classes("w-full mb-2")
            e_type = ui.select(
                {"mat": "Thảm", "clothing": "Quần áo", "accessory": "Phụ kiện", "other": "Khác"},
                label="Loại sản phẩm *",
            ).props("outlined dense").classes("w-full mb-2")
            e_price = ui.number("Giá gốc (VNĐ) *", value=0, format="%.0f").props("outlined dense").classes("w-full mb-2")
            e_sale = ui.number("Giảm giá (%)", value=0, min=0, max=100, format="%.0f").props("outlined dense").classes("w-full mb-2")
            e_stock = ui.number("Tồn kho hiện tại", value=0, format="%.0f").props("outlined dense").classes("w-full mb-2")
            e_min = ui.number("Tồn kho tối thiểu", value=0, format="%.0f").props("outlined dense").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def handle_edit():
                if not e_name.value or e_price.value is None:
                    edit_err.set_text("Vui lòng nhập tên và giá")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    conn.execute(
                        """UPDATE products SET name = ?, product_type = ?, price = ?, sale_percent = ?,
                           current_stock = ?, min_stock = ?, updated_at = datetime('now','localtime')
                           WHERE id = ?""",
                        (e_name.value, e_type.value, e_price.value or 0, e_sale.value or 0,
                         int(e_stock.value or 0), int(e_min.value or 0), int(edit_id.value or 0)),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'update', 'product', ?, ?)""",
                        (loc_id, user_id, int(edit_id.value or 0),
                         f'{{"name":"{e_name.value}","price":{e_price.value or 0}}}'),
                    )
                edit_dialog.close()
                refresh()
                ui.notify("Đã cập nhật sản phẩm", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary")

        def open_edit(row):
            edit_id.value = row.get("id") or row.get("action")
            e_name.value = row.get("name", "")
            e_type.value = row.get("product_type", "other")
            e_price.value = float(row.get("price", 0))
            e_sale.value = float(row.get("sale_percent", 0))
            e_stock.value = int(row.get("current_stock", 0))
            e_min.value = int(row.get("min_stock", 0))
            edit_err.set_text("")
            edit_dialog.open()

        def soft_delete_product_ui(product_id):
            try:
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (int(product_id),)).fetchone()
                    if not row:
                        ui.notify("Không tìm thấy sản phẩm", type="warning")
                        return
                    conn.execute("UPDATE products SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?", (int(product_id),))
                    user_id = app.storage.user.get("user_id", 1)
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'soft_delete', 'product', ?, ?)""",
                        (loc_id, user_id, int(product_id), f'{{"name":"{row["name"]}"}}'),
                    )
                refresh()
                ui.notify("Đã vô hiệu hóa sản phẩm", type="positive")
            except Exception as exc:
                ui.notify(f"Lỗi: {exc}", type="negative")

        # Action buttons based on role
        if role == "OWNER":
            product_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit_product', props.row)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense color="negative" icon="delete" @click="$parent.$emit('delete_product', props.row.id)">
                        <q-tooltip>Vô hiệu hóa</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
        else:
            product_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit_product', props.row)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )

        product_table.on("edit_product", lambda e: open_edit(e.args))
        product_table.on("delete_product", lambda e: soft_delete_product_ui(e.args))

        search_input.on("keyup.enter", refresh)
        type_select.on("update:model-value", lambda e: refresh())

        refresh()