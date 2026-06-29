"""Dashboard with revenue stats, ingredient stock, and fraud alerts."""
import csv
import io
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from nicegui import ui, app

from database import get_db
from auth import get_current_user, require_role, render_navbar

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ---------------------------------------------------------------------------
# Helpers: date boundaries computed in Python (works on SQLite AND PostgreSQL)
# ---------------------------------------------------------------------------
def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _week_ago_str() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

def _this_month_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@router.get("/stats")
def get_stats(user: dict = Depends(get_current_user)):
    """Get dashboard statistics."""
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
    """Get potential fraud alerts."""
    today = _today_str() + "%"
    alerts = []
    with get_db() as conn:
        # Transactions with no package and no amount (should not happen)
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
                "message": f"Ban {r['drink_name']} cho {r['customer_name']} khong co goi, khong thu tien!",
                "created_at": r["created_at"],
            })

        # Many transactions by same user in short time
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
                "message": f"{r['user_name']} da ban {r['cnt']} ly hom nay (cao bat thuong)",
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
    """Export transactions to CSV."""
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
                       u.full_name as created_by_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN drinks d ON d.id = t.drink_id
                JOIN users u ON u.id = t.created_by
                {where_clause}
                ORDER BY t.created_at DESC""",
            params,
        ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Ngay", "Ma KH", "Ten KH", "Do uong", "So ly", "Doanh thu", "Ghi chu", "Nhan vien"])
    for r in rows:
        writer.writerow([r["id"], r["created_at"], r["customer_code"], r["customer_name"],
                        r["drink_name"], r["servings"], r["amount"], r["notes"], r["created_by_name"]])
    output.seek(0)
    filename = f"transactions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def render():
    """Render the dashboard page."""
    role = app.storage.user.get("role", "STAFF")
    render_navbar()
    ui.label("Bang dieu khien").classes("text-2xl font-bold mb-4")

    today_prefix = _today_str() + "%"
    week_ago = _week_ago_str()
    month_prefix = _this_month_prefix() + "%"

    d = {}
    with get_db() as conn:
        d["total_customers"] = conn.execute("SELECT COUNT(*) as cnt FROM customers WHERE is_active = 1").fetchone()["cnt"]
        d["total_drinks"] = conn.execute("SELECT COUNT(*) as cnt FROM drinks WHERE is_active = 1").fetchone()["cnt"]
        d["today_tx"] = conn.execute("SELECT COUNT(*) as cnt FROM transactions WHERE created_at LIKE ?", (today_prefix,)).fetchone()["cnt"]
        d["today_revenue"] = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at LIKE ?", (today_prefix,)).fetchone()["total"]
        d["week_revenue"] = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at >= ?", (week_ago,)).fetchone()["total"]
        d["month_revenue"] = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE created_at LIKE ?", (month_prefix,)).fetchone()["total"]

        d["low_stock_count"] = conn.execute("SELECT COUNT(*) as cnt FROM ingredients WHERE is_active = 1 AND current_stock <= min_stock").fetchone()["cnt"]
        d["low_stock_items"] = conn.execute("SELECT name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 AND current_stock <= min_stock ORDER BY name").fetchall()

        d["recent_tx"] = conn.execute(
            """SELECT t.*, c.full_name as customer_name, c.code as customer_code,
                       d.name as drink_name, u.full_name as user_name
                FROM transactions t
                JOIN customers c ON c.id = t.customer_id
                JOIN drinks d ON d.id = t.drink_id
                JOIN users u ON u.id = t.created_by
                ORDER BY t.created_at DESC LIMIT 5"""
        ).fetchall()

        d["all_stock"] = conn.execute("SELECT name, unit, current_stock, min_stock FROM ingredients WHERE is_active = 1 ORDER BY name").fetchall()

    # Stats cards
    with ui.row().classes("w-full gap-4 mb-8 flex-wrap"):
        with ui.card().classes("w-full md:w-1/4 p-4 bg-blue-50 text-center"):
            ui.label(str(d["total_customers"])).classes("text-3xl font-bold text-blue-700")
            ui.label("Khach hang").classes("text-sm text-blue-600")
        with ui.card().classes("w-full md:w-1/4 p-4 bg-green-50 text-center"):
            ui.label(str(d["total_drinks"])).classes("text-3xl font-bold text-green-700")
            ui.label("Do uong ban ra").classes("text-sm text-green-600")
        with ui.card().classes("w-full md:w-1/4 p-4 bg-yellow-50 text-center"):
            ui.label(str(d["today_tx"])).classes("text-3xl font-bold text-yellow-700")
            ui.label("Giao dich hom nay").classes("text-sm text-yellow-600")
        with ui.card().classes("w-full md:w-1/4 p-4 bg-purple-50 text-center"):
            ui.label(f"{d['today_revenue']:,.0f}d").classes("text-3xl font-bold text-purple-700")
            ui.label("Doanh thu hom nay").classes("text-sm text-purple-600")

    # Revenue summary
    with ui.row().classes("w-full gap-4 mb-8 flex-wrap"):
        with ui.card().classes("w-full md:w-1/2 p-4 bg-indigo-50"):
            ui.label("Doanh thu tuan nay").classes("text-lg text-indigo-700")
            ui.label(f"{d['week_revenue']:,.0f}d").classes("text-2xl font-bold text-indigo-800")
        with ui.card().classes("w-full md:w-1/2 p-4 bg-pink-50"):
            ui.label("Doanh thu thang nay").classes("text-lg text-pink-700")
            ui.label(f"{d['month_revenue']:,.0f}d").classes("text-2xl font-bold text-pink-800")

    # Low stock alerts
    if d["low_stock_count"] > 0:
        with ui.card().classes("w-full p-4 mb-6 bg-red-50 border-2 border-red-300"):
            ui.label(f"!!! {d['low_stock_count']} nguyen lieu sap HET!").classes("text-lg font-bold text-red-700")
            for p in d["low_stock_items"]:
                ui.label(f"* {p['name']}: con {p['current_stock']:.0f} {p['unit']} (toi thieu {p['min_stock']:.0f})").classes("text-sm text-red-600 ml-4")

    # Recent transactions
    with ui.row().classes("w-full items-center justify-between mb-4 flex-wrap gap-2"):
        ui.label("Giao dich gan day").classes("text-xl font-bold")
        ui.button("Xuat CSV", icon="download", on_click=lambda: ui.navigate.to("/api/dashboard/transactions/export-csv", new_tab=True)).props("outlined").classes("text-sm")

    tx_table = ui.table(
        columns=[
            {"name": "time", "label": "Gio", "field": "time"},
            {"name": "customer", "label": "Khach hang", "field": "customer"},
            {"name": "drink", "label": "Do uong", "field": "drink"},
            {"name": "servings", "label": "Ly", "field": "servings"},
            {"name": "amount", "label": "Doanh thu", "field": "amount"},
            {"name": "by", "label": "Nhan vien", "field": "by"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    tx_table.rows = [
        {
            "id": r["id"],
            "time": r["created_at"][11:19],
            "customer": f"{r['customer_code']} - {r['customer_name']}",
            "drink": r["drink_name"],
            "servings": r["servings"],
            "amount": f"{r['amount']:,.0f}d" if r["amount"] > 0 else "📦",
            "by": r["user_name"],
        }
        for r in d["recent_tx"]
    ]
    tx_table.update()

    # Fraud alerts for MANAGER+
    if role in ("MANAGER", "OWNER"):
        ui.label("Canh bao gian lan").classes("text-xl font-bold mt-8 mb-4")
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
                (today_prefix,),
            ).fetchall()
        if suspicious:
            alert_table = ui.table(
                columns=[
                    {"name": "time", "label": "Gio", "field": "time"},
                    {"name": "customer", "label": "Khach hang", "field": "customer"},
                    {"name": "drink", "label": "Do uong", "field": "drink"},
                    {"name": "by", "label": "Nhan vien", "field": "by"},
                ],
                rows=[],
                row_key="id",
            ).classes("w-full overflow-x-auto")
            alert_table.rows = [
                {
                    "time": r["created_at"][11:19],
                    "customer": f"{r['customer_code']} - {r['customer_name']}",
                    "drink": r["drink_name"],
                    "by": r["user_name"],
                }
                for r in suspicious
            ]
            alert_table.update()
        else:
            ui.label("OK Khong co giao dich dang ngo hom nay.").classes("text-green-600 italic")

    # Ingredient stock overview
    ui.label("Tong quan ton kho nguyen lieu").classes("text-xl font-bold mt-8 mb-4")

    stock_table = ui.table(
        columns=[
            {"name": "name", "label": "Nguyen lieu", "field": "name"},
            {"name": "unit", "label": "Don vi", "field": "unit"},
            {"name": "stock", "label": "Ton kho", "field": "stock"},
            {"name": "min", "label": "Toi thieu", "field": "min"},
            {"name": "status", "label": "Trang thai", "field": "status"},
        ],
        rows=[],
        row_key="id",
    ).classes("w-full overflow-x-auto")

    stock_table.rows = []
    for s in d["all_stock"]:
        if s["current_stock"] <= s["min_stock"]:
            status = "!!! THIEU"
        elif s["current_stock"] <= s["min_stock"] * 2:
            status = "!! Canh bao"
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