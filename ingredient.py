"""Ingredient inventory management - filtered by location."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])

class IngredientCreate(BaseModel):
    name: str
    unit: str = "muỗng"
    current_stock: float = 0
    min_stock: float = 0
    location_id: int | None = None

class IngredientUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    min_stock: float | None = None

class InventoryAdjust(BaseModel):
    ingredient_id: int
    adjustment_type: str
    quantity: float
    reason: str = ""

class CountCorrect(BaseModel):
    ingredient_id: int
    actual_stock: float
    reason: str = ""


@router.get("")
def list_ingredients(search: str = "", location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            if location_id:
                rows = conn.execute(
                    "SELECT id, name, unit, current_stock, min_stock, is_active, created_at, location_id FROM ingredients WHERE is_active = 1 AND location_id = ? AND name LIKE ? ORDER BY name",
                    (location_id, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, unit, current_stock, min_stock, is_active, created_at, location_id FROM ingredients WHERE is_active = 1 AND name LIKE ? ORDER BY name",
                    (like,),
                ).fetchall()
        else:
            if location_id:
                rows = conn.execute(
                    "SELECT id, name, unit, current_stock, min_stock, is_active, created_at, location_id FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                    (location_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, unit, current_stock, min_stock, is_active, created_at, location_id FROM ingredients WHERE is_active = 1 ORDER BY name"
                ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{ingredient_id}")
def get_ingredient(ingredient_id: int, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
    return dict(row)


@router.post("", status_code=201)
def create_ingredient(data: IngredientCreate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM ingredients WHERE name = ? AND location_id = ?", (data.name, data.location_id)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Tên nguyên liệu đã tồn tại tại cơ sở này")
        if data.unit not in ("muỗng", "nắp", "gói"):
            raise HTTPException(status_code=400, detail="Đơn vị không hợp lệ. Phải là: muỗng, nắp, gói")
        cur = conn.execute(
            "INSERT INTO ingredients (location_id, name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (data.location_id, data.name, data.unit, data.current_stock, data.min_stock, user["id"]),
        )
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'create', 'ingredient', ?, ?)",
            (data.location_id, user["id"], cur.lastrowid, f'{{"name":"{data.name}","unit":"{data.unit}","stock":{data.current_stock}}}'),
        )
    return {"id": cur.lastrowid, "message": "Nguyên liệu đã được tạo"}


@router.put("/{ingredient_id}")
def update_ingredient(ingredient_id: int, data: IngredientUpdate, user: dict = Depends(require_role("MANAGER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
        updates = {}
        if data.name is not None:
            existing = conn.execute(
                "SELECT id FROM ingredients WHERE name = ? AND location_id = ? AND id != ?",
                (data.name, row["location_id"], ingredient_id),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Tên nguyên liệu đã tồn tại")
            updates["name"] = data.name
        if data.unit is not None:
            if data.unit not in ("muỗng", "nắp", "gói"):
                raise HTTPException(status_code=400, detail="Đơn vị không hợp lệ")
            updates["unit"] = data.unit
        if data.min_stock is not None:
            updates["min_stock"] = data.min_stock
        if not updates:
            return {"message": "Không có thay đổi"}
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [ingredient_id]
        conn.execute(f"UPDATE ingredients SET {set_clause} WHERE id = ?", values)
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'update', 'ingredient', ?, ?)",
            (row["location_id"], user["id"], ingredient_id, str(updates)),
        )
    return {"message": "Nguyên liệu đã được cập nhật"}


@router.delete("/{ingredient_id}")
def deactivate_ingredient(ingredient_id: int, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT id, name, location_id FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE ingredients SET is_active = 0, updated_at = ? WHERE id = ?", (now, ingredient_id))
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'deactivate', 'ingredient', ?, ?)",
            (row["location_id"], user["id"], ingredient_id, f'{{"name":"{row["name"]}"}}'),
        )
    return {"message": "Nguyên liệu đã bị vô hiệu hóa"}


# Inventory endpoints
@router.get("/inventory/products")
def list_inventory(location_id: int | None = None, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if location_id:
            rows = conn.execute(
                "SELECT id, name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                (location_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 ORDER BY name"
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/inventory/adjustments")
def list_adjustments(ingredient_id: int | None = None, location_id: int | None = None, limit: int = 50, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        where = []
        params = []
        if ingredient_id:
            where.append("ia.ingredient_id = ?")
            params.append(ingredient_id)
        if location_id:
            where.append("ia.location_id = ?")
            params.append(location_id)
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT ia.*, i.name as ingredient_name, i.unit, u.full_name as user_name
                FROM inventory_adjustments ia
                JOIN ingredients i ON i.id = ia.ingredient_id
                JOIN users u ON u.id = ia.created_by
                {where_clause}
                ORDER BY ia.created_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/inventory/adjust")
def adjust_inventory(data: InventoryAdjust, user: dict = Depends(require_role("OWNER"))):
    if data.adjustment_type not in ("add", "remove", "count_correct"):
        raise HTTPException(status_code=400, detail="Loại điều chỉnh không hợp lệ")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ingredients WHERE id = ? AND is_active = 1", (data.ingredient_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
        loc_id = row["location_id"]
        if data.adjustment_type == "add":
            new_stock = row["current_stock"] + data.quantity
        elif data.adjustment_type == "remove":
            new_stock = row["current_stock"] - data.quantity
            if new_stock < 0:
                raise HTTPException(status_code=400, detail="Không đủ tồn kho")
        else:
            new_stock = data.quantity
        conn.execute(
            "UPDATE ingredients SET current_stock = ?, updated_at = ? WHERE id = ?",
            (new_stock, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), data.ingredient_id),
        )
        conn.execute(
            "INSERT INTO inventory_adjustments (location_id, ingredient_id, adjustment_type, quantity, reason, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (loc_id, data.ingredient_id, data.adjustment_type, data.quantity, data.reason, user["id"]),
        )
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'inventory_adjust', 'ingredient', ?, ?)",
            (loc_id, user["id"], data.ingredient_id, f'{{"type":"{data.adjustment_type}","qty":{data.quantity},"old":{row["current_stock"]},"new":{new_stock}}}'),
        )
    return {"message": "Đã điều chỉnh tồn kho", "new_stock": new_stock}


@router.post("/inventory/count-correct")
def count_correct_inventory(data: CountCorrect, user: dict = Depends(require_role("OWNER"))):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ingredients WHERE id = ? AND is_active = 1", (data.ingredient_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy nguyên liệu")
        loc_id = row["location_id"]
        old_stock = row["current_stock"]
        conn.execute(
            "UPDATE ingredients SET current_stock = ?, updated_at = ? WHERE id = ?",
            (data.actual_stock, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), data.ingredient_id),
        )
        diff = data.actual_stock - old_stock
        conn.execute(
            "INSERT INTO inventory_adjustments (location_id, ingredient_id, adjustment_type, quantity, reason, created_by) VALUES (?, ?, 'count_correct', ?, ?, ?)",
            (loc_id, data.ingredient_id, abs(diff), data.reason, user["id"]),
        )
        conn.execute(
            "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'inventory_adjust', 'ingredient', ?, ?)",
            (loc_id, user["id"], data.ingredient_id, f'{{"type":"count_correct","old":{old_stock},"new":{data.actual_stock},"diff":{diff}}}'),
        )
    return {"message": "Đã kiểm kê", "new_stock": data.actual_stock}


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

    ui.label("Quản lý nguyên liệu").classes("text-2xl font-bold mb-4")

    search_input = ui.input("Tìm theo tên nguyên liệu").props("outlined").classes("w-full mb-4")
    ingredient_table = ui.table(
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
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            search = search_input.value
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
            if r["current_stock"] <= r["min_stock"]:
                status = "⚠️ Thiếu"
            elif r["current_stock"] <= r["min_stock"] * 2:
                status = "⚠️ Cảnh báo"
            else:
                status = "✅ OK"
            result.append({
                "id": r["id"],
                "name": r["name"],
                "unit": r["unit"],
                "stock": f"{r['current_stock']:.1f}",
                "stock_raw": r["current_stock"],
                "min": f"{r['min_stock']:.1f}",
                "min_raw": r["min_stock"],
                "status": status,
                "action": r["id"],
            })
        ingredient_table.rows = result
        ingredient_table.update()

    # Create dialog
    if role in ("MANAGER", "OWNER"):
        with ui.dialog() as create_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Thêm nguyên liệu").classes("text-xl font-bold mb-4")
            i_name = ui.input("Tên nguyên liệu *").props("outlined").classes("w-full mb-2")
            i_unit = ui.select(["muỗng", "nắp", "gói"], label="Đơn vị *", value="muỗng").props("outlined").classes("w-full mb-2")
            i_stock = ui.number("Tồn kho ban đầu", value=0).props("outlined").classes("w-full mb-2")
            i_min = ui.number("Tồn kho tối thiểu", value=0).props("outlined").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def handle_create():
                if not i_name.value:
                    err.set_text("Vui lòng nhập tên nguyên liệu")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM ingredients WHERE name = ? AND location_id = ?",
                        (i_name.value, loc_id),
                    ).fetchone()
                    if existing:
                        err.set_text("Tên nguyên liệu đã tồn tại")
                        return
                    conn.execute(
                        "INSERT INTO ingredients (location_id, name, unit, current_stock, min_stock, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                        (loc_id, i_name.value, i_unit.value, i_stock.value or 0, i_min.value or 0, user_id),
                    )
                    conn.execute(
                        "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'create', 'ingredient', ?, ?)",
                        (loc_id, user_id, conn.lastrowid, f'{{"name":"{i_name.value}","unit":"{i_unit.value}","stock":{i_stock.value or 0}}}'),
                    )
                create_dialog.close()
                refresh()
                ui.notify(f"Đã thêm nguyên liệu {i_name.value}", type="positive")

            ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

        # Edit dialog
        with ui.dialog() as edit_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Sửa nguyên liệu").classes("text-xl font-bold mb-4")
            e_ing_id = ui.number("e_ing_id").props("hidden")
            e_name = ui.input("Tên nguyên liệu *").props("outlined").classes("w-full mb-2")
            e_unit = ui.select(["muỗng", "nắp", "gói"], label="Đơn vị *").props("outlined").classes("w-full mb-2")
            e_min = ui.number("Tồn kho tối thiểu", value=0).props("outlined").classes("w-full mb-4")
            edit_err = ui.label().classes("text-red-500 text-sm")

            def handle_edit():
                if not e_name.value:
                    edit_err.set_text("Vui lòng nhập tên nguyên liệu")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM ingredients WHERE name = ? AND location_id = ? AND id != ?",
                        (e_name.value, loc_id, int(e_ing_id.value or 0)),
                    ).fetchone()
                    if existing:
                        edit_err.set_text("Tên nguyên liệu đã tồn tại")
                        return
                    conn.execute(
                        "UPDATE ingredients SET name = ?, unit = ?, min_stock = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                        (e_name.value, e_unit.value, e_min.value or 0, int(e_ing_id.value or 0)),
                    )
                    conn.execute(
                        "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'update', 'ingredient', ?, ?)",
                        (loc_id, user_id, int(e_ing_id.value or 0), f'{{"name":"{e_name.value}","unit":"{e_unit.value}","min_stock":{e_min.value or 0}}}'),
                    )
                edit_dialog.close()
                refresh()
                ui.notify("Đã cập nhật nguyên liệu", type="positive")

            def open_edit(ing: dict):
                e_ing_id.value = ing["id"]
                e_name.value = ing.get("name", "")
                e_unit.value = ing.get("unit", "muỗng")
                e_min.value = ing.get("min_raw", 0)
                edit_err.set_text("")
                edit_dialog.open()

            ui.button("Lưu", on_click=handle_edit, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    # Inventory adjust dialog (OWNER only)
    if role == "OWNER":
        with ui.dialog() as adjust_dialog, ui.card().classes("p-6 w-96"):
            ui.label("Điều chỉnh tồn kho").classes("text-xl font-bold mb-4")
            with get_db() as conn:
                ingredients = conn.execute(
                    "SELECT id, name, unit, current_stock FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
                    (loc_id,),
                ).fetchall()
            ing_map = {r["id"]: f"{r['name']} ({r['current_stock']:.0f} {r['unit']})" for r in ingredients}
            a_ingredient = ui.select(ing_map, label="Nguyên liệu *").props("outlined").classes("w-full mb-2")
            a_type = ui.select(["add", "remove", "count_correct"], label="Loại điều chỉnh *").props("outlined").classes("w-full mb-2")
            a_qty = ui.number("Số lượng", value=0).props("outlined").classes("w-full mb-2")
            a_reason = ui.textarea("Lý do").props("outlined").classes("w-full mb-4")
            err = ui.label().classes("text-red-500 text-sm")

            def handle_adjust():
                if not a_ingredient.value or not a_type.value:
                    err.set_text("Vui lòng chọn nguyên liệu và loại điều chỉnh")
                    return
                user_id = app.storage.user.get("user_id", 1)
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (a_ingredient.value,)).fetchone()
                    if row is None:
                        err.set_text("Nguyên liệu không tồn tại")
                        return
                    if a_type.value == "add":
                        new_stock = row["current_stock"] + (a_qty.value or 0)
                    elif a_type.value == "remove":
                        new_stock = row["current_stock"] - (a_qty.value or 0)
                        if new_stock < 0:
                            err.set_text("Không đủ tồn kho để trừ")
                            return
                    else:
                        new_stock = a_qty.value or 0
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute("UPDATE ingredients SET current_stock = ?, updated_at = ? WHERE id = ?", (new_stock, now, a_ingredient.value))
                    conn.execute(
                        "INSERT INTO inventory_adjustments (location_id, ingredient_id, adjustment_type, quantity, reason, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                        (loc_id, a_ingredient.value, a_type.value, abs(a_qty.value or 0), a_reason.value, user_id),
                    )
                    conn.execute(
                        "INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details) VALUES (?, ?, 'inventory_adjust', 'ingredient', ?, ?)",
                        (loc_id, user_id, a_ingredient.value, f'{{"type":"{a_type.value}","qty":{abs(a_qty.value or 0)},"old":{row["current_stock"]},"new":{new_stock},"reason":"{a_reason.value}"}}'),
                    )
                adjust_dialog.close()
                refresh()
                ui.notify("Đã điều chỉnh tồn kho thành công", type="positive")

            ui.button("Lưu", on_click=handle_adjust, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    with ui.row().classes("gap-2 mb-4"):
        if role in ("MANAGER", "OWNER"):
            ui.button("Thêm nguyên liệu", on_click=create_dialog.open, icon="add").props("unelevated").classes("bg-green-600 text-white")
        if role == "OWNER":
            ui.button("Điều chỉnh tồn kho", on_click=adjust_dialog.open, icon="inventory").props("unelevated").classes("bg-orange-600 text-white")
        ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")

    search_input.on("keyup.enter", refresh)

    # Adjustment history dialog
    with ui.dialog() as history_dialog, ui.card().classes("p-6 w-full max-w-2xl"):
        ui.label("Lịch sử điều chỉnh").classes("text-xl font-bold mb-4")
        history_table = ui.table(
            columns=[
                {"name": "date", "label": "Ngày", "field": "date"},
                {"name": "ingredient", "label": "Nguyên liệu", "field": "ingredient"},
                {"name": "type", "label": "Loại", "field": "type"},
                {"name": "qty", "label": "Số lượng", "field": "qty"},
                {"name": "reason", "label": "Lý do", "field": "reason"},
                {"name": "by", "label": "Người thực hiện", "field": "by"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full overflow-x-auto")

        def show_history():
            with get_db() as conn:
                rows = conn.execute(
                    """SELECT ia.*, i.name as ingredient_name, i.unit, u.full_name as user_name
                       FROM inventory_adjustments ia
                       JOIN ingredients i ON i.id = ia.ingredient_id
                       JOIN users u ON u.id = ia.created_by
                       WHERE ia.location_id = ?
                       ORDER BY ia.created_at DESC LIMIT 50""",
                    (loc_id,),
                ).fetchall()
            type_labels = {"add": "Thêm", "remove": "Bớt", "count_correct": "Kiểm kê"}
            history_table.rows = [
                {
                    "id": r["id"],
                    "date": r["created_at"][:19],
                    "ingredient": r["ingredient_name"],
                    "type": type_labels.get(r["adjustment_type"], r["adjustment_type"]),
                    "qty": f"{r['quantity']:.1f} {r['unit']}",
                    "reason": r["reason"],
                    "by": r["user_name"],
                }
                for r in rows
            ]
            history_table.update()
            history_dialog.open()

    ui.button("Lịch sử điều chỉnh", on_click=show_history, icon="history").props("outlined").classes("mb-4")

    if role in ("MANAGER", "OWNER"):
        ingredient_table.add_slot(
            "body-cell-action",
            """
            <q-td :props="props">
                <q-btn flat dense size="sm" color="warning" icon="edit" @click="$parent.$emit('edit_ingredient', props.row)">
                    <q-tooltip>Sửa</q-tooltip>
                </q-btn>
            </q-td>
            """,
        )
        ingredient_table.on("edit_ingredient", lambda e: open_edit(e.args))

    refresh()