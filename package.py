"""Prepaid package management - filtered by location."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/packages", tags=["packages"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class PackageCreate(BaseModel):
    customer_id: int
    name: str = ""
    total_amount: float = 0
    items: list[dict] = []  # [{drink_id: int, total_servings: float}]
    package_template_id: int | None = None
    duration_days: int = 0
    start_date: str | None = None
    total_sessions: int = 0

class PackageItemAdd(BaseModel):
    drink_id: int
    total_servings: float


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@router.get("")
def list_packages(customer_id: int | None = None, location_id: int | None = None, user: dict = Depends(get_current_user)):
    """List active packages with optional customer filter and location."""
    with get_db() as conn:
        where = "WHERE p.is_active = 1"
        params = []
        if customer_id:
            where += " AND p.customer_id = ?"
            params.append(customer_id)
        if location_id:
            where += " AND p.location_id = ?"
            params.append(location_id)
        rows = conn.execute(
            f"""SELECT p.*, c.full_name as customer_name, c.code as customer_code
                FROM packages p
                JOIN customers c ON c.id = p.customer_id
                {where}
                ORDER BY p.created_at DESC""",
            params,
        ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        with get_db() as conn:
            items = conn.execute(
                """SELECT pi.*, d.name as drink_name
                   FROM package_items pi
                   JOIN drinks d ON d.id = pi.drink_id
                   WHERE pi.package_id = ?""",
                (r["id"],),
            ).fetchall()
        d["items"] = [dict(item) for item in items]
        results.append(d)
    return results


@router.get("/{package_id}")
def get_package(package_id: int, user: dict = Depends(get_current_user)):
    """Get package details with items."""
    with get_db() as conn:
        pkg = conn.execute(
            """SELECT p.*, c.full_name as customer_name, c.code as customer_code
               FROM packages p
               JOIN customers c ON c.id = p.customer_id
               WHERE p.id = ?""",
            (package_id,),
        ).fetchone()
        if pkg is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy gói")
        items = conn.execute(
            """SELECT pi.*, d.name as drink_name
               FROM package_items pi
               JOIN drinks d ON d.id = pi.drink_id
               WHERE pi.package_id = ?""",
            (package_id,),
        ).fetchall()
    result = dict(pkg)
    result["items"] = [dict(item) for item in items]
    return result


@router.post("", status_code=201)
def create_package(data: PackageCreate, user: dict = Depends(get_current_user)):
    """Create a new prepaid package. Any authenticated user can create."""
    with get_db() as conn:
        customer = conn.execute("SELECT id, location_id FROM customers WHERE id = ? AND is_active = 1", (data.customer_id,)).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng hoặc đã bị vô hiệu hóa")
        loc_id = customer["location_id"]

        # Resolve template to compute start_date, end_date, total_sessions
        template = None
        total_sessions = data.total_sessions or 0
        duration_days = data.duration_days or 0
        total_drinks = sum(item.get("total_servings", 0) for item in data.items)
        if data.package_template_id:
            template = conn.execute(
                "SELECT * FROM package_templates WHERE id = ? AND location_id = ?",
                (data.package_template_id, loc_id),
            ).fetchone()
            if template is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy mẫu gói")
            total_sessions = template["total_sessions"]
            duration_days = template["duration_days"]
            total_drinks = template["total_drinks"]

        start_date = data.start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_date = None
        if duration_days > 0:
            from datetime import timedelta
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = (sd + timedelta(days=duration_days)).strftime("%Y-%m-%d")

        cur = conn.execute(
            """INSERT INTO packages
               (location_id, customer_id, name, total_amount,
                package_template_id, duration_days, start_date, end_date,
                total_sessions, remaining_sessions, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (loc_id, data.customer_id, data.name, data.total_amount,
             data.package_template_id, duration_days, start_date, end_date,
             total_sessions, total_sessions, user["id"]),
        )
        package_id = cur.lastrowid

        # Use explicit items, or fall back to first drink in location if template + no items
        items_to_create = data.items
        if not items_to_create and template and total_drinks > 0:
            first_drink = conn.execute(
                "SELECT id FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY id LIMIT 1",
                (loc_id,),
            ).fetchone()
            if first_drink:
                items_to_create = [{"drink_id": first_drink["id"], "total_servings": total_drinks}]

        for item in items_to_create:
            drink_id = item.get("drink_id")
            qty = item.get("total_servings", 0)
            if drink_id and qty > 0:
                conn.execute(
                    "INSERT INTO package_items (package_id, drink_id, total_servings, remaining_servings) VALUES (?, ?, ?, ?)",
                    (package_id, drink_id, qty, qty),
                )
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'create', 'package', ?, ?)""",
            (loc_id, user["id"], package_id,
             f'{{"customer_id": {data.customer_id}, "name": "{data.name}", "amount": {data.total_amount}, "template_id": {data.package_template_id}, "duration_days": {duration_days}, "total_sessions": {total_sessions}}}'),
        )
    return {"id": package_id, "message": "Gói đã được tạo", "start_date": start_date, "end_date": end_date}


@router.get("/customer/{customer_id}/packages")
def get_customer_packages(customer_id: int, user: dict = Depends(get_current_user)):
    """Get active packages for a customer with remaining servings."""
    with get_db() as conn:
        packages = conn.execute(
            """SELECT p.*, c.full_name as customer_name, c.code as customer_code
               FROM packages p
               JOIN customers c ON c.id = p.customer_id
               WHERE p.customer_id = ? AND p.is_active = 1
               ORDER BY p.created_at DESC""",
            (customer_id,),
        ).fetchall()
    results = []
    for pkg in packages:
        d = dict(pkg)
        with get_db() as conn:
            items = conn.execute(
                """SELECT pi.*, d.name as drink_name
                   FROM package_items pi
                   JOIN drinks d ON d.id = pi.drink_id
                   WHERE pi.package_id = ? AND pi.remaining_servings > 0""",
                (pkg["id"],),
            ).fetchall()
        d["items"] = [dict(item) for item in items]
        results.append(d)
    return results


@router.put("/{package_id}/deactivate")
def deactivate_package(package_id: int, user: dict = Depends(require_role("MANAGER"))):
    """Deactivate a package (soft delete). MANAGER+."""
    with get_db() as conn:
        pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        if pkg is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy gói")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE packages SET is_active = 0, updated_at = ? WHERE id = ?", (now, package_id))
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'deactivate', 'package', ?, ?)""",
            (pkg["location_id"], user["id"], package_id, f'{{"name": "{pkg["name"]}"}}'),
        )
    return {"message": "Gói đã bị vô hiệu hóa"}


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/packages")
def packages_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return

    render()
    render_navbar()


def render():
    """Render the package management page."""
    role = app.storage.user.get("role", "STAFF")
    loc_id = get_current_location_id()

    # Helpers defined first so on_click callbacks can reference them.
    # Widgets (search_input, customer_select, package_table) are resolved
    # at call time via Python's closure mechanism.
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
        customer_select_options.clear()
        for r in rows:
            customer_select_options[r["id"]] = f"{r['code']} - {r['full_name']}"
        customer_select.set_options(customer_select_options)

    def refresh():
        customer_id = customer_select.value
        with get_db() as conn:
            where = "WHERE p.is_active = 1 AND p.location_id = ?"
            params = [loc_id]
            if customer_id:
                where += " AND p.customer_id = ?"
                params.append(customer_id)
            packages = conn.execute(
                f"""SELECT p.*, c.full_name as customer_name, c.code as customer_code
                    FROM packages p
                    JOIN customers c ON c.id = p.customer_id
                    {where}
                    ORDER BY p.created_at DESC""",
                params,
            ).fetchall()
        results = []
        for pkg in packages:
            with get_db() as conn:
                items = conn.execute(
                    """SELECT pi.*, d.name as drink_name
                       FROM package_items pi
                       JOIN drinks d ON d.id = pi.drink_id
                       WHERE pi.package_id = ?""",
                    (pkg["id"],),
                ).fetchall()
            item_str = ", ".join(f"{it['drink_name']}: {it['remaining_servings']:.0f}/{it['total_servings']:.0f} ly" for it in items)
            results.append({
                "id": pkg["id"],
                "name": pkg["name"],
                "customer": f"{pkg['customer_code']} - {pkg['customer_name']}",
                "amount": f"{pkg['total_amount']:,.0f}đ",
                "items": item_str,
                "date": pkg["created_at"][:10],
            })
        package_table.rows = results
        package_table.update()

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("📦").classes("text-2xl")
            ui.label("Quản lý gói tập")

    # Search customer
    with ui.element("div").classes("page-container"):
        with ui.element("div").classes("search-bar"):
            search_input = ui.input("Tìm theo tên hoặc mã khách hàng").props("outlined clearable dense").classes("flex-grow")
            ui.button("Tìm khách hàng", on_click=search_customers, icon="search").props("outlined")
    customer_select_options = {}

    customer_select = ui.select({}, label="Chọn khách hàng").props("outlined dense").classes("w-full mb-3")

    search_input.on("keyup.enter", search_customers)

    # Create package dialog (must be defined before buttons that reference it)
    with ui.dialog() as create_dialog, ui.card().classes("p-6 w-full max-w-lg"):
        ui.label("Tạo gói trả trước").classes("text-xl font-bold mb-4")

        # Customer select inside dialog
        with get_db() as conn:
            all_customers = conn.execute(
                "SELECT id, code, full_name FROM customers WHERE is_active = 1 AND location_id = ? ORDER BY full_name",
                (loc_id,),
            ).fetchall()
        cust_options = {r["id"]: f"{r['code']} - {r['full_name']}" for r in all_customers}
        p_customer = ui.select(cust_options, label="Khách hàng *").props("outlined").classes("w-full mb-2")
        p_name = ui.input("Tên gói", value="").props("outlined").classes("w-full mb-2")
        p_amount = ui.number("Tổng tiền (VNĐ)", value=0).props("outlined").classes("w-full mb-4")

        ui.label("Các món trong gói:").classes("text-sm font-bold mb-2")
        package_items = []

        with get_db() as conn:
            all_drinks = conn.execute(
                "SELECT id, name, price_per_serving FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY name",
                (loc_id,),
            ).fetchall()
        drink_options = {r["id"]: f"{r['name']} ({r['price_per_serving']:,.0f}đ/ly)" for r in all_drinks}

        items_container = ui.column().classes("w-full mb-4")

        def add_item_row():
            with items_container:
                with ui.row().classes("w-full items-center gap-2 mb-2"):
                    drink_select = ui.select(drink_options, label="Đồ uống").props("outlined").classes("flex-1")
                    servings = ui.number("Số ly", value=1).props("outlined").classes("w-24")
            package_items.append({"drink_select": drink_select, "servings": servings})

        add_item_row()

        err = ui.label().classes("text-red-500 text-sm")

        def handle_create():
            if not p_customer.value:
                err.set_text("Vui lòng chọn khách hàng")
                return
            if not package_items:
                err.set_text("Vui lòng thêm ít nhất một món")
                return
            user_id = app.storage.user.get("user_id", 1)
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO packages (location_id, customer_id, name, total_amount, created_by) VALUES (?, ?, ?, ?, ?)",
                    (loc_id, p_customer.value, p_name.value, p_amount.value or 0, user_id),
                )
                package_id = cur.lastrowid
                for item in package_items:
                    drink_id = item["drink_select"].value
                    qty = item["servings"].value or 0
                    if drink_id and qty > 0:
                        conn.execute(
                            "INSERT INTO package_items (package_id, drink_id, total_servings, remaining_servings) VALUES (?, ?, ?, ?)",
                            (package_id, drink_id, qty, qty),
                        )
                conn.execute(
                    """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                       VALUES (?, ?, 'create', 'package', ?, ?)""",
                    (loc_id, user_id, package_id, f'{{"customer_id": {p_customer.value}, "amount": {p_amount.value or 0}}}'),
                )
            create_dialog.close()
            refresh()
            ui.notify("Đã tạo gói trả trước", type="positive")

        ui.button("Thêm món", on_click=add_item_row, icon="add").props("outlined").classes("mb-2")
        ui.button("Lưu", on_click=handle_create, icon="save").props("unelevated").classes("bg-blue-600 text-white w-full")

    with ui.element("div").classes("mb-3"):
        with ui.row().classes("gap-2"):
            ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined")
            ui.button("Tạo gói tập", on_click=create_dialog.open, icon="shopping_cart").props("unelevated").classes("btn-success")

    package_table = ui.table(
        columns=[
            {"name": "name", "label": "Tên gói", "field": "name"},
            {"name": "customer", "label": "Khách hàng", "field": "customer"},
            {"name": "amount", "label": "Tổng tiền", "field": "amount"},
            {"name": "items", "label": "Đồ uống", "field": "items"},
            {"name": "date", "label": "Ngày tạo", "field": "date"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full")

    search_customers()
    refresh()
