"""Package upgrade flow: customer with active package -> upgrade to a new package.

Upgrade formula (as agreed):
    1. Compute the per-session price of the old package: old_price / old_total_sessions
    2. Value remaining of old package = old_per_session * old_remaining_sessions
    3. Per-session price of the new package: new_price / new_total_sessions
    4. Cost of equivalent remaining sessions in the new package:
       new_per_session * old_remaining_sessions
    5. Top-up amount = cost_in_new - remaining_value_of_old
    6. Edge case: if old package has no sessions (drinks-only), use the
       remaining_servings ratio instead: (remaining / total) * old_price.

After the upgrade:
    - Old package is deactivated (is_active = 0), with audit log.
    - A new package is created with full quota, end_date = today + new_duration.
    - top_up_amount is stored on the new package's total_amount.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/package-upgrade", tags=["package-upgrade"])


class UpgradePreview(BaseModel):
    customer_id: int
    old_package_id: int
    new_template_id: int
    start_date: str | None = None
    top_up_amount: float = 0


class UpgradeExecute(BaseModel):
    customer_id: int
    old_package_id: int
    new_template_id: int
    start_date: str | None = None


# ---------------------------------------------------------------------------
# Helper: compute top-up amount
# ---------------------------------------------------------------------------
def _compute_top_up(conn, old_pkg: dict, new_template: dict) -> dict:
    """Return breakdown dict of the upgrade math.

    Keys: old_per_session, old_value_remaining, new_per_session,
          cost_in_new, top_up, ratio_used
    """
    old_total_sessions = old_pkg.get("total_sessions", 0) or 0
    old_remaining = old_pkg.get("remaining_sessions", 0) or 0
    new_total_sessions = new_template.get("total_sessions", 0) or 0
    new_total_drinks = new_template.get("total_drinks", 0) or 0
    old_price = float(old_pkg.get("total_amount", 0) or 0)
    new_price = float(new_template.get("total_amount", 0) or 0)

    ratio_used = "session"
    if old_total_sessions > 0 and old_remaining > 0 and new_total_sessions > 0:
        # Per-session conversion
        old_per_session = old_price / old_total_sessions
        old_value_remaining = old_per_session * old_remaining
        new_per_session = new_price / new_total_sessions
        cost_in_new = new_per_session * old_remaining
        top_up = cost_in_new - old_value_remaining
    else:
        # Fallback to drinks ratio (e.g. when old is drinks-only)
        old_total_drinks = 0
        old_remaining_drinks = 0
        items = conn.execute(
            "SELECT total_servings, remaining_servings FROM package_items WHERE package_id = ?",
            (old_pkg["id"],),
        ).fetchall()
        for it in items:
            old_total_drinks += it["total_servings"]
            old_remaining_drinks += it["remaining_servings"]
        if old_total_drinks > 0 and old_remaining_drinks > 0:
            ratio_used = "drink"
            old_value_remaining = old_price * (old_remaining_drinks / old_total_drinks)
            top_up = new_price - old_value_remaining
            new_per_session = new_price / max(new_total_drinks, 1)
            cost_in_new = new_per_session * old_remaining_drinks
            old_per_session = old_price / max(old_total_drinks, 1)
        else:
            # No usable data, full price
            ratio_used = "full"
            top_up = new_price
            old_per_session = old_price
            old_value_remaining = 0
            new_per_session = new_price / max(new_total_sessions, 1)
            cost_in_new = new_price

    return {
        "old_per_session": old_per_session,
        "old_value_remaining": old_value_remaining,
        "new_per_session": new_per_session,
        "cost_in_new": cost_in_new,
        "top_up": max(0, top_up),
        "ratio_used": ratio_used,
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.post("/preview")
def upgrade_preview(data: UpgradePreview, user: dict = Depends(require_role("MANAGER"))):
    """Compute the upgrade breakdown without actually performing it."""
    with get_db() as conn:
        old_pkg = conn.execute("SELECT * FROM packages WHERE id = ? AND is_active = 1", (data.old_package_id,)).fetchone()
        if old_pkg is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy gói cũ")
        if old_pkg["customer_id"] != data.customer_id:
            raise HTTPException(status_code=400, detail="Gói cũ không thuộc khách hàng này")
        new_tpl = conn.execute(
            "SELECT * FROM package_templates WHERE id = ? AND is_active = 1",
            (data.new_template_id,),
        ).fetchone()
        if new_tpl is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mẫu gói mới")
        breakdown = _compute_top_up(conn, old_pkg, new_tpl)
    return {
        "old_package": {
            "id": old_pkg["id"],
            "name": old_pkg["name"],
            "total_amount": old_pkg["total_amount"],
            "total_sessions": old_pkg.get("total_sessions", 0),
            "remaining_sessions": old_pkg.get("remaining_sessions", 0),
            "end_date": old_pkg.get("end_date"),
        },
        "new_template": dict(new_tpl),
        "breakdown": breakdown,
    }


@router.post("/execute", status_code=201)
def upgrade_execute(data: UpgradeExecute, user: dict = Depends(require_role("MANAGER"))):
    """Perform the upgrade: deactivate old, create new with top-up amount."""
    with get_db() as conn:
        old_pkg = conn.execute("SELECT * FROM packages WHERE id = ? AND is_active = 1", (data.old_package_id,)).fetchone()
        if old_pkg is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy gói cũ")
        if old_pkg["customer_id"] != data.customer_id:
            raise HTTPException(status_code=400, detail="Gói cũ không thuộc khách hàng này")
        new_tpl = conn.execute(
            "SELECT * FROM package_templates WHERE id = ? AND is_active = 1",
            (data.new_template_id,),
        ).fetchone()
        if new_tpl is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mẫu gói mới")
        breakdown = _compute_top_up(conn, old_pkg, new_tpl)
        top_up = breakdown["top_up"]
        loc_id = old_pkg["location_id"]
        start_date = data.start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = (sd + timedelta(days=new_tpl["duration_days"])).strftime("%Y-%m-%d")

        # 1) Deactivate old
        conn.execute(
            "UPDATE packages SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?",
            (old_pkg["id"],),
        )

        # 2) Create new
        cur = conn.execute(
            """INSERT INTO packages
               (location_id, customer_id, name, total_amount,
                package_template_id, duration_days, start_date, end_date,
                total_sessions, remaining_sessions, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (loc_id, data.customer_id, new_tpl["name"], top_up,
             new_tpl["id"], new_tpl["duration_days"], start_date, end_date,
             new_tpl["total_sessions"], new_tpl["total_sessions"], user["id"]),
        )
        new_id = cur.lastrowid

        # 3) Create package_items for the new package (1 item per drink in location)
        first_drink = conn.execute(
            "SELECT id FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY id LIMIT 1",
            (loc_id,),
        ).fetchone()
        total_drinks = new_tpl["total_drinks"] or 0
        if first_drink and total_drinks > 0:
            conn.execute(
                """INSERT INTO package_items
                   (package_id, drink_id, total_servings, remaining_servings)
                   VALUES (?, ?, ?, ?)""",
                (new_id, first_drink["id"], total_drinks, total_drinks),
            )

        # 4) Audit
        conn.execute(
            """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, 'upgrade', 'package', ?, ?)""",
            (loc_id, user["id"], new_id,
             f'{{"old_package_id":{old_pkg["id"]}, "new_template_id":{new_tpl["id"]}, '
             f'"top_up":{top_up}, "breakdown":{breakdown!r}}}'),
        )

    return {
        "new_package_id": new_id,
        "top_up_amount": top_up,
        "breakdown": breakdown,
        "message": f"Nâng cấp thành công. Tiền bù: {top_up:,.0f}đ",
    }


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/packages/upgrade")
def upgrade_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return
    role = app.storage.user.get("role", "STAFF")
    if role not in ("MANAGER", "OWNER"):
        ui.notify("Chỉ MANAGER trở lên mới được nâng cấp gói", type="negative")
        ui.navigate.to("/dashboard")
        return
    render()
    render_navbar()


def render():
    loc_id = get_current_location_id()
    ui.label("Nâng cấp gói").classes("text-2xl font-bold mb-4")

    # Step 1: select customer
    with ui.row().classes("w-full items-end gap-2 mb-4 flex-wrap"):
        search_input = ui.input("Tìm khách hàng (mã, tên, SĐT)").props("outlined").classes("flex-1 min-w-64")
        ui.button("Tìm", on_click=lambda: do_search(), icon="search").props("unelevated").classes("bg-blue-600 text-white")

    customer_options = {}
    customer_select = ui.select({}, label="Chọn khách hàng").props("outlined").classes("w-full mb-4")
    package_options = {}
    package_select = ui.select({}, label="Chọn gói hiện tại").props("outlined").classes("w-full mb-4")
    template_options = {}
    template_select = ui.select({}, label="Chọn mẫu gói muốn nâng cấp").props("outlined").classes("w-full mb-4")

    preview_card = ui.column().classes("w-full mb-4")
    success_label = ui.label().classes("text-green-600 text-base font-bold mb-2")
    err_label = ui.label().classes("text-red-500 text-sm mb-2")

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

    def load_customer_packages():
        package_options.clear()
        package_select.set_options({})
        cid = customer_select.value
        if not cid:
            return
        with get_db() as conn:
            packages = conn.execute(
                """SELECT p.*, (SELECT SUM(remaining_servings) FROM package_items WHERE package_id = p.id) as remaining_drinks
                   FROM packages p
                   WHERE p.customer_id = ? AND p.is_active = 1
                   ORDER BY p.created_at DESC""",
                (cid,),
            ).fetchall()
        for p in packages:
            label = f"#{p['id']} - {p['name'] or 'Gói'} ({p['total_amount']:,.0f}đ)"
            if p.get("total_sessions", 0) > 0:
                label += f" | {p['remaining_sessions']}/{p['total_sessions']} buổi"
            if p.get("end_date"):
                label += f" | Hết hạn {p['end_date']}"
            package_options[p["id"]] = label
        package_select.set_options(package_options)

    def load_templates():
        template_options.clear()
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM package_templates WHERE is_active = 1 AND location_id = ? ORDER BY total_amount",
                (loc_id,),
            ).fetchall()
        for t in rows:
            template_options[t["id"]] = (
                f"{t['name']} - {t['total_amount']:,.0f}đ "
                f"({t['total_sessions']} buổi, {t['total_drinks']} ly, {t['duration_days']} ngày)"
            )
        template_select.set_options(template_options)

    def compute_preview():
        preview_card.clear()
        success_label.set_text("")
        err_label.set_text("")
        pid = package_select.value
        tid = template_select.value
        if not pid or not tid:
            return
        with get_db() as conn:
            old_pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (pid,)).fetchone()
            new_tpl = conn.execute("SELECT * FROM package_templates WHERE id = ?", (tid,)).fetchone()
        if old_pkg is None or new_tpl is None:
            err_label.set_text("Gói hoặc mẫu gói không hợp lệ")
            return
        # Inline compute (mirroring _compute_top_up)
        old_total_s = old_pkg.get("total_sessions", 0) or 0
        old_rem_s = old_pkg.get("remaining_sessions", 0) or 0
        new_total_s = new_tpl.get("total_sessions", 0) or 0
        old_price = float(old_pkg.get("total_amount", 0) or 0)
        new_price = float(new_tpl.get("total_amount", 0) or 0)
        if old_total_s > 0 and old_rem_s > 0 and new_total_s > 0:
            old_per = old_price / old_total_s
            old_val = old_per * old_rem_s
            new_per = new_price / new_total_s
            cost_in_new = new_per * old_rem_s
            top_up = max(0, cost_in_new - old_val)
            method = "theo buổi"
        else:
            with get_db() as conn:
                items = conn.execute(
                    "SELECT total_servings, remaining_servings FROM package_items WHERE package_id = ?",
                    (old_pkg["id"],),
                ).fetchall()
            tot = sum(it["total_servings"] for it in items)
            rem = sum(it["remaining_servings"] for it in items)
            if tot > 0 and rem > 0:
                old_val = old_price * (rem / tot)
                top_up = max(0, new_price - old_val)
                old_per = old_price / tot
                new_per = new_price / max(new_tpl["total_drinks"], 1)
                cost_in_new = new_per * rem
                method = "theo ly"
            else:
                top_up = new_price
                old_per = old_price
                old_val = 0
                new_per = new_price / max(new_total_s, 1)
                cost_in_new = new_price
                method = "trọn gói"
        with preview_card:
            with ui.card().classes("w-full p-4 border-2 border-blue-200"):
                ui.label("📊 Chi tiết nâng cấp").classes("text-lg font-bold mb-2")
                ui.label(f"Phương pháp tính: {method}").classes("text-sm text-gray-600 mb-2")
                ui.label(f"Gói cũ: {old_pkg['name']} - {old_price:,.0f}đ ({old_rem_s}/{old_total_s} buổi)").classes("text-sm")
                ui.label(f"Đơn giá buổi cũ: {old_per:,.0f}đ").classes("text-sm text-gray-700")
                ui.label(f"Giá trị còn lại: {old_val:,.0f}đ").classes("text-sm text-gray-700")
                ui.separator()
                ui.label(f"Gói mới: {new_tpl['name']} - {new_price:,.0f}đ ({new_total_s} buổi, {new_tpl['total_drinks']} ly, {new_tpl['duration_days']} ngày)").classes("text-sm")
                ui.label(f"Đơn giá buổi mới: {new_per:,.0f}đ").classes("text-sm text-gray-700")
                ui.label(f"Giá trị {old_rem_s} buổi theo gói mới: {cost_in_new:,.0f}đ").classes("text-sm text-gray-700")
                ui.separator()
                ui.label(f"💰 Tiền bù phải trả: {top_up:,.0f}đ").classes("text-xl font-bold text-red-600")
            ui.button(
                "✓ Xác nhận nâng cấp",
                on_click=lambda: do_upgrade(pid, tid),
                icon="check_circle",
            ).props("unelevated").classes("bg-green-600 text-white w-full mt-2")

    def do_upgrade(pid, tid):
        cid = customer_select.value
        if not cid:
            err_label.set_text("Chưa chọn khách hàng")
            return
        user_id = app.storage.user.get("user_id", 1)
        with get_db() as conn:
            old_pkg = conn.execute("SELECT * FROM packages WHERE id = ? AND is_active = 1", (pid,)).fetchone()
            new_tpl = conn.execute("SELECT * FROM package_templates WHERE id = ? AND is_active = 1", (tid,)).fetchone()
            if old_pkg is None or new_tpl is None:
                err_label.set_text("Gói hoặc mẫu gói không hợp lệ")
                return
            breakdown = _compute_top_up(conn, old_pkg, new_tpl)
            top_up = breakdown["top_up"]
            start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = (sd + timedelta(days=new_tpl["duration_days"])).strftime("%Y-%m-%d")
            conn.execute(
                "UPDATE packages SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?",
                (pid,),
            )
            cur = conn.execute(
                """INSERT INTO packages
                   (location_id, customer_id, name, total_amount,
                    package_template_id, duration_days, start_date, end_date,
                    total_sessions, remaining_sessions, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (loc_id, cid, new_tpl["name"], top_up,
                 new_tpl["id"], new_tpl["duration_days"], start_date, end_date,
                 new_tpl["total_sessions"], new_tpl["total_sessions"], user_id),
            )
            new_id = cur.lastrowid
            first_drink = conn.execute(
                "SELECT id FROM drinks WHERE is_active = 1 AND location_id = ? ORDER BY id LIMIT 1",
                (loc_id,),
            ).fetchone()
            if first_drink and new_tpl["total_drinks"] > 0:
                conn.execute(
                    """INSERT INTO package_items
                       (package_id, drink_id, total_servings, remaining_servings)
                       VALUES (?, ?, ?, ?)""",
                    (new_id, first_drink["id"], new_tpl["total_drinks"], new_tpl["total_drinks"]),
                )
            conn.execute(
                """INSERT INTO audit_logs (location_id, user_id, action, entity_type, entity_id, details)
                   VALUES (?, ?, 'upgrade', 'package', ?, ?)""",
                (loc_id, user_id, new_id,
                 f'{{"old_package_id":{pid}, "new_template_id":{tid}, "top_up":{top_up}}}'),
            )
        success_label.set_text(f"✅ Nâng cấp thành công! Gói mới #{new_id}, tiền bù {top_up:,.0f}đ")
        load_customer_packages()

    customer_select.on("update:model-value", load_customer_packages)
    package_select.on("update:model-value", compute_preview)
    template_select.on("update:model-value", compute_preview)
    do_search()
    load_templates()