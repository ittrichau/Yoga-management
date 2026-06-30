"""Drink management - location-filtered."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/drinks", tags=["drinks"])

class DrinkCreate(BaseModel):
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
def create_drink(data: DrinkCreate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO drinks (location_id, name, price, description, recipe, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (data.get("location_id"), data.name, data.price, data.description, data.recipe, user["id"]),
        )
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'drink', ?, ?)""",
            (data.get("location_id"), user["id"], cur.lastrowid, f'{{"name":"{data.name}","price":{data.price}}}'),
        )
    return {"id": cur.lastrowid, "message": "Đồ uống đã được tạo"}


@router.put("/{drink_id}")
def update_drink(drink_id: int, data: DrinkUpdate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drinks WHERE id = ?", (drink_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        updates = {}
        for field in ["name", "price", "description", "recipe"]:
            val = getattr(data, field)
            if val is not None:
                updates[field] = val
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
def soft_delete_drink(drink_id: int, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drinks WHERE id = ? AND is_active = 1", (drink_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đồ uống")
        conn.execute("UPDATE drinks SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?", (drink_id,))
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'soft_delete', 'drink', ?, ?)""",
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

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("🥤").classes("text-2xl")
            ui.label("Quản lý đồ uống")

        # ── Search + Add ──
        with ui.element("div").classes("search-bar"):
            search_input = ui.input("Tìm kiếm đồ uống").props("outlined clearable dense").classes("flex-grow")
            ui.button("Tìm", icon="search", on_click=refresh).props("outlined")
            if role in ("MANAGER", "OWNER"):
                ui.button("Thêm đồ uống", icon="add", on_click=create_dialog.open).props("unelevated").classes("btn-success")

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

        def refresh():
            search = search_input.value or ""
            with get_db() as conn:
                if search:
                    like = f"%{search}%"
                    rows = conn.execute(
                        "SELECT id, name, price, description FROM drinks WHERE is_active = 1 AND location_id = ? AND name LIKE ? ORDER BY name",
                        (loc_id, like),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, name, price, description FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
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

        # Create dialog
        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Thêm đồ uống").classes("text-xl font-bold mb-4")
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
                    conn.execute(
                        """INSERT INTO drinks (location_id, name, price, description, recipe, created_by)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (loc_id, d_name.value, d_price.value, d_desc.value, d_recipe.value, user_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'create', 'drink', ?, ?)""",
                        (loc_id, user_id, conn.lastrowid, f'{{"name":"{d_name.value}","price":{d_price.value}}}'),
                    )
                create_dialog.close()
                refresh()
                ui.notify("Đã thêm đồ uống", type="positive")

            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary w-full mt-2")

        # Edit dialog
        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Sửa đồ uống").classes("text-xl font-bold mb-4")
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
                        "UPDATE drinks SET name = ?, price = ?, description = ?, recipe = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                        (e_name.value, e_price.value, e_desc.value, e_recipe.value, int(edit_id.value or 0)),
                    )
                edit_dialog.close()
                refresh()
                ui.notify("Đã cập nhật đồ uống", type="positive")

            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary w-full mt-2")

        if role in ("MANAGER", "OWNER"):
            with ui.row().classes("gap-2 mb-4"):
                ui.button("Thêm đồ uống", on_click=create_dialog.open, icon="add").props("unelevated").classes("btn-success")
                ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

        search_input.on("keyup.enter", refresh)

        drink_table.add_slot(
            "body-cell-action",
            """
            <q-td :props="props">
                <q-btn flat color="primary" icon="edit" @click="$parent.$emit('edit_drink', props.row)">
                    <q-tooltip>Sửa</q-tooltip>
                </q-btn>
            </q-td>
            """,
        )
        drink_table.on("edit_drink", lambda e: open_edit(e.args))

        refresh()