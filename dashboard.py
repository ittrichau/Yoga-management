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


@router.get("/fraud-alerts")
def get_fraud_alerts(user: dict = Depends(require_role("MANAGER"))):
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

    render()
    render_navbar()


def render():
    """Render the dashboard content."""
    role = app.storage.user.get("role", "STAFF")
    loc_id = get_current_location_id()
    loc_name = get_current_location_name()
    today_prefix = _today_str() + "%"
    week_ago = _week_ago_str()
    month_prefix = _this_month_prefix() + "%"

    ui.label(f"Bảng điều khiển - {loc_name}").classes("text-2xl font-bold mb-4")

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
        d["low_stock_items"] = conn.execute(
            "SELECT name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND current_stock <= min_stock AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()

        d["recent_tx"] = conn.execute(
            """SELECT t.*, c.full_name as customer_name, c.code as customer_code,
                       d.name as drink_name, u.full_name as user_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN drinks d ON d.id = t.drink_id
                JOIN users u ON u.id = t.created_by
                WHERE t.location_id = ?
                ORDER BY t.created_at DESC LIMIT 5""",
            (loc_id,),
        ).fetchall()

        d["all_stock"] = conn.execute(
            "SELECT name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND location_id = ? ORDER BY name",
            (loc_id,),
        ).fetchall()

    # Stats cards
    with ui.row().classes("w-full gap-4 mb-8 flex-wrap"):
        with ui.card().classes("w-full md:w-1/4 p-4 bg-blue-50 text-center"):
            ui.label(str(d["total_customers"])).classes("text-3xl font-bold text-blue-700")
            ui.label("Khách hàng").classes("text-sm text-blue-600")
        with ui.card().classes("w-full md:w-1/4 p-4 bg-green-50 text-center"):
            ui.label(str(d["total_drinks"])).classes("text-3xl font-bold text-green-700")
            ui.label("Đồ uống bán ra").classes("text-sm text-green-600")
        with ui.card().classes("w-full md:w-1/4 p-4 bg-yellow-50 text-center"):
            ui.label(str(d["today_tx"])).classes("text-3xl font-bold text-yellow-700")
            ui.label("Giao dịch hôm nay").classes("text-sm text-yellow-600")
        with ui.card().classes("w-full md:w-1/4 p-4 bg-purple-50 text-center"):
            ui.label(f"{d['today_revenue']:,.0f}đ").classes("text-3xl font-bold text-purple-700")
            ui.label("Doanh thu hôm nay").classes("text-sm text-purple-600")

    # Revenue summary
    with ui.row().classes("w-full gap-4 mb-8 flex-wrap"):
        with ui.card().classes("w-full md:w-1/2 p-4 bg-indigo-50"):
            ui.label("Doanh thu tuần này").classes("text-lg text-indigo-700")
            ui.label(f"{d['week_revenue']:,.0f}đ").classes("text-2xl font-bold text-indigo-800")
        with ui.card().classes("w-full md:w-1/2 p-4 bg-pink-50"):
            ui.label("Doanh thu tháng này").classes("text-lg text-pink-700")
            ui.label(f"{d['month_revenue']:,.0f}đ").classes("text-2xl font-bold text-pink-800")

    # Low stock alerts
    if d["low_stock_count"] > 0:
        with ui.card().classes("w-full p-4 mb-6 bg-red-50 border-2 border-red-300"):
            ui.label(f"!!! {d['low_stock_count']} nguyên liệu sắp HẾT!").classes("text-lg font-bold text-red-700")
            for p in d["low_stock_items"]:
                ui.label(f"* {p['name']}: còn {p['current_stock']:.0f} {p['unit']} (tối thiểu {p['min_stock']:.0f})").classes("text-sm text-red-600 ml-4")

    # Recent transactions
    with ui.row().classes("w-full items-center justify-between mb-4 flex-wrap gap-2"):
        ui.label("Giao dịch gần đây").classes("text-xl font-bold")
        ui.button("Xuất CSV", icon="download",
                  on_click=lambda: ui.navigate.to("/api/dashboard/transactions/export-csv", new_tab=True)).props("outlined").classes("text-sm")

    tx_table = ui.table(
        columns=[
            {"name": "time", "label": "Giờ", "field": "time"},
            {"name": "customer", "label": "Khách hàng", "field": "customer"},
            {"name": "drink", "label": "Đồ uống", "field": "drink"},
            {"name": "servings", "label": "Số ly", "field": "servings"},
            {"name": "amount", "label": "Doanh thu", "field": "amount"},
            {"name": "by", "label": "Nhân viên", "field": "by"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

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

    # Fraud alerts for MANAGER+
    if role in ("MANAGER", "OWNER"):
        ui.label("Giao dịch bất thường").classes("text-xl font-bold mt-8 mb-4")
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
            alert_table = ui.table(
                columns=[
                    {"name": "time", "label": "Giờ", "field": "time"},
                    {"name": "customer", "label": "Khách hàng", "field": "customer"},
                    {"name": "drink", "label": "Đồ uống", "field": "drink"},
                    {"name": "by", "label": "Nhân viên", "field": "by"},
                ],
                rows=[],
                row_key="id",
            ).classes("w-full overflow-x-auto")
            alert_table.rows = [
                {
                    "time": r["created_at"][11:19] if r["created_at"] else "",
                    "customer": f"{r['customer_code']} - {r['customer_name']}",
                    "drink": r["drink_name"],
                    "by": r["user_name"],
                }
                for r in suspicious
            ]
            alert_table.update()
        else:
            ui.label("OK - Không có giao dịch đáng ngờ hôm nay.").classes("text-green-600 italic")

    # Ingredient stock overview
    ui.label("Tổng quan tồn kho nguyên liệu").classes("text-xl font-bold mt-8 mb-4")

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
    ).classes("w-full overflow-x-auto")

    stock_table.rows = []
    for s in d["all_stock"]:
        if s["current_stock"] <= s["min_stock"]:
            status = "!!! THIẾU"
        elif s["current_stock"] <= s["min_stock"] * 2:
            status = "!! Cảnh báo"
        else:
            status = "OK"
        stock_table.rows.append({
            "id": s["name"],
            "name": s["name"],
            "unit": s["unit"],
            "stock": f"{s['current_stock']:.1f}",
            "min": f"{s['min_stock']:.1f}",
            "status": status,
        })
    stock_table.update()