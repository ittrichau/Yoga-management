"""Check-in workflow: search customer -> show active package -> 1-tap check-in.

The check-in page is the daily driver for staff. It combines:
- finding a customer quickly (search by code / name / phone)
- showing the customer's active package(s) with remaining sessions and drinks
- recording a session check-in (deducts 1 session + 1 drink from package)
- (optional) recording a "drink only" transaction if the customer has a drinks-only package
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/checkin", tags=["checkin"])


class CheckinRequest(BaseModel):
    customer_id: int
    package_id: int
    package_item_id: int | None = None
    drink_id: int | None = None
    notes: str = ""


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.post("/session")
def checkin_session(data: CheckinRequest, user: dict = Depends(get_current_user)):
    """Record a training session check-in for a customer with active package.

    - Validates the package is active, not expired, has remaining sessions and drinks.
    - Deducts 1 from remaining_sessions and 1 from the first available package_item.
    - Inserts a transaction (session_checkin=1, amount=0, package_item_id=...).
    - Inserts a package_sessions row for audit/reporting.
    """
    with get_db() as conn:
        customer = conn.execute(
            "SELECT * FROM customers WHERE id = ? AND is_active = 1", (data.customer_id,)
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")

        pkg = conn.execute(
            "SELECT * FROM packages WHERE id = ? AND customer_id = ? AND is_active = 1",
            (data.package_id, data.customer_id),
        ).fetchone()
        if pkg is None:
            raise HTTPException(status_code=404, detail="Gói không hợp lệ")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if pkg.get("end_date") and pkg["end_date"] < today:
            raise HTTPException(status_code=400, detail=f"Gói đã hết hạn từ {pkg['end_date']}")

        if pkg.get("total_sessions", 0) > 0 and pkg.get("remaining_sessions", 0) <= 0:
            raise HTTPException(status_code=400, detail="Gói đã hết buổi tập")

        # Pick the package_item: explicit or first one with remaining servings
        item = None
        if data.package_item_id:
            item = conn.execute(
                "SELECT * FROM package_items WHERE id = ? AND package_id = ?",
                (data.package_item_id, data.package_id),
            ).fetchone()
        else:
            item = conn.execute(
                """SELECT * FROM package_items
                   WHERE package_id = ? AND remaining_servings > 0
                   ORDER BY id LIMIT 1""",
                (data.package_id,),
            ).fetchone()
        if item is None or item["remaining_servings"] <= 0:
            raise HTTPException(status_code=400, detail="Gói đã hết ly đồ uống")

        drink_id = data.drink_id or item["drink_id"]
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        today_str = today

        # 1) Insert session log
        cur = conn.execute(
            """INSERT INTO package_sessions
               (package_id, checkin_date, checkin_time, created_by)
               VALUES (?, ?, ?, ?)""",
            (data.package_id, today_str, now_str, user["id"]),
        )
        session_id = cur.lastrowid

        # 2) Deduct from package
        conn.execute(
            "UPDATE package_items SET remaining_servings = remaining_servings - 1 WHERE id = ?",
            (item["id"],),
        )
        if pkg.get("total_sessions", 0) > 0:
            conn.execute(
                "UPDATE packages SET remaining_sessions = remaining_sessions - 1 WHERE id = ?",
                (data.package_id,),
            )

        # 3) Insert transaction
        cur = conn.execute(
            """INSERT INTO transactions
               (location_id, customer_id, drink_id, package_item_id,
                servings, amount, notes, session_checkin, created_by)
               VALUES (?, ?, ?, ?, 1, 0, ?, 1, ?)""",
            (customer["location_id"], data.customer_id, drink_id, item["id"],
             data.notes or f"Check-in buổi tập gói #{data.package_id}", user["id"]),
        )
        tx_id = cur.lastrowid

        # 4) Update session with transaction link
        conn.execute(
            "UPDATE package_sessions SET transaction_id = ? WHERE id = ?", (tx_id, session_id)
        )

        # 5) Deduct ingredients
        _deduct_ingredients(conn, drink_id, 1, customer["location_id"])

        # 6) Audit
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'checkin_session', 'package', ?, ?)""",
            (customer["location_id"], user["id"], data.package_id,
             f'{{"customer":"{customer["full_name"]}","session_id":{session_id},"tx_id":{tx_id}}}'),
        )

        # Return remaining counts
        new_pkg = conn.execute(
            "SELECT remaining_sessions, total_sessions, end_date FROM packages WHERE id = ?",
            (data.package_id,),
        ).fetchone()
        new_item = conn.execute(
            "SELECT remaining_servings, total_servings FROM package_items WHERE id = ?",
            (item["id"],),
        ).fetchone()

    return {
        "message": "Check-in thành công",
        "session_id": session_id,
        "transaction_id": tx_id,
        "remaining_sessions": new_pkg["remaining_sessions"],
        "total_sessions": new_pkg["total_sessions"],
        "remaining_servings": new_item["remaining_servings"],
        "total_servings": new_item["total_servings"],
        "end_date": new_pkg.get("end_date"),
    }


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
            """INSERT INTO inventory_adjustments
               (location_id, ingredient_id, adjustment_type, quantity, reason)
               VALUES (?, ?, 'remove', ?, ?)""",
            (loc_id, rec["ingredient_id"], needed, f"Auto-deduct from checkin: {drink_id}"),
        )


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/checkin")
def checkin_page():
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
    ui.label("Check-in buổi tập").classes("text-2xl font-bold mb-4")

    # Search customer
    with ui.row().classes("w-full items-end gap-2 mb-4 flex-wrap"):
        search_input = ui.input("Tìm khách hàng (mã, tên, SĐT)").props("outlined autofocus").classes("flex-1 min-w-64")
        ui.button("Tìm", on_click=lambda: do_search(), icon="search").props("unelevated").classes("bg-blue-600 text-white")

    customer_options = {}
    customer_select = ui.select({}, label="Chọn khách hàng").props("outlined").classes("w-full mb-4")

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
            phone = r.get("phone") or ""
            customer_options[r["id"]] = f"{r['code']} - {r['full_name']}" + (f" ({phone})" if phone else "")
        customer_select.set_options(customer_options)

    search_input.on("keyup.enter", do_search)

    # Info card area
    info_card = ui.column().classes("w-full mb-4")

    success_label = ui.label().classes("text-green-600 text-base font-bold mb-2")
    err_label = ui.label().classes("text-red-500 text-sm mb-2")

    def load_packages_for_customer():
        info_card.clear()
        success_label.set_text("")
        err_label.set_text("")
        cid = customer_select.value
        if not cid:
            with info_card:
                ui.label("Vui lòng chọn khách hàng để xem gói.").classes("text-gray-500 italic")
            return
        with get_db() as conn:
            customer = conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
            packages = conn.execute(
                """SELECT * FROM packages
                   WHERE customer_id = ? AND is_active = 1
                   ORDER BY created_at DESC""",
                (cid,),
            ).fetchall()
        if customer is None:
            with info_card:
                ui.label("Khách hàng không tồn tại.").classes("text-red-500")
            return

        with info_card:
            ui.label(f"Khách hàng: {customer['full_name']} ({customer['code']})").classes("text-lg font-bold mb-2")
            if not packages:
                ui.label("⚠️ Khách chưa có gói nào đang hoạt động.").classes("text-orange-600 italic")
                return

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for pkg in packages:
                items = []
                with get_db() as conn:
                    items = conn.execute(
                        """SELECT pi.*, d.name as drink_name FROM package_items pi
                           JOIN drinks d ON d.id = pi.drink_id
                           WHERE pi.package_id = ?""",
                        (pkg["id"],),
                    ).fetchall()
                sessions_info = ""
                if pkg.get("total_sessions", 0) > 0:
                    sessions_info = f" | Buổi: {pkg['remaining_sessions']}/{pkg['total_sessions']}"
                end_info = f" | Hết hạn: {pkg['end_date']}" if pkg.get("end_date") else ""
                expired = pkg.get("end_date") and pkg["end_date"] < today
                color = "red" if expired else "blue"
                with ui.card().classes(f"w-full p-4 mb-2 border-2 border-{color}-200"):
                    ui.label(f"📦 {pkg['name'] or 'Gói #'+str(pkg['id'])}").classes("text-base font-bold")
                    ui.label(
                        f"Tiền: {pkg['total_amount']:,.0f}đ{sessions_info}{end_info}"
                    ).classes("text-sm text-gray-700")
                    items_str = ", ".join(
                        f"{it['drink_name']}: {it['remaining_servings']:.0f}/{it['total_servings']:.0f} ly"
                        for it in items
                    )
                    ui.label(f"Đồ uống: {items_str}").classes("text-sm text-gray-700")
                    if expired:
                        ui.label("⛔ GÓI ĐÃ HẾT HẠN").classes("text-red-600 font-bold")
                        continue
                    if pkg.get("total_sessions", 0) > 0 and pkg.get("remaining_sessions", 0) <= 0:
                        ui.label("⛔ Đã hết buổi tập").classes("text-red-600 font-bold")
                        continue
                    # Check-in button
                    def make_checkin(pkg_id=pkg["id"], first_item_id=items[0]["id"] if items else None, drink_id=items[0]["drink_id"] if items else None):
                        def do():
                            err_label.set_text("")
                            success_label.set_text("")
                            try:
                                r = _do_checkin_api(pkg_id, first_item_id, drink_id)
                                success_label.set_text(
                                    f"✅ Check-in thành công! Còn {r['remaining_sessions']}/{r['total_sessions']} buổi, "
                                    f"{r['remaining_servings']}/{r['total_servings']} ly"
                                )
                                load_packages_for_customer()
                            except HTTPException as ex:
                                err_label.set_text(f"❌ Lỗi: {ex.detail}")
                        return do
                    ui.button("✓ Check-in buổi tập", on_click=make_checkin(), icon="check_circle").props(
                        "unelevated"
                    ).classes("bg-green-600 text-white mt-2")

    def _do_checkin_api(pkg_id, item_id, drink_id):
        """Call the checkin API synchronously via the same code path."""
        cid = customer_select.value
        if not cid:
            raise HTTPException(status_code=400, detail="Chưa chọn khách hàng")
        # Re-use logic by calling a fake request object
        from fastapi import Request
        # Direct DB call is simpler than faking a Request
        with get_db() as conn:
            user_id = app.storage.user.get("user_id", 1)
            # mirror checkin_session logic
            customer = conn.execute("SELECT * FROM customers WHERE id = ? AND is_active = 1", (cid,)).fetchone()
            if customer is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")
            pkg = conn.execute(
                "SELECT * FROM packages WHERE id = ? AND customer_id = ? AND is_active = 1",
                (pkg_id, cid),
            ).fetchone()
            if pkg is None:
                raise HTTPException(status_code=404, detail="Gói không hợp lệ")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if pkg.get("end_date") and pkg["end_date"] < today:
                raise HTTPException(status_code=400, detail=f"Gói đã hết hạn từ {pkg['end_date']}")
            if pkg.get("total_sessions", 0) > 0 and pkg.get("remaining_sessions", 0) <= 0:
                raise HTTPException(status_code=400, detail="Gói đã hết buổi tập")
            item = conn.execute(
                "SELECT * FROM package_items WHERE id = ? AND package_id = ?", (item_id, pkg_id)
            ).fetchone() if item_id else None
            if item is None or item["remaining_servings"] <= 0:
                raise HTTPException(status_code=400, detail="Gói đã hết ly đồ uống")
            drink_id_final = drink_id or item["drink_id"]
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            cur = conn.execute(
                """INSERT INTO package_sessions (package_id, checkin_date, checkin_time, created_by)
                   VALUES (?, ?, ?, ?)""",
                (pkg_id, today, now_str, user_id),
            )
            session_id = cur.lastrowid
            conn.execute("UPDATE package_items SET remaining_servings = remaining_servings - 1 WHERE id = ?", (item["id"],))
            if pkg.get("total_sessions", 0) > 0:
                conn.execute("UPDATE packages SET remaining_sessions = remaining_sessions - 1 WHERE id = ?", (pkg_id,))
            cur = conn.execute(
                """INSERT INTO transactions
                   (location_id, customer_id, drink_id, package_item_id, servings, amount, notes, session_checkin, created_by)
                   VALUES (?, ?, ?, ?, 1, 0, ?, 1, ?)""",
                (customer["location_id"], cid, drink_id_final, item["id"], f"Check-in buổi tập gói #{pkg_id}", user_id),
            )
            tx_id = cur.lastrowid
            conn.execute("UPDATE package_sessions SET transaction_id = ? WHERE id = ?", (tx_id, session_id))
            _deduct_ingredients(conn, drink_id_final, 1, customer["location_id"])
            conn.execute(
                """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                   VALUES (?, ?, 'checkin_session', 'package', ?, ?)""",
                (customer["location_id"], user_id, pkg_id,
                 f'{{"customer":"{customer["full_name"]}","session_id":{session_id},"tx_id":{tx_id}}}'),
            )
            new_pkg = conn.execute(
                "SELECT remaining_sessions, total_sessions, end_date FROM packages WHERE id = ?", (pkg_id,)
            ).fetchone()
            new_item = conn.execute(
                "SELECT remaining_servings, total_servings FROM package_items WHERE id = ?", (item["id"],)
            ).fetchone()
        return {
            "message": "ok",
            "session_id": session_id,
            "transaction_id": tx_id,
            "remaining_sessions": new_pkg["remaining_sessions"],
            "total_sessions": new_pkg["total_sessions"],
            "remaining_servings": new_item["remaining_servings"],
            "total_servings": new_item["total_servings"],
            "end_date": new_pkg.get("end_date"),
        }

    customer_select.on("update:model-value", load_packages_for_customer)
    do_search()