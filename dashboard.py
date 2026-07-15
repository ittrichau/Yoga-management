"""Dashboard with revenue stats, ingredient stock, and fraud alerts - filtered by location."""
import csv
import io
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from nicegui import ui, app

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id, get_current_location_name

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _week_ago_str() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

def _this_month_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@router.get("/stats")
def get_stats(user: dict = Depends(get_current_user)):
    """API stats (not location-filtered, for mobile API)."""
    today = _today_str() + "%"
    with get_db() as conn:
        total_customers = conn.execute("SELECT COUNT(*) as cnt FROM customers WHERE is_active = 1").fetchone()["cnt"]
        total_drinks = conn.execute("SELECT COUNT(*) as cnt FROM drinks WHERE is_active = 1").fetchone()["cnt"]
        today_tx = conn.execute("SELECT COUNT(*) as cnt FROM transactions WHERE created_at LIKE ?", (today,)).fetchone()["cnt"]
        today_revenue = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at LIKE ?", (today,)).fetchone()["total"]
        low_stock = conn.execute("SELECT COUNT(*) as cnt FROM ingredients WHERE is_active = 1 AND current_stock <= min_stock").fetchone()["cnt"]
    return {
        "total_customers": total_customers,
        "total_drinks": total_drinks,
        "today_transactions": today_tx,
        "today_revenue": today_revenue,
        "low_stock_ingredients": low_stock,
    }


@router.get("/expiring-packages")
def get_expiring_packages(user: dict = Depends(get_current_user)):
    """Packages expiring within 7 days or low on sessions, in the current location."""
    loc_id = get_current_location_id()
    today = _today_str()
    with get_db() as conn:
        where = "p.is_active = 1"
        params = []
        if loc_id:
            where += " AND p.location_id = ?"
            params.append(loc_id)
        rows = conn.execute(
            f"""SELECT p.id, p.name, p.end_date, p.total_sessions, p.remaining_sessions,
                       p.total_amount, c.full_name as customer_name, c.code as customer_code,
                       (SELECT SUM(remaining_servings) FROM package_items WHERE package_id = p.id) as remaining_drinks
                FROM packages p
                JOIN customers c ON c.id = p.customer_id
                WHERE {where}
                ORDER BY p.end_date ASC NULLS LAST""",
            params,
        ).fetchall() if False else conn.execute(
            f"""SELECT p.id, p.name, p.end_date, p.total_sessions, p.remaining_sessions,
                       p.total_amount, c.full_name as customer_name, c.code as customer_code,
                       (SELECT SUM(remaining_servings) FROM package_items WHERE package_id = p.id) as remaining_drinks
                FROM packages p
                JOIN customers c ON c.id = p.customer_id
                WHERE {where}
                ORDER BY p.end_date IS NULL, p.end_date ASC""",
            params,
        ).fetchall()
    alerts = []
    for r in rows:
        reasons = []
        if r.get("end_date"):
            days_left = (datetime.strptime(r["end_date"], "%Y-%m-%d") -
                         datetime.strptime(today, "%Y-%m-%d")).days
            if days_left < 0:
                reasons.append(f"Đã hết hạn {abs(days_left)} ngày")
            elif days_left <= 7:
                reasons.append(f"Còn {days_left} ngày hết hạn")
        if r.get("total_sessions", 0) > 0 and r.get("remaining_sessions", 0) <= 3:
            reasons.append(f"Chỉ còn {r['remaining_sessions']}/{r['total_sessions']} buổi")
        if reasons:
            alerts.append({
                "package_id": r["id"],
                "package_name": r["name"] or f"Gói #{r['id']}",
                "customer": f"{r['customer_code']} - {r['customer_name']}",
                "end_date": r.get("end_date"),
                "remaining_sessions": r.get("remaining_sessions", 0),
                "total_sessions": r.get("total_sessions", 0),
                "remaining_drinks": r.get("remaining_drinks") or 0,
                "reasons": reasons,
            })
    return alerts


@router.get("/fraud-alerts")
def get_fraud_alerts(user: dict = Depends(require_role("OWNER"))):
    today = _today_str() + "%"
    alerts = []
    with get_db() as conn:
        suspicious = conn.execute(
            """SELECT t.*, c.full_name as customer_name, c.code as customer_code,
                       d.name as drink_name, u.full_name as user_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN drinks d ON d.id = t.drink_id
                JOIN users u ON u.id = t.created_by
                WHERE t.amount = 0 AND t.package_item_id IS NULL
                  AND t.created_at LIKE ?
                ORDER BY t.created_at DESC""",
            (today,),
        ).fetchall()
        for r in suspicious:
            alerts.append({
                "type": "missing_payment",
                "severity": "critical",
                "message": f"Bán {r['drink_name']} cho {r['customer_name']} không có gói, không thu tiền!",
                "created_at": r["created_at"],
            })
        rapid = conn.execute(
            """SELECT u.full_name as user_name, COUNT(*) as cnt
                FROM transactions t
                JOIN users u ON u.id = t.created_by
                WHERE t.created_at LIKE ?
                GROUP BY t.created_by
                HAVING COUNT(*) > 50""",
            (today,),
        ).fetchall()
        for r in rapid:
            alerts.append({
                "type": "rapid_sales",
                "severity": "warning",
                "message": f"{r['user_name']} đã bán {r['cnt']} ly hôm nay (cao bất thường)",
                "created_at": "today",
            })
    return alerts


@router.get("/transactions/export-csv")
def export_transactions_csv(
    customer_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: dict = Depends(get_current_user),
):
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
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT t.id, t.created_at, c.code as customer_code, c.full_name as customer_name,
                       d.name as drink_name, t.servings, t.amount, t.notes,
                       u.full_name as created_by_name,
                       l.name as location_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN drinks d ON d.id = t.drink_id
                JOIN users u ON u.id = t.created_by
                LEFT JOIN locations l ON l.id = t.location_id
                {where_clause}
                ORDER BY t.created_at DESC""",
            params,
        ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Ngày", "Cơ sở", "Mã KH", "Tên KH", "Đồ uống", "Số ly", "Doanh thu", "Ghi chú", "Nhân viên"])
    for r in rows:
        writer.writerow([r["id"], r["created_at"], r.get("location_name", ""), r["customer_code"], r["customer_name"],
                        r["drink_name"], r["servings"], r["amount"], r["notes"], r["created_by_name"]])
    output.seek(0)
    filename = f"transactions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@ui.page("/dashboard")
def dashboard_page():
    """Dashboard page - filtered by current location."""
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return

    render_navbar()
    render()


def render():
    """Render the dashboard content."""
    role = app.storage.user.get("role", "TEACHER")
    loc_id = get_current_location_id()
    loc_name = get_current_location_name()
    today_prefix = _today_str() + "%"
    week_ago = _week_ago_str()
    month_prefix = _this_month_prefix() + "%"

    ui.add_head_html('<link rel="stylesheet" href="/static/style.css">')

    d = {}
    with get_db() as conn:
        d["total_customers"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM customers WHERE is_active = 1 AND location_id = ?", (loc_id,)
        ).fetchone()["cnt"]
        d["total_drinks"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM drinks WHERE is_active = 1 AND location_id = ?", (loc_id,)
        ).fetchone()["cnt"]
        d["today_tx"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM transactions WHERE created_at LIKE ? AND location_id = ?",
            (today_prefix, loc_id),
        ).fetchone()["cnt"]
        d["today_revenue"] = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at LIKE ? AND location_id = ?",
            (today_prefix, loc_id),
        ).fetchone()["total"]
        d["week_revenue"] = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at >= ? AND location_id = ?",
            (week_ago, loc_id),
        ).fetchone()["total"]
        d["month_revenue"] = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at LIKE ? AND location_id = ?",
            (month_prefix, loc_id),
        ).fetchone()["total"]
        d["low_stock_count"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM ingredients WHERE is_active = 1 AND current_stock <= min_stock AND location_id = ?",
            (loc_id,),
        ).fetchone()["cnt"]
        d["low_product_count"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE is_active = 1 AND current_stock <= min_stock AND location_id = ?",
            (loc_id,),
        ).fetchone()["cnt"]
        d["today_pt_revenue"] = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) as total FROM pt_sessions WHERE location_id = ? AND session_date = ?",
            (loc_id, today_prefix[:-1]),
        ).fetchone()["total"]
        d["month_pt_revenue"] = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) as total FROM pt_sessions WHERE location_id = ? AND session_date LIKE ?",
            (loc_id, month_prefix),
        ).fetchone()["total"]
        d["low_stock_items"] = conn.execute(
            "SELECT name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND current_stock <= min_stock AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()
        d["low_product_items"] = conn.execute(
            "SELECT name, product_type, current_stock, min_stock FROM products WHERE is_active = 1 AND current_stock <= min_stock AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()
        d["recent_tx"] = conn.execute(
            """SELECT t.*, c.full_name as customer_name, c.code as customer_code,
                       COALESCE(d.name, p.name) as drink_name, u.full_name as user_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN users u ON u.id = t.created_by
                LEFT JOIN drinks d ON d.id = t.drink_id
                LEFT JOIN products p ON p.id = t.product_id
                WHERE t.location_id = ?
                ORDER BY t.created_at DESC LIMIT 5""",
            (loc_id,),
        ).fetchall()
        d["all_stock"] = conn.execute(
            "SELECT name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()
        d["all_product_stock"] = conn.execute(
            "SELECT id, name, product_type, current_stock, min_stock, price, sale_percent FROM products WHERE is_active = 1 AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()

    with ui.element("div").classes("page-container"):
        # Page Title
        with ui.row().classes("items-center page-title w-full"):
            ui.label("📊").classes("text-2xl")
            ui.label(f"Trang chính - {loc_name}")

        # Stats Grid
        with ui.element("div").classes("dashboard-stat-grid"):
            with ui.element("div").classes("stat-card border-primary"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("people", size="2.5rem").classes("text-primary")
                    with ui.column():
                        ui.label(str(d["total_customers"])).classes("stat-value text-primary")
                        ui.label("Khách hàng đang hoạt động").classes("stat-label")
            with ui.element("div").classes("stat-card border-success"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("local_drink", size="2.5rem").classes("text-success")
                    with ui.column():
                        ui.label(str(d["total_drinks"])).classes("stat-value text-success")
                        ui.label("Đồ uống").classes("stat-label")
            with ui.element("div").classes("stat-card border-warning"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("receipt_long", size="2.5rem").classes("text-warning")
                    with ui.column():
                        ui.label(str(d["today_tx"])).classes("stat-value text-warning")
                        ui.label("Bán hàng hôm nay").classes("stat-label")
            with ui.element("div").classes("stat-card border-info"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("account_balance_wallet", size="2.5rem").classes("text-info")
                    with ui.column():
                        ui.label(f"{d['today_revenue']:,.0f}đ").classes("stat-value text-info")
                        ui.label("Doanh thu hôm nay").classes("stat-label")

        # Revenue Summary
        with ui.element("div").classes("custom-card p-4 mt-4"):
            ui.label("💰 Tổng quan doanh thu").classes("section-header")
            with ui.element("div").classes("flex flex-col sm:flex-row gap-4 md:gap-8 mt-2"):
                ui.label(f"Tuần này: {int(d['week_revenue']):,}đ").classes("text-lg font-bold text-indigo-700")
                ui.label(f"Tháng này: {int(d['month_revenue']):,}đ").classes("text-lg font-bold text-pink-700")
                ui.label(f"PT hôm nay: {int(d['today_pt_revenue'] or 0):,}đ").classes("text-lg font-bold text-orange-700")

        # Low Stock Alerts
        if d["low_stock_count"] > 0 or d["low_product_count"] > 0:
            with ui.element("div").classes("custom-card p-4 mt-4"):
                ui.label("⚠️ Cảnh báo tồn kho").classes("section-header")
                if d["low_stock_count"] > 0:
                    with ui.element("div").classes("alert-card danger mt-2"):
                        ui.label(f"{d['low_stock_count']} nguyên liệu sắp HẾT!").classes("font-bold mb-1")
                        for p in d["low_stock_items"]:
                            ui.label(f"• {p['name']}: còn {p['current_stock']:.0f} {p['unit']} (tối thiểu {p['min_stock']:.0f})").classes("text-sm ml-2")
                if d["low_product_count"] > 0:
                    from product import PRODUCT_TYPE_LABELS
                    with ui.element("div").classes("alert-card warning mt-2"):
                        ui.label(f"{d['low_product_count']} sản phẩm (thảm, quần áo...) sắp HẾT!").classes("font-bold mb-1")
                        for p in d["low_product_items"]:
                            ptype = PRODUCT_TYPE_LABELS.get(p["product_type"], p["product_type"])
                            ui.label(f"• {p['name']} [{ptype}]: còn {p['current_stock']} cái (tối thiểu {p['min_stock']})").classes("text-sm ml-2")

        # Upcoming Birthdays (next 3 days)
        with get_db() as conn:
            today_dt = datetime.now(timezone.utc).date()
            raw_bdays = conn.execute(
                "SELECT id, code, full_name, phone, birth_date FROM customers WHERE is_active = 1 AND location_id = ? AND birth_date IS NOT NULL AND birth_date != '' ORDER BY full_name",
                (loc_id,),
            ).fetchall()
        birthday_alerts = []
        for r in raw_bdays:
            bd_str = r["birth_date"]
            if not bd_str:
                continue
            try:
                bd = datetime.strptime(bd_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            try:
                next_bd = bd.replace(year=today_dt.year)
            except ValueError:
                next_bd = bd.replace(year=today_dt.year, day=28)
            if next_bd < today_dt:
                try:
                    next_bd = bd.replace(year=today_dt.year + 1)
                except ValueError:
                    next_bd = bd.replace(year=today_dt.year + 1, day=28)
            days_until = (next_bd - today_dt).days
            if 0 <= days_until <= 3:
                age = today_dt.year - bd.year + (1 if next_bd.year > today_dt.year else 0)
                birthday_alerts.append({
                    "code": r["code"],
                    "full_name": r["full_name"],
                    "phone": r["phone"] or "",
                    "birth_date": bd.strftime("%d/%m/%Y"),
                    "days_until": days_until,
                    "age": age,
                })
        birthday_alerts.sort(key=lambda x: x["days_until"])
        if birthday_alerts:
            with ui.element("div").classes("custom-card p-4 mt-4"):
                ui.label(f"🎂 Sắp sinh nhật ({len(birthday_alerts)} khách hàng)").classes("section-header")
                for ba in birthday_alerts:
                    emoji = "🎉" if ba["days_until"] == 0 else "🎂"
                    day_text = "HÔM NAY!" if ba["days_until"] == 0 else f"Còn {ba['days_until']} ngày"
                    with ui.element("div").classes("alert-card birthday"):
                        ui.label(f"{emoji} {ba['code']} - {ba['full_name']} • Ngày sinh: {ba['birth_date']} • {day_text}").classes("text-sm font-medium")

        # Recent Transactions
        with ui.element("div").classes("custom-card p-4 mt-4"):
            with ui.row().classes("items-center justify-between mb-3"):
                ui.label("🔁 Giao dịch gần đây").classes("section-header")
                ui.button("Xuất CSV", icon="download",
                          on_click=lambda: ui.navigate.to("/api/dashboard/transactions/export-csv", new_tab=True)).props("outlined dense")

            tx_table = ui.table(
                columns=[
                    {"name": "time", "label": "Giờ", "field": "time"},
                    {"name": "customer", "label": "Khách hàng", "field": "customer"},
                    {"name": "drink", "label": "Đồ uống", "field": "drink"},
                    {"name": "servings", "label": "Số ly", "field": "servings"},
                    {"name": "amount", "label": "Doanh thu", "field": "amount"},
                    {"name": "by", "label": "NV", "field": "by"},
                ],
                rows=[],
                row_key="id",
            ).classes("w-full")

            tx_table.rows = [
                {
                    "id": r["id"],
                    "time": r["created_at"][11:19] if r["created_at"] else "",
                    "customer": f"{r['customer_code']} - {r['customer_name']}",
                    "drink": r["drink_name"],
                    "servings": r["servings"],
                    "amount": f"{r['amount']:,.0f}đ" if r["amount"] > 0 else "📦",
                    "by": r["user_name"],
                }
                for r in d["recent_tx"]
            ]
            tx_table.update()

        # Expiring Packages
        with get_db() as conn:
            expiring = conn.execute(
                """SELECT p.id, p.name, p.end_date, p.total_sessions, p.remaining_sessions,
                           c.full_name as customer_name, c.code as customer_code,
                           (SELECT SUM(remaining_servings) FROM package_items WHERE package_id = p.id) as remaining_drinks
                    FROM packages p
                    JOIN customers c ON c.id = p.customer_id
                    WHERE p.is_active = 1 AND p.location_id = ? AND p.end_date IS NOT NULL
                    ORDER BY p.end_date ASC""",
                (loc_id,),
            ).fetchall()
        today_d = datetime.strptime(today_prefix[:-1], "%Y-%m-%d")
        expiring_alerts = []
        for r in expiring:
            ed = datetime.strptime(r["end_date"], "%Y-%m-%d")
            days_left = (ed - today_d).days
            reasons = []
            if days_left < 0:
                reasons.append(f"Quá hạn {abs(days_left)} ngày")
            elif days_left <= 7:
                reasons.append(f"Còn {days_left} ngày hết hạn")
            if r.get("total_sessions", 0) > 0 and r.get("remaining_sessions", 0) <= 3:
                reasons.append(f"Chỉ còn {r['remaining_sessions']}/{r['total_sessions']} buổi")
            if reasons:
                expiring_alerts.append({
                    "package_id": r["id"],
                    "name": r["name"] or f"Gói #{r['id']}",
                    "customer": f"{r['customer_code']} - {r['customer_name']}",
                    "end_date": r["end_date"],
                    "reasons": ", ".join(reasons),
                })
        if expiring_alerts:
            with ui.element("div").classes("custom-card p-4 mt-4"):
                ui.label(f"📦 {len(expiring_alerts)} gói sắp hết hạn/sắp hết buổi").classes("section-header")
                for a in expiring_alerts[:10]:
                    with ui.element("div").classes("alert-card warning"):
                        ui.label(f"{a['customer']} - {a['name']} ({a['end_date']}): {a['reasons']}").classes("text-sm font-medium")

        # Fraud Alerts (OWNER+)
        if role in ("OWNER", "ADMIN"):
            with ui.element("div").classes("custom-card p-4 mt-4"):
                ui.label("🔍 Giao dịch bất thường").classes("section-header")
                with get_db() as conn:
                    suspicious = conn.execute(
                        """SELECT t.*, c.full_name as customer_name, c.code as customer_code,
                                   d.name as drink_name, u.full_name as user_name
                            FROM transactions t
                            JOIN customers c ON c.id = t.customer_id
                            JOIN drinks d ON d.id = t.drink_id
                            JOIN users u ON u.id = t.created_by
                            WHERE t.amount = 0 AND t.package_item_id IS NULL
                              AND t.created_at LIKE ?
                              AND t.location_id = ?
                            ORDER BY t.created_at DESC""",
                        (today_prefix, loc_id),
                    ).fetchall()
                if suspicious:
                    alert2_table = ui.table(
                        columns=[
                            {"name": "time", "label": "Giờ", "field": "time"},
                            {"name": "customer", "label": "Khách hàng", "field": "customer"},
                            {"name": "drink", "label": "Đồ uống", "field": "drink"},
                            {"name": "by", "label": "Nhân viên", "field": "by"},
                        ],
                        rows=[],
                        row_key="id",
                    ).classes("w-full mt-2")
                    alert2_table.rows = [
                        {
                            "time": r["created_at"][11:19] if r["created_at"] else "",
                            "customer": f"{r['customer_code']} - {r['customer_name']}",
                            "drink": r["drink_name"],
                            "by": r["user_name"],
                        }
                        for r in suspicious
                    ]
                    alert2_table.update()
                else:
                    with ui.element("div").classes("alert-card success"):
                        ui.label("✅ Không có giao dịch đáng ngờ hôm nay.").classes("text-sm font-medium")

        # Ingredient Stock Overview
        with ui.element("div").classes("custom-card p-4 mt-4"):
            ui.label("🧪 Tổng quan tồn kho nguyên liệu").classes("section-header")

            stock_table = ui.table(
                columns=[
                    {"name": "name", "label": "Nguyên liệu", "field": "name"},
                    {"name": "unit", "label": "Đơn vị", "field": "unit"},
                    {"name": "stock", "label": "Tồn kho", "field": "stock"},
                    {"name": "min", "label": "Tối thiểu", "field": "min"},
                    {"name": "status", "label": "Trạng thái", "field": "status"},
                ],
                rows=[],
                row_key="id",
            ).classes("w-full mt-2")

            stock_table.rows = []
            for s in d["all_stock"]:
                            if s["current_stock"] <= s["min_stock"]:
                                status = "🔴 THIẾU"
                            elif s["current_stock"] <= s["min_stock"] * 2:
                                status = "🟡 Cảnh báo"
                            else:
                                status = "🟢 OK"
                            stock_table.rows.append({
                                "id": s["name"],
                                "name": s["name"],
                                "unit": s["unit"],
                                "stock": f"{s['current_stock']:.1f}",
                                "min": f"{s['min_stock']:.1f}",
                                "status": status,
                            })
            stock_table.update()

        # Product Stock Overview
        if d["all_product_stock"]:
            with ui.element("div").classes("custom-card p-4 mt-4"):
                ui.label("🏪 Tổng quan tồn kho sản phẩm (thảm, quần áo...)").classes("section-header")

                product_stock_table = ui.table(
                    columns=[
                        {"name": "name", "label": "Sản phẩm", "field": "name"},
                        {"name": "type", "label": "Loại", "field": "type"},
                        {"name": "stock", "label": "Tồn kho", "field": "stock"},
                        {"name": "min", "label": "Tối thiểu", "field": "min"},
                        {"name": "price", "label": "Giá", "field": "price"},
                        {"name": "status", "label": "Trạng thái", "field": "status"},
                    ],
                    rows=[],
                    row_key="id",
                ).classes("w-full mt-2")

                from product import PRODUCT_TYPE_LABELS
                product_stock_table.rows = []
                for s in d["all_product_stock"]:
                    sale_price = s["price"] * (1 - s["sale_percent"] / 100) if s["sale_percent"] else s["price"]
                    if s["current_stock"] <= s["min_stock"]:
                        status = "🔴 THIẾU"
                    elif s["current_stock"] <= s["min_stock"] * 2:
                        status = "🟡 Cảnh báo"
                    else:
                        status = "🟢 OK"
                    product_stock_table.rows.append({
                        "id": s["id"],
                        "name": s["name"],
                        "type": PRODUCT_TYPE_LABELS.get(s["product_type"], s["product_type"]),
                        "stock": str(s["current_stock"]),
                        "min": str(s["min_stock"]),
                        "price": f"{sale_price:,.0f}đ",
                        "status": status,
                    })
                product_stock_table.update()
