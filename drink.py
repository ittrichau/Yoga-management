"""Drink management (CRUD đồ uống + công thức pha chế) - filtered by location."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/drinks", tags=["drinks"])

class DrinkCreate(BaseModel):
    name: str
    price_per_serving: float = 0
    location_id: int | None = None
    recipe: list[dict] = []

class DrinkUpdate(BaseModel):
    name: str | None = None
    price_per_serving: float | None = None
    recipe: list[dict] | None = None


@router.get("")
def list_drinks(search: str = "", location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            if location_id:
                rows = conn.execute(
                    "SELECT id, name, price_per_serving, is_active, created_at, location_id FROM drinks WHERE is_active = 1 AND location_id = ? AND name LIKE ? ORDER BY name",
                    (location_id, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, price_per_serving, is_active, created_at, location_id FROM drinks WHERE is_active = 1 AND name LIKE ? ORDER BY name",
                    (like,),
                ).fetchall()
        else:
            if location_id:
                rows = conn.execute(
                    "SELECT id, name, price_per_serving, is_active, created_at, location_id FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
                    (location_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, price_per_serving, is_active, created_at, location_id FROM drinks WHERE is_active = 1 ORDER BY name"
                ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{drink_id}")
def get_drink(drink_id: int, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        drink = conn.execute("SELECT * FROM drinks WHERE id = ?", (drink_id,)).fetchone()
        if drink is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        recipe = conn.execute(
            """SELECT dr.*, i.name as ingredient_name, i.unit
               FROM drink_recipes dr
               JOIN ingredients i ON i.id = dr.ingredient_id
               WHERE dr.drink_id = ?""",
            (drink_id,),
        ).fetchall()
    result = dict(drink)
    result["recipe"] = [dict(r) for r in recipe]
    return result


@router.post("", status_code=201)
def create_drink(data: DrinkCreate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM drinks WHERE name = ? AND location_id = ?",
            (data.name, data.location_id),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Tên đồ uống đã tồn tại tại cơ sở này")
        cur = conn.execute(
            "INSERT INTO drinks (location_id, name, price_per_serving, created_by) VALUES (?, ?, ?, ?)",
            (data.location_id, data.name, data.price_per_serving, user["id"]),
        )
        drink_id = cur.lastrowid
        for item in data.recipe:
            conn.execute(
                "INSERT INTO drink_recipes (drink_id, ingredient_id, quantity_per_serving) VALUES (?, ?, ?)",
                (drink_id, item.get("ingredient_id"), item.get("quantity_per_serving", 0)),
            )
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'create', 'drink', ?, ?)",
            (data.location_id, user["id"], drink_id, f'{{"name":"{data.name}"}}'),
        )
    return {"id": drink_id, "message": "Đồ uống đã được tạo"}


@router.put("/{drink_id}")
def update_drink(drink_id: int, data: DrinkUpdate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drinks WHERE id = ?", (drink_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        updates = {}
        if data.name is not None:
            existing = conn.execute(
                "SELECT id FROM drinks WHERE name = ? AND location_id = ? AND id != ?",
                (data.name, row["location_id"], drink_id),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Tên đồ uống đã tồn tại")
            updates["name"] = data.name
        if data.price_per_serving is not None:
            updates["price_per_serving"] = data.price_per_serving
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [drink_id]
            conn.execute(f"UPDATE drinks SET {set_clause} WHERE id = ?", values)
        if data.recipe is not None:
            conn.execute("DELETE FROM drink_recipes WHERE drink_id = ?", (drink_id,))
            for item in data.recipe:
                conn.execute(
                    "INSERT INTO drink_recipes (drink_id, ingredient_id, quantity_per_serving) VALUES (?, ?, ?)",
                    (drink_id, item.get("ingredient_id"), item.get("quantity_per_serving", 0)),
                )
            conn.execute(
                "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'update_recipe', 'drink', ?, ?)",
                (row["location_id"], user["id"], drink_id, str(data.recipe)),
            )
        if updates:
            conn.execute(
                "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'update', 'drink', ?, ?)",
                (row["location_id"], user["id"], drink_id, str(updates)),
            )
    return {"message": "Đồ uống đã được cập nhật"}


@router.delete("/{drink_id}")
def deactivate_drink(drink_id: int, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT id, name, location_id FROM drinks WHERE id = ?", (drink_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE drinks SET is_active = 0, updated_at = ? WHERE id = ?", (now, drink_id))
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'deactivate', 'drink', ?, ?)",
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
    role = app.storage.user.get("role", "STAFF")
    loc_id = get_current_location_id()

    ui.label("Quản lý đồ uống").classes("text-2xl font-bold mb-4")

    search_input = ui.input("Tìm theo tên đồ uống").props("outlined").classes("w-full mb-4")
    drink_table = ui.table(
        columns=[
            {"name": "name", "label": "Tên đồ uống", "field": "name"},
            {"name": "price", "label": "Giá / ly", "field": "price"},
            {"name": "action", "label": "Thao tác", "field": "action"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    # Recipe dialog
    with ui.dialog() as recipe_dialog, ui.card().classes("p-6 w-full max-w-lg"):
        ui.label("Công thức pha chế").classes("text-xl font-bold mb-4")
        recipe_drink_name = ui.label().classes("text-sm text-gray-500 mb-2")
        recipe_table = ui.table(
            columns=[
                {"name": "ingredient", "label": "Nguyên liệu", "field": "ingredient_name"},
                {"name": "quantity", "label": "Số lượng / ly", "field": "quantity_per_serving"},
                {"name": "unit", "label": "Đơn vị", "field": "unit"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full overflow-x-auto")

        def show_recipe(drink_id: int, drink_name: str):
            recipe_drink_name.set_text(drink_name)
            with get_db() as conn:
                recipe = conn.execute(
                    """SELECT dr.*, i.name as ingredient_name, i.unit
                       FROM drink_recipes dr
                       JOIN ingredients i ON i.id = dr.ingredient_id
                       WHERE dr.drink_id = ?""",
                    (drink_id,),
                ).fetchall()
            recipe_table.rows = [dict(r) for r in recipe]
            recipe_table.update()
            recipe_dialog.open()

        if role in ("MANAGER", "OWNER"):
            with ui.dialog() as edit_recipe_dialog, ui.card().classes("p-6 w-full max-w-lg"):
                ui.label("Sửa công thức").classes("text-xl font-bold mb-4")
                edit_drink_id_label = ui.label().classes("text-sm mb-2")
                recipe_rows = []

                def save_recipe():
                    drink_id_val = getattr(edit_recipe_dialog, "_drink_id", None)
                    if not drink_id_val:
                        return
                    with get_db() as conn:
                        conn.execute("DELETE FROM drink_recipes WHERE drink_id = ?", (drink_id_val,))
                        for item in recipe_rows:
                            ing_id = item["ingredient_select"].value if "ingredient_select" in item else item.get("ingredient_id")
                            qty = item["quantity"].value if "quantity" in item else item.get("quantity_per_serving")
                            if ing_id and qty:
                                conn.execute(
                                    "INSERT INTO drink_recipes (drink_id, ingredient_id, quantity_per_serving) VALUES (?, ?, ?)",
                                    (drink_id_val, ing_id, qty),
                                )
                    edit_recipe_dialog.close()
                    show_recipe(drink_id_val, getattr(edit_recipe_dialog, "_drink_name", ""))
                    ui.notify("Đã cập nhật công thức", type="positive")

                recipe_container = ui.column().classes("w-full mb-4")

                def add_recipe_row():
                    with get_db() as conn:
                        ingredients = conn.execute(
                            "SELECT id, name, unit FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                            (loc_id,),
                        ).fetchall()
                    with recipe_container:
                        with ui.row().classes("w-full items-center gap-2 mb-2"):
                            ing_select = ui.select(
                                {r["id"]: f"{r['name']} ({r['unit']})" for r in ingredients},
                                label="Nguyên liệu",
                            ).props("outlined").classes("flex-1")
                            qty = ui.number("Số lượng / ly", value=1.0).props("outlined").classes("w-32")
                    recipe_rows.append({"ingredient_select": ing_select, "quantity": qty})

                def show_edit_recipe(drink_id: int, drink_name: str):
                    edit_recipe_dialog._drink_id = drink_id
                    edit_recipe_dialog._drink_name = drink_name
                    edit_drink_id_label.set_text(drink_name)
                    recipe_container.clear()
                    recipe_rows.clear()
                    with get_db() as conn:
                        recipe = conn.execute(
                            """SELECT dr.*, i.name as ingredient_name, i.unit
                               FROM drink_recipes dr
                               JOIN ingredients i ON i.id = dr.ingredient_id
                               WHERE dr.drink_id = ?""",
                            (drink_id,),
                        ).fetchall()
                        ingredients = conn.execute(
                            "SELECT id, name, unit FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                            (loc_id,),
                        ).fetchall()
                        ing_options = {r["id"]: f"{r['name']} ({r['unit']})" for r in ingredients}
                    for rec in recipe:
                        with recipe_container:
                            with ui.row().classes("w-full items-center gap-2 mb-2"):
                                ing_select = ui.select(ing_options, label="Nguyên liệu", value=rec["ingredient_id"]).props("outlined").classes("flex-1")
                                qty = ui.number("Số lượng / ly", value=rec["quantity_per_serving"]).props("outlined").classes("w-32")
                        recipe_rows.append({"ingredient_select": ing_select, "quantity": qty})
                    edit_recipe_dialog.open()

                ui.button("Thêm nguyên liệu", on_click=add_recipe_row, icon="add").props("outlined").classes("mb-2")
                ui.button("Lưu công thức", on_click=save_recipe, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    # Create dialog
    if role in ("MANAGER", "OWNER"):
        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Thêm đồ uống").classes("text-xl font-bold mb-4")
            d_name = ui.input("Tên đồ uống *").props("outlined").classes("w-full mb-2")
            d_price = ui.number("Giá / ly (VNĐ)", value=0).props("outlined").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def handle_create():
                if not d_name.value:
                    err.set_text("Vui lòng nhập tên đồ uống")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM drinks WHERE name = ? AND location_id = ?",
                        (d_name.value, loc_id),
                    ).fetchone()
                    if existing:
                        err.set_text("Tên đồ uống đã tồn tại")
                        return
                    conn.execute(
                        "INSERT INTO drinks (location_id, name, price_per_serving, created_by) VALUES (?, ?, ?, ?)",
                        (loc_id, d_name.value, d_price.value or 0, user_id),
                    )
                    conn.execute(
                        "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'create', 'drink', ?, ?)",
                        (loc_id, user_id, conn.lastrowid, f'{{"name":"{d_name.value}"}}'),
                    )
                create_dialog.close()
                refresh()
                ui.notify(f"Đã thêm đồ uống {d_name.value}", type="positive")

            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

        # Edit dialog
        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Sửa đồ uống").classes("text-xl font-bold mb-4")
            e_drink_id = ui.number("e_drink_id").props("hidden")
            e_name = ui.input("Tên đồ uống *").props("outlined").classes("w-full mb-2")
            e_price = ui.number("Giá / ly (VNĐ)", value=0).props("outlined").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def handle_edit():
                if not e_name.value:
                    edit_err.set_text("Vui lòng nhập tên đồ uống")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM drinks WHERE name = ? AND location_id = ? AND id != ?",
                        (e_name.value, loc_id, int(e_drink_id.value or 0)),
                    ).fetchone()
                    if existing:
                        edit_err.set_text("Tên đồ uống đã tồn tại")
                        return
                    conn.execute(
                        "UPDATE drinks SET name = ?, price_per_serving = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                        (e_name.value, e_price.value or 0, int(e_drink_id.value or 0)),
                    )
                    conn.execute(
                        "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'update', 'drink', ?, ?)",
                        (loc_id, user_id, int(e_drink_id.value or 0), f'{{"name":"{e_name.value}","price":{e_price.value or 0}}}'),
                    )
                edit_dialog.close()
                refresh()
                ui.notify("Đã cập nhật đồ uống", type="positive")

            def open_edit(drink: dict):
                e_drink_id.value = drink["id"]
                e_name.value = drink.get("name", "")
                e_price.value = drink.get("price_raw", 0)
                edit_err.set_text("")
                edit_dialog.open()

            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    # Refresh & buttons
    def refresh():
        with get_db() as conn:
            search = search_input.value
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    "SELECT id, name, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? AND name LIKE ? ORDER BY name",
                    (loc_id, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
                    (loc_id,),
                ).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "name": r["name"],
                "price": f"{r['price_per_serving']:,.0f}đ",
                "price_raw": r["price_per_serving"],
                "action": r["id"],
            })
        drink_table.rows = result
        drink_table.update()
        drink_options.clear()
        drink_options.update({r["id"]: r["name"] for r in rows})

    search_input.on("keyup.enter", refresh)

    with ui.row().classes("gap-2 mb-4"):
        if role in ("MANAGER", "OWNER"):
            ui.button("Thêm đồ uống", on_click=create_dialog.open, icon="add").props("unelevated").classes("bg-green-600 text-white")
        ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

    # Action column slot
    drink_table.add_slot(
        "body-cell-action",
        """
        <q-td :props="props">
            <div class="flex gap-1">
                <q-btn flat dense size="sm" color="primary" icon="visibility" @click="$parent.$emit('view_recipe', props.row)">
                    <q-tooltip>Xem công thức</q-tooltip>
                </q-btn>
            </div>
        </q-td>
        """,
    )
    drink_table.on("view_recipe", lambda e: show_recipe(e.args["id"], e.args["name"]))

    if role in ("MANAGER", "OWNER"):
        drink_table.add_slot(
            "body-cell-action",
            """
            <q-td :props="props">
                <div class="flex gap-1">
                    <q-btn flat dense size="sm" color="primary" icon="visibility" @click="$parent.$emit('view_recipe', props.row)">
                        <q-tooltip>Xem công thức</q-tooltip>
                    </q-btn>
                    <q-btn flat dense size="sm" color="warning" icon="edit" @click="$parent.$emit('edit_drink', props.row)">
                        <q-tooltip>Sửa đồ uống</q-tooltip>
                    </q-btn>
                    <q-btn flat dense size="sm" color="secondary" icon="menu_book" @click="$parent.$emit('edit_recipe', props.row)">
                        <q-tooltip>Sửa công thức</q-tooltip>
                    </q-btn>
                </div>
            </q-td>
            """,
        )
        drink_table.on("view_recipe", lambda e: show_recipe(e.args["id"], e.args["name"]))
        drink_table.on("edit_drink", lambda e: open_edit(e.args))
        drink_table.on("edit_recipe", lambda e: show_edit_recipe(e.args["id"], e.args["name"]))

    # Drink selector dropdown
    with ui.row().classes("w-full items-end gap-2 mt-4 flex-wrap"):
        drink_options = {}
        ui.label("Xem công thức:").classes("text-sm font-bold")
        with get_db() as conn:
            all_drinks = conn.execute(
                "SELECT id, name FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
                (loc_id,),
            ).fetchall()
        drink_options = {r["id"]: r["name"] for r in all_drinks}
        selected_drink = ui.select(drink_options, label="Chọn đồ uống").props("outlined").classes("w-64")
        if drink_options:
            first_id = list(drink_options.keys())[0]
            selected_drink.set_value(first_id)
        ui.button("Xem", on_click=lambda: show_recipe(selected_drink.value, drink_options.get(selected_drink.value, "")), icon="visibility").props("outlined")

    refresh()