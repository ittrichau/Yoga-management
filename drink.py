"""Drink management - location-filtered."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/drinks", tags=["drinks"])

class DrinkCreate(BaseModel):
    location_id: int | None = None
    name: str
    price: float
    description: str = ""
    recipe: str = ""

class DrinkUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    description: str | None = None
    recipe: str | None = None


@router.get("")
def list_drinks(location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if location_id:
            rows = conn.execute(
                "SELECT * FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
                (location_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM drinks WHERE is_active = 1 ORDER BY name"
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_drink(data: DrinkCreate, user: dict = Depends(require_role("OWNER"))):
    location_id = data.location_id or user.get("location_id")
    if not location_id:
        raise HTTPException(status_code=400, detail="Chưa chọn chi nhánh")

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO drinks (location_id, name, price_per_serving, description, recipe, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (location_id, data.name, data.price, data.description, data.recipe, user["id"]),
        )
        drink_id = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'drink', ?, ?)""",
            (location_id, user["id"], drink_id, f'{{"name":"{data.name}","price":{data.price}}}'),
        )
    return {"id": drink_id, "message": "Đồ uống đã được tạo"}


@router.put("/{drink_id}")
def update_drink(drink_id: int, data: DrinkUpdate, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drinks WHERE id = ?", (drink_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        updates = {}
        for field in ["name", "description", "recipe"]:
            val = getattr(data, field)
            if val is not None:
                updates[field] = val
        if data.price is not None:
            updates["price_per_serving"] = data.price
        if not updates:
            return {"message": "Không có thay đổi"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [drink_id]
        conn.execute(f"UPDATE drinks SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'update', 'drink', ?, ?)""",
            (row["location_id"], user["id"], drink_id, str(updates)),
        )
    return {"message": "Đồ uống đã được cập nhật"}


@router.delete("/{drink_id}")
def soft_delete_drink(drink_id: int, user: dict = Depends(require_role("ADMIN"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drinks WHERE id = ? AND is_active = 1", (drink_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        conn.execute("UPDATE drinks SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?", (drink_id,))
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'deactivate', 'drink', ?, ?)""",
            (row["location_id"], user["id"], drink_id, f'{{"name":"{row["name"]}"}}'),
        )
    return {"message": "Đồ uống đã bị vô hiệu hóa"}


# ==================== NiceGUI UI ====================
@ui.page("/drinks")
def drinks_page():
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

    # Helper functions defined first so on_click callbacks can reference them.
    # Widgets referenced inside (search_input, drink_table) are resolved at
    # call time via Python's closure mechanism, so they only need to exist
    # when the button is actually clicked – not at definition time.
    def refresh():
        search = search_input.value or ""
        with get_db() as conn:
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    "SELECT id, name, price_per_serving AS price, description, recipe FROM drinks WHERE is_active = 1 AND location_id = ? AND name LIKE ? ORDER BY name",
                    (loc_id, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, price_per_serving AS price, description, recipe FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
                    (loc_id,),
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["price"] = f"{r['price']:,.0f}đ"
            d["action"] = d["id"]
            result.append(d)
        drink_table.rows = result
        drink_table.update()

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("🥤").classes("text-2xl")
            ui.label("Quản lý đồ uống")

        # ── Search + Add ──
        with ui.element("div").classes("search-bar"):
            search_input = ui.input("Tìm kiếm đồ uống").props("outlined clearable dense").classes("flex-grow")
            ui.button("Tìm", icon="search", on_click=refresh).props("outlined")
            if role in ("OWNER", "ADMIN"):
                ui.button("Thêm đồ uống", icon="add", on_click=lambda: create_dialog.open()).props("unelevated").classes("btn-success")

        drink_table = ui.table(
            columns=[
                {"name": "name", "label": "Tên đồ uống", "field": "name"},
                {"name": "price", "label": "Giá", "field": "price"},
                {"name": "description", "label": "Mô tả", "field": "description"},
                {"name": "action", "label": "Thao tác", "field": "action"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

        # Create dialog
        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Thêm đồ uống").classes("text-xl font-bold mb-4 pr-8")
            d_name = ui.input("Tên đồ uống *").props("outlined dense").classes("w-full mb-2")
            d_price = ui.number("Giá bán *", value=0, format="%.0f").props("outlined dense").classes("w-full mb-2")
            d_desc = ui.textarea("Mô tả").props("outlined dense").classes("w-full mb-2")
            d_recipe = ui.textarea("Công thức (nguyên liệu)").props("outlined dense").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def handle_create():
                if not d_name.value or d_price.value is None:
                    err.set_text("Vui lòng nhập tên và giá")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    cur = conn.execute(
                        """INSERT INTO drinks (location_id, name, price_per_serving, description, recipe, created_by)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (loc_id, d_name.value, d_price.value, d_desc.value, d_recipe.value, user_id),
                    )
                    drink_id = cur.lastrowid
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'create', 'drink', ?, ?)""",
                        (loc_id, user_id, drink_id, f'{{"name":"{d_name.value}","price":{d_price.value}}}'),
                    )
                create_dialog.close()
                refresh()
                ui.notify("Đã thêm đồ uống", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary")

        # Edit dialog
        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Sửa đồ uống").classes("text-xl font-bold mb-4 pr-8")
            edit_id = ui.number("edit_id").props("hidden")
            e_name = ui.input("Tên đồ uống *").props("outlined dense").classes("w-full mb-2")
            e_price = ui.number("Giá bán *", value=0, format="%.0f").props("outlined dense").classes("w-full mb-2")
            e_desc = ui.textarea("Mô tả").props("outlined dense").classes("w-full mb-2")
            e_recipe = ui.textarea("Công thức").props("outlined dense").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def handle_edit():
                if not e_name.value or e_price.value is None:
                    edit_err.set_text("Vui lòng nhập tên và giá")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    conn.execute(
                        "UPDATE drinks SET name = ?, price_per_serving = ?, description = ?, recipe = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                        (e_name.value, e_price.value, e_desc.value, e_recipe.value, int(edit_id.value or 0)),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'update', 'drink', ?, ?)""",
                        (loc_id, user_id, int(edit_id.value or 0), f'{{"name":"{e_name.value}","price":{e_price.value}}}'),
                    )
                edit_dialog.close()
                refresh()
                ui.notify("Đã cập nhật đồ uống", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary")

        def open_edit(row):
            edit_id.value = row.get("id") or row.get("action")
            e_name.value = row.get("name", "")
            price_val = row.get("price", 0)
            if isinstance(price_val, str):
                price_val = price_val.replace("đ", "").replace(",", "").strip()
            try:
                e_price.value = float(price_val) if price_val else 0
            except (TypeError, ValueError):
                e_price.value = 0
            e_desc.value = row.get("description", "")
            e_recipe.value = row.get("recipe", "")
            edit_err.set_text("")
            edit_dialog.open()

        if role in ("OWNER", "ADMIN"):
            with ui.row().classes("gap-2 mb-4"):
                ui.button("Thêm đồ uống", on_click=create_dialog.open, icon="add").props("unelevated").classes("btn-success")
                ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

        search_input.on("keyup.enter", refresh)

        if role == "ADMIN":
            drink_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit_drink', props.row)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense color="negative" icon="delete" @click="$parent.$emit('delete_drink', props.row.id)">
                        <q-tooltip>Vô hiệu hóa</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
        elif role == "OWNER":
            drink_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit_drink', props.row)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
        else:
            drink_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <span class="text-gray-400">Chỉ xem</span>
                </q-td>
                """,
            )

        with ui.dialog() as confirm_delete_dialog, ui.card().classes("p-6 w-96 max-w-full relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=confirm_delete_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Xác nhận vô hiệu hóa").classes("text-xl font-bold mb-2 pr-8")
            confirm_delete_text = ui.label().classes("text-sm text-gray-600 mb-4")
            confirm_delete_id = ui.number("confirm_delete_id").props("hidden")

            def confirm_soft_delete_drink():
                confirm_delete_dialog.close()
                soft_delete_drink_ui(int(confirm_delete_id.value or 0))

            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button("Hủy", on_click=confirm_delete_dialog.close, icon="close").props("outlined")
                ui.button("Vô hiệu hóa", on_click=confirm_soft_delete_drink, icon="delete").props("unelevated color=negative")

        def open_confirm_delete_drink(drink_id):
            confirm_delete_id.value = int(drink_id)
            confirm_delete_text.set_text("Bạn có chắc muốn vô hiệu hóa đồ uống này? Thao tác này sẽ ẩn đồ uống khỏi danh sách sử dụng.")
            confirm_delete_dialog.open()

        def soft_delete_drink_ui(drink_id):
            try:
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM drinks WHERE id = ? AND is_active = 1", (int(drink_id),)).fetchone()
                    if not row:
                        ui.notify("Không tìm thấy đồ uống", type="warning")
                        return
                    conn.execute("UPDATE drinks SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?", (int(drink_id),))
                    user_id = app.storage.user.get("user_id", 1)
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'deactivate', 'drink', ?, ?)""",
                        (loc_id, user_id, int(drink_id), f'{{"name":"{row["name"]}"}}'),
                    )
                refresh()
                ui.notify("Đã vô hiệu hóa đồ uống", type="positive")
            except Exception as exc:
                ui.notify(f"Lỗi: {exc}", type="negative")

        drink_table.on("edit_drink", lambda e: open_edit(e.args))
        drink_table.on("delete_drink", lambda e: open_confirm_delete_drink(e.args))

        refresh()
