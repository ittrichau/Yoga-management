"""Ingredient/stock management - location-filtered."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])

class IngredientCreate(BaseModel):
    location_id: int | None = None
    name: str
    unit: str = ""
    current_stock: float = 0.0
    min_stock: float = 0.0

class IngredientUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    min_stock: float | None = None

class StockAdjust(BaseModel):
    quantity: float
    reason: str = ""


@router.get("")
def list_ingredients(location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if location_id:
            rows = conn.execute(
                "SELECT * FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                (location_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ingredients WHERE is_active = 1 ORDER BY name"
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_ingredient(data: IngredientCreate, user: dict = Depends(require_role("MANAGER"))):
    location_id = data.location_id or user.get("location_id")
    if not location_id:
        raise HTTPException(status_code=400, detail="Chưa chọn chi nhánh")

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO ingredients (location_id, name, unit, current_stock, min_stock, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (location_id, data.name, data.unit, data.current_stock, data.min_stock, user["id"]),
        )
        ingredient_id = cur.lastrowid
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'ingredient', ?, ?)""",
            (location_id, user["id"], ingredient_id, f'{{"name":"{data.name}","stock":{data.current_stock}}}'),
        )
    return {"id": ingredient_id, "message": "Nguyên liệu đã được tạo"}


@router.put("/{ingredient_id}")
def update_ingredient(ingredient_id: int, data: IngredientUpdate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
        updates = {}
        for field in ["name", "unit", "min_stock"]:
            val = getattr(data, field)
            if val is not None:
                updates[field] = val
        if not updates:
            return {"message": "Không có thay đổi"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [ingredient_id]
        conn.execute(f"UPDATE ingredients SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'update', 'ingredient', ?, ?)""",
            (row["location_id"], user["id"], ingredient_id, str(updates)),
        )
    return {"message": "Nguyên liệu đã được cập nhật"}


@router.post("/{ingredient_id}/adjust")
def adjust_stock(ingredient_id: int, data: StockAdjust, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ingredients WHERE id = ? AND is_active = 1", (ingredient_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
        new_stock = row["current_stock"] + data.quantity
        if new_stock < 0:
            raise HTTPException(status_code=400, detail="Tồn kho không thể âm")
        conn.execute(
            "UPDATE ingredients SET current_stock = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (new_stock, ingredient_id),
        )
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'adjust_stock', 'ingredient', ?, ?)""",
        (row["location_id"], user["id"], ingredient_id,
         f'{{"name":"{row["name"]}","old":{row["current_stock"]},"adjust":{data.quantity},"new":{new_stock},"reason":"{data.reason}"}}'),
        )
    return {"message": f"Đã điều chỉnh tồn kho {data.quantity:+.1f}", "new_stock": new_stock}


# ==================== NiceGUI UI ====================
@ui.page("/ingredients")
def ingredients_page():
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

    # Helper defined first so on_click callbacks can reference it.
    # Widgets (search_input, ing_table) are resolved at call time via closure.
    def refresh():
        search = search_input.value or ""
        with get_db() as conn:
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    "SELECT id, name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND location_id = ? AND name LIKE ? ORDER BY name",
                    (loc_id, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                    (loc_id,),
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["stock"] = f"{r['current_stock']:.1f}"
            d["min"] = f"{r['min_stock']:.1f}"
            if r["current_stock"] <= r["min_stock"]:
                d["status"] = '<span class="status-chip danger">THIẾU</span>'
            elif r["current_stock"] <= r["min_stock"] * 2:
                d["status"] = '<span class="status-chip warning">Cảnh báo</span>'
            else:
                d["status"] = '<span class="status-chip ok">OK</span>'
            d["action"] = d["id"]
            result.append(d)
        ing_table.rows = result
        ing_table.update()

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("🧪").classes("text-2xl")
            ui.label("Quản lý nguyên liệu")

        # ── Search + Add ──
        with ui.element("div").classes("search-bar"):
            search_input = ui.input("Tìm kiếm nguyên liệu").props("outlined clearable dense").classes("flex-grow")
            ui.button("Tìm", icon="search", on_click=refresh).props("outlined")
            if role in ("MANAGER", "OWNER"):
                ui.button("Thêm nguyên liệu", icon="add", on_click=lambda: create_dialog.open()).props("unelevated").classes("btn-success")

        ing_table = ui.table(
            columns=[
                {"name": "name", "label": "Tên nguyên liệu", "field": "name"},
                {"name": "unit", "label": "Đơn vị", "field": "unit"},
                {"name": "stock", "label": "Tồn kho", "field": "stock"},
                {"name": "min", "label": "Tối thiểu", "field": "min"},
                {"name": "status", "label": "Trạng thái", "field": "status"},
                {"name": "action", "label": "Thao tác", "field": "action"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

        # Create dialog
        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96 relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=create_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Thêm nguyên liệu").classes("text-xl font-bold mb-4 pr-8")
            i_name = ui.input("Tên nguyên liệu *").props("outlined dense").classes("w-full mb-2")
            i_unit = ui.input("Đơn vị (vd: kg, lít, gói)").props("outlined dense").classes("w-full mb-2")
            i_stock = ui.number("Tồn kho ban đầu", value=0, format="%.1f").props("outlined dense").classes("w-full mb-2")
            i_min = ui.number("Tồn kho tối thiểu", value=0, format="%.1f").props("outlined dense").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def handle_create():
                if not i_name.value:
                    err.set_text("Vui lòng nhập tên nguyên liệu")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                                    cur = conn.execute(
                                        """INSERT INTO ingredients (location_id, name, unit, current_stock, min_stock, created_by)
                                           VALUES (?, ?, ?, ?, ?, ?)""",
                                        (loc_id, i_name.value, i_unit.value or "", i_stock.value or 0, i_min.value or 0, user_id),
                                    )
                                    ingredient_id = cur.lastrowid
                                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'create', 'ingredient', ?, ?)""",
                        (loc_id, user_id, ingredient_id, f'{{"name":"{i_name.value}","stock":{i_stock.value or 0}}}'),
                    )
                create_dialog.close()
                refresh()
                ui.notify("Đã thêm nguyên liệu", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=create_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("btn-primary")

        # Edit dialog
        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96 relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=edit_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Sửa nguyên liệu").classes("text-xl font-bold mb-4 pr-8")
            edit_id = ui.number("edit_id").props("hidden")
            e_name = ui.input("Tên nguyên liệu *").props("outlined dense").classes("w-full mb-2")
            e_unit = ui.input("Đơn vị").props("outlined dense").classes("w-full mb-2")
            e_min = ui.number("Tồn kho tối thiểu", value=0, format="%.1f").props("outlined dense").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def handle_edit():
                if not e_name.value:
                    edit_err.set_text("Vui lòng nhập tên nguyên liệu")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    conn.execute(
                        "UPDATE ingredients SET name = ?, unit = ?, min_stock = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                        (e_name.value, e_unit.value or "", e_min.value or 0, int(edit_id.value or 0)),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'update', 'ingredient', ?, ?)""",
                        (loc_id, user_id, int(edit_id.value or 0), f'{{"name":"{e_name.value}","unit":"{e_unit.value or ""}","min_stock":{e_min.value or 0}}}'),
                    )
                edit_dialog.close()
                refresh()
                ui.notify("Đã cập nhật nguyên liệu", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=edit_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("btn-primary")

        # Adjust stock dialog (OWNER only)
        with ui.dialog() as adjust_dialog, ui.card().classes("p-6 w-96 relative"):
            with ui.element("div").classes("absolute top-2 right-2"):
                ui.button(icon="close", on_click=adjust_dialog.close).props("flat round dense").tooltip("Đóng")
            ui.label("Điều chỉnh tồn kho").classes("text-xl font-bold mb-4 pr-8")
            adj_id = ui.number("adj_id").props("hidden")
            adj_label = ui.label().classes("text-sm font-bold mb-2")
            adj_current = ui.label().classes("text-sm text-gray-500 mb-2")
            adj_qty = ui.number("Số lượng (+: thêm, -: bớt)", value=0, format="%.1f").props("outlined dense").classes("w-full mb-2")
            adj_reason = ui.textarea("Lý do").props("outlined dense").classes("w-full mb-4")
            adj_err = ui.label().classes("text-red-500 text-sm")

            def handle_adjust():
                user_id = app.storage.user.get("user_id", 1)
                ing_id = int(adj_id.value or 0)
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ing_id,)).fetchone()
                    if not row:
                        adj_err.set_text("Không tìm thấy nguyên liệu")
                        return
                    new_stock = row["current_stock"] + (adj_qty.value or 0)
                    if new_stock < 0:
                        adj_err.set_text("Tồn kho không thể âm")
                        return
                    conn.execute("UPDATE ingredients SET current_stock = ?, updated_at = datetime('now','localtime') WHERE id = ?", (new_stock, ing_id))
                    conn.execute(
                        """INSERT INTO inventory_adjustments (location_id, ingredient_id, adjustment_type, quantity, reason, created_by)
                           VALUES (?, ?, 'add', ?, ?, ?)""",
                        (loc_id, ing_id, adj_qty.value or 0, adj_reason.value or "", user_id),
                    )
                    conn.execute(
                        """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                           VALUES (?, ?, 'adjust_stock', 'ingredient', ?, ?)""",
                        (loc_id, user_id, ing_id, f'{{"old":{row["current_stock"]},"adjust":{adj_qty.value or 0},"new":{new_stock},"reason":"{adj_reason.value or ""}"}}'),
                    )
                adjust_dialog.close()
                refresh()
                ui.notify(f"Đã điều chỉnh tồn kho {(adj_qty.value or 0):+.1f}", type="positive")

            with ui.row().classes("gap-2 justify-end w-full mt-2"):
                ui.button("Đóng", on_click=adjust_dialog.close, icon="close").props("outlined")
                ui.button("Lưu", on_click=handle_adjust, icon="save").props("unelevated").classes("btn-primary")

        def open_edit(row):
            edit_id.value = row.get("id") or row.get("action")
            e_name.value = row.get("name", "")
            e_unit.value = row.get("unit", "")
            try:
                e_min.value = float(row.get("min", 0))
            except (TypeError, ValueError):
                e_min.value = 0
            edit_err.set_text("")
            edit_dialog.open()

        def open_adjust(row):
            ing_id = row.get("id") or row.get("action")
            adj_id.value = ing_id
            adj_label.set_text(f"Nguyên liệu: {row.get('name', '')}")
            adj_current.set_text(f"Tồn kho hiện tại: {row.get('stock', 0)}")
            adj_qty.value = 0
            adj_reason.value = ""
            adj_err.set_text("")
            adjust_dialog.open()

        with ui.row().classes("gap-2 mb-4"):
            if role in ("MANAGER", "OWNER"):
                ui.button("Thêm nguyên liệu", on_click=create_dialog.open, icon="add").props("unelevated").classes("btn-success")
            ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

        search_input.on("keyup.enter", refresh)

        if role == "OWNER":
            ing_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit_ing', props.row)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense color="warning" icon="tune" @click="$parent.$emit('adjust_ing', props.row)">
                        <q-tooltip>Điều chỉnh kho</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
        else:
            ing_table.add_slot(
                "body-cell-action",
                """
                <q-td :props="props">
                    <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit_ing', props.row)">
                        <q-tooltip>Sửa</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
        ing_table.on("edit_ing", lambda e: open_edit(e.args))
        ing_table.on("adjust_ing", lambda e: open_adjust(e.args))

        refresh()
