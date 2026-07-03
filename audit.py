"""Audit log viewer - filtered by location."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from nicegui import app, ui

from database import get_db
from auth import get_current_user, require_role, render_navbar, get_current_location_id

router = APIRouter(prefix="/api/audit", tags=["audit"])

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
ENTITY_LABELS = {
    "customer": "Khách hàng",
    "drink": "Đồ uống",
    "ingredient": "Nguyên liệu",
    "transaction": "Giao dịch",
    "package": "Gói trả trước",
    "user": "Người dùng",
    "location": "Cơ sở",
}

ACTION_LABELS = {
    "create": "Tạo mới",
    "update": "Cập nhật",
    "deactivate": "Vô hiệu hóa",
    "activate": "Kích hoạt",
    "checkin": "Check-in",
    "inventory_adjust": "Điều chỉnh tồn kho",
    "update_recipe": "Cập nhật công thức",
    "login": "Đăng nhập",
    "logout": "Đăng xuất",
}


def _resolve_entity_name(conn, entity_type: str, entity_id: int | None) -> str:
    """Lookup friendly name for an entity. Returns '' if not found."""
    if entity_id is None:
        return ""
    table_map = {
        "customer": ("customers", "full_name", "code"),
        "drink": ("drinks", "name", None),
        "ingredient": ("ingredients", "name", None),
        "transaction": ("transactions", "id", None),
        "package": ("packages", "name", None),
        "user": ("users", "username", "full_name"),
        "location": ("locations", "name", None),
    }
    info = table_map.get(entity_type)
    if not info:
        return ""
    table, col1, col2 = info
    try:
        row = conn.execute(f"SELECT {col1}{', ' + col2 if col2 else ''} FROM {table} WHERE id = ?", (entity_id,)).fetchone()
    except Exception:
        return ""
    if not row:
        return f"(đã xóa #{entity_id})"
    if col2:
        val = f"{row[col1]} ({row[col2]})" if row[col2] else row[col1]
    else:
        val = row[col1]
    return str(val)


def _format_details(details: str) -> str:
    """Parse JSON details into a readable string. Falls back to raw text."""
    if not details:
        return ""
    try:
        data = json.loads(details)
        if isinstance(data, dict):
            parts = []
            for k, v in data.items():
                parts.append(f"{k}: {v}")
            return " | ".join(parts)
        return str(data)
    except (json.JSONDecodeError, TypeError):
        return details


@router.get("/logs")
def list_logs(
    request: Request,
    entity_type: str | None = None,
    action: str | None = None,
    location_id: int | None = None,
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
    user: dict = Depends(require_role("MANAGER")),
):
    """List audit logs. MANAGER+ only (excluding user/location logs unless OWNER)."""
    with get_db() as conn:
        where = []
        params = []
        if location_id:
            where.append("al.location_id = ?")
            params.append(location_id)
        if entity_type:
            where.append("al.entity_type = ?")
            params.append(entity_type)
        if action:
            where.append("al.action = ?")
            params.append(action)
        if user_id:
            where.append("al.user_id = ?")
            params.append(user_id)
        if date_from:
            where.append("al.created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("al.created_at <= ?")
            params.append(date_to)
        # MANAGER không thấy log về user/location
        if user["role"] != "OWNER":
            where.append("al.entity_type NOT IN ('user', 'location')")
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT al.*, u.username, u.full_name as user_full_name
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.user_id
                {where_clause}
                ORDER BY al.created_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
        # Resolve entity names
        results = []
        for r in rows:
            d = dict(r)
            d["entity_name"] = _resolve_entity_name(conn, d["entity_type"], d["entity_id"])
            results.append(d)
    return results


@router.get("/users")
def list_users_for_filter(user: dict = Depends(require_role("MANAGER"))):
    """List users for filter dropdown."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, username, full_name FROM users WHERE is_active = 1 ORDER BY full_name, username").fetchall()
    return [dict(r) for r in rows]


@router.get("/summary-by-user")
def summary_by_user(
    location_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: dict = Depends(require_role("MANAGER")),
):
    """Aggregate count per user for the 'By user' tab."""
    with get_db() as conn:
        where = []
        params = []
        if location_id:
            where.append("al.location_id = ?")
            params.append(location_id)
        if date_from:
            where.append("al.created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("al.created_at <= ?")
            params.append(date_to)
        if user["role"] != "OWNER":
            where.append("al.entity_type NOT IN ('user', 'location')")
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT al.user_id, u.username, u.full_name, COUNT(*) as total,
                       MAX(al.created_at) as last_activity,
                       SUM(CASE WHEN al.action='create' THEN 1 ELSE 0 END) as creates,
                       SUM(CASE WHEN al.action='update' THEN 1 ELSE 0 END) as updates,
                       SUM(CASE WHEN al.action='deactivate' THEN 1 ELSE 0 END) as deactivates,
                       SUM(CASE WHEN al.action='inventory_adjust' THEN 1 ELSE 0 END) as adjusts
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.user_id
                {where_clause}
                GROUP BY al.user_id
                ORDER BY total DESC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/suspicious")
def list_suspicious(
    location_id: int | None = None,
    user: dict = Depends(require_role("MANAGER")),
):
    """Heuristic suspicious logs:
    - inventory_adjust between 22:00-06:00
    - deactivate by non-OWNER (data quality issue)
    - rapid activity: >20 transactions by 1 user in last 1 hour
    """
    with get_db() as conn:
        where = ["al.location_id = ?"] if location_id else []
        params = [location_id] if location_id else []
        if user["role"] != "OWNER":
            where.append("al.entity_type NOT IN ('user', 'location')")
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""

        # 1) Inventory adjust late at night
        night_rows = conn.execute(
            f"""SELECT al.*, u.username, u.full_name as user_full_name
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.user_id
                {where_clause + (' AND' if where_clause else 'WHERE')}
                   al.action = 'inventory_adjust'
                   AND (substr(al.created_at, 12, 2) >= '22' OR substr(al.created_at, 12, 2) < '06')
                ORDER BY al.created_at DESC LIMIT 50""",
            params,
        ).fetchall()

        # 2) Rapid transaction creation (>= 20 in last 1 hour per user)
        rapid_rows = conn.execute(
            f"""SELECT u.id as user_id, u.username, u.full_name, COUNT(*) as cnt, MAX(t.created_at) as last_time
                FROM transactions t
                JOIN users u ON u.id = t.created_by
                {'WHERE t.location_id = ?' if location_id else ''}
                {('AND' if location_id else 'WHERE')} t.created_at >= datetime('now','-1 hour','localtime')
                GROUP BY u.id
                HAVING cnt >= 20
                ORDER BY cnt DESC""",
            ([location_id] if location_id else []),
        ).fetchall()

        # 3) User changes by non-OWNER
        user_change_rows = []
        if user["role"] == "OWNER":
            user_change_rows = conn.execute(
                """SELECT al.*, u.username, u.full_name as user_full_name
                   FROM audit_logs al
                   LEFT JOIN users u ON u.id = al.user_id
                   WHERE al.entity_type IN ('user', 'location')
                   ORDER BY al.created_at DESC LIMIT 50"""
            ).fetchall()

    results = []
    for r in night_rows:
        d = dict(r)
        d["suspicious_type"] = "Điều chỉnh tồn kho ngoài giờ (22h-6h)"
        d["severity"] = "warning"
        results.append(d)
    for r in user_change_rows:
        d = dict(r)
        d["suspicious_type"] = f"Thay đổi {ENTITY_LABELS.get(d['entity_type'], d['entity_type'])}"
        d["severity"] = "info"
        results.append(d)
    for r in rapid_rows:
        results.append({
            "id": None,
            "created_at": r["last_time"],
            "user_id": r["user_id"],
            "username": r["username"],
            "user_full_name": r["full_name"],
            "action": "rapid_activity",
            "entity_type": "transaction",
            "entity_id": None,
            "details": f'{{"count_last_hour": {r["cnt"]}}}',
            "ip_address": "",
            "suspicious_type": f"Tạo {r['cnt']} giao dịch trong 1 giờ qua",
            "severity": "danger",
        })
    # Sort by created_at desc
    results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return results


@router.get("/entity-history/{entity_type}/{entity_id}")
def entity_history(
    entity_type: str,
    entity_id: int,
    user: dict = Depends(require_role("MANAGER")),
):
    """All audit logs touching a specific entity."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT al.*, u.username, u.full_name as user_full_name
               FROM audit_logs al
               LEFT JOIN users u ON u.id = al.user_id
               WHERE al.entity_type = ? AND al.entity_id = ?
               ORDER BY al.created_at DESC""",
            (entity_type, entity_id),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
@ui.page("/audit")
def audit_page():
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return
    render()


def render():
    """Render the audit log page."""
    role = app.storage.user.get("role", "STAFF")
    loc_id = get_current_location_id()
    is_owner = role == "OWNER"
    render_navbar()

    with ui.element("div").classes("page-container"):
        with ui.row().classes("items-center page-title w-full"):
            ui.label("📋").classes("text-2xl")
            ui.label("Nhật ký kiểm toán")

    # Load users for filter
    with get_db() as conn:
        users_rows = conn.execute(
            "SELECT id, username, full_name FROM users WHERE is_active = 1 ORDER BY full_name, username"
        ).fetchall()
    user_options = {"": "Tất cả"}
    for u in users_rows:
        label = u["full_name"] or u["username"]
        user_options[str(u["id"])] = label

    # Entity options (OWNER thấy thêm user/location)
    entity_options = ["customer", "drink", "ingredient", "transaction", "package"]
    if is_owner:
        entity_options += ["user", "location"]

    # Tabs: Tất cả / Theo nhân viên / Đáng ngờ
    with ui.element("div").classes("page-container"):
        with ui.tabs().classes("w-full mb-3") as tabs:
            tab_all = ui.tab("Tất cả", icon="list")
            tab_by_user = ui.tab("Theo nhân viên", icon="people")
            tab_suspicious = ui.tab("Đáng ngờ", icon="warning")

    with ui.tab_panels(tabs, value=tab_all).classes("w-full"):

        # ===================== Tab: Tất cả =====================
        with ui.tab_panel(tab_all):
            # Detail dialog (defined first so it is in scope for open_detail)
            with ui.dialog() as detail_dialog, ui.card().classes("p-6 w-full max-w-2xl relative"):
                with ui.element("div").classes("absolute top-2 right-2"):
                    ui.button(icon="close", on_click=detail_dialog.close).props("flat round dense").tooltip("Đóng")
                ui.label("Chi tiết nhật ký").classes("text-xl font-bold mb-4 pr-8")
                detail_container = ui.column().classes("w-full gap-2")
                ui.button("Đóng", on_click=detail_dialog.close, icon="close").props("outlined").classes("mt-4")

            with ui.element("div").classes("custom-card p-4 mb-3"):
                ui.label("🔍 Bộ lọc").classes("section-header")
                with ui.element("div").classes("grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2 mt-2"):
                    entity_filter = ui.select(
                        {"": "Tất cả", **{e: ENTITY_LABELS.get(e, e) for e in entity_options}},
                        label="Đối tượng",
                        value="",
                    ).props("outlined")
                    action_filter = ui.select(
                        {"": "Tất cả", **{k: v for k, v in ACTION_LABELS.items()}},
                        label="Hành động",
                        value="",
                    ).props("outlined")
                    user_filter = ui.select(
                        user_options,
                        label="Người dùng",
                        value="",
                    ).props("outlined")
                    date_from = ui.input("Từ ngày").props("outlined type=date")
                    date_to = ui.input("Đến ngày").props("outlined type=date")

            log_table = ui.table(
                columns=[
                    {"name": "date", "label": "Ngày", "field": "date"},
                    {"name": "user", "label": "Người dùng", "field": "user"},
                    {"name": "action", "label": "Hành động", "field": "action"},
                    {"name": "entity", "label": "Đối tượng", "field": "entity"},
                    {"name": "details", "label": "Chi tiết", "field": "details"},
                    {"name": "ip", "label": "IP", "field": "ip"},
                    {"name": "view", "label": "", "field": "view"},
                ],
                rows=[],
                row_key="id",
                pagination={"rowsPerPage": 25},
            ).classes("w-full overflow-x-auto")

            # Define functions before they are used.
            def refresh():
                try:
                    with get_db() as conn:
                        where = ["al.location_id = ?"]
                        params = [loc_id]
                        if entity_filter.value:
                            where.append("al.entity_type = ?")
                            params.append(entity_filter.value)
                        if action_filter.value:
                            where.append("al.action = ?")
                            params.append(action_filter.value)
                        if user_filter.value:
                            where.append("al.user_id = ?")
                            params.append(int(user_filter.value))
                        if date_from.value:
                            where.append("al.created_at >= ?")
                            params.append(date_from.value)
                        if date_to.value:
                            where.append("al.created_at < ?")
                            try:
                                dt = datetime.strptime(date_to.value, "%Y-%m-%d") + timedelta(days=1)
                                params.append(dt.strftime("%Y-%m-%d"))
                            except ValueError:
                                params.append(date_to.value)
                        if role != "OWNER":
                            where.append("al.entity_type NOT IN ('user', 'location')")
                        where_clause = "WHERE " + " AND ".join(where)
                        rows = conn.execute(
                            f"""SELECT al.*, u.username, u.full_name as user_full_name
                                FROM audit_logs al
                                LEFT JOIN users u ON u.id = al.user_id
                                {where_clause}
                                ORDER BY al.created_at DESC LIMIT 500""",
                            params,
                        ).fetchall()

                    table_rows = []
                    for r in rows:
                        entity_label = ENTITY_LABELS.get(r["entity_type"], r["entity_type"])
                        entity_name = ""
                        try:
                            entity_name = _resolve_entity_name(conn, r["entity_type"], r["entity_id"])
                        except Exception:
                            entity_name = ""
                        if entity_name:
                            entity_display = f"{entity_label}: {entity_name}"
                        elif r["entity_id"]:
                            entity_display = f"{entity_label} #{r['entity_id']}"
                        else:
                            entity_display = entity_label
                        table_rows.append({
                            "id": r["id"],
                            "date": r["created_at"][:19] if r["created_at"] else "",
                            "user": r["user_full_name"] or r["username"] or "Hệ thống",
                            "action": ACTION_LABELS.get(r["action"], r["action"]),
                            "entity": entity_display,
                            "details": _format_details(r["details"]),
                            "ip": r["ip_address"] or "",
                            "view": r["id"],
                            "raw_entity_type": r["entity_type"],
                            "raw_entity_id": r["entity_id"],
                        })
                    log_table.rows = table_rows
                    log_table.update()
                except Exception as exc:
                    ui.notify(f"Lỗi tải nhật ký: {exc}", type="negative")

            def clear_filters():
                entity_filter.value = ""
                action_filter.value = ""
                user_filter.value = ""
                date_from.value = ""
                date_to.value = ""
                refresh()

            def open_detail(log_id):
                row = next((r for r in log_table.rows if r["id"] == log_id), None)
                if not row:
                    return
                detail_container.clear()
                with detail_container:
                    with ui.row().classes("w-full gap-2"):
                        ui.icon("schedule").classes("text-gray-500")
                        ui.label(row["date"]).classes("font-bold")
                    with ui.row().classes("w-full gap-2"):
                        ui.icon("person").classes("text-gray-500")
                        ui.label(f"{row.get('user', '')}").classes("font-bold")
                    with ui.row().classes("w-full gap-2"):
                        ui.icon("flash_on").classes("text-gray-500")
                        ui.label(row["action"]).classes("font-bold text-blue-600")
                    with ui.row().classes("w-full gap-2"):
                        ui.icon("category").classes("text-gray-500")
                        ui.label(row["entity"]).classes("font-bold")
                    if row.get("details"):
                        ui.separator()
                        ui.label("Chi tiết:").classes("text-sm font-bold text-gray-600")
                        ui.label(row["details"]).classes("text-sm break-words")
                    if row.get("ip"):
                        ui.separator()
                        ui.label(f"IP: {row['ip']}").classes("text-xs text-gray-500")
                    ui.separator()
                    ui.button(
                        "Xem tất cả log của đối tượng này",
                        icon="history",
                        on_click=lambda: open_entity_history(row["raw_entity_type"], row["raw_entity_id"]),
                    ).props("outlined").classes("w-full mt-2")
                detail_dialog.open()

            def open_entity_history(et, eid):
                detail_dialog.close()
                if et and eid:
                    with get_db() as conn:
                        name = _resolve_entity_name(conn, et, int(eid))
                    entity_filter.value = et
                    user_filter.value = ""
                    action_filter.value = ""
                    refresh()
                    ui.notify(f"Đang lọc log của {ENTITY_LABELS.get(et, et)}: {name}", type="info")

            # Action buttons row (defined after functions to be safe)
            with ui.row().classes("gap-2 mt-2 mb-2"):
                ui.button("Làm mới", on_click=refresh, icon="refresh").props("unelevated").classes("btn-primary")
                ui.button("Xóa bộ lọc", on_click=clear_filters, icon="clear").props("outlined")

            log_table.add_slot(
                "body-cell-view",
                """
                <q-td :props="props" auto-width>
                    <q-btn flat round dense icon="visibility" color="blue"
                           @click="$parent.$emit('view_log', props.row.id)">
                        <q-tooltip>Xem chi tiết</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )
            log_table.on("view_log", lambda e: open_detail(e.args))

            entity_filter.on("update:model-value", refresh)
            action_filter.on("update:model-value", refresh)
            user_filter.on("update:model-value", refresh)
            date_from.on("update:model-value", refresh)
            date_to.on("update:model-value", refresh)
            refresh()

        # ===================== Tab: Theo nhân viên =====================
        with ui.tab_panel(tab_by_user):
            with ui.element("div").classes("custom-card p-4 mb-3"):
                ui.label("📊 Tổng hợp hoạt động theo nhân viên").classes("section-header")
            with ui.row().classes("w-full gap-2 mb-2 flex-wrap"):
                sum_from = ui.input("Từ ngày").props("outlined type=date")
                sum_to = ui.input("Đến ngày").props("outlined type=date")

            summary_table = ui.table(
                columns=[
                    {"name": "user", "label": "Nhân viên", "field": "user"},
                    {"name": "total", "label": "Tổng log", "field": "total"},
                    {"name": "creates", "label": "Tạo mới", "field": "creates"},
                    {"name": "updates", "label": "Cập nhật", "field": "updates"},
                    {"name": "deactivates", "label": "Vô hiệu hóa", "field": "deactivates"},
                    {"name": "adjusts", "label": "Điều chỉnh kho", "field": "adjusts"},
                    {"name": "last", "label": "Hoạt động cuối", "field": "last"},
                ],
                rows=[],
                row_key="user_id",
                pagination={"rowsPerPage": 20},
            ).classes("w-full overflow-x-auto")

            def refresh_summary():
                with get_db() as conn:
                    where = ["al.location_id = ?"] if loc_id else []
                    params = [loc_id] if loc_id else []
                    if sum_from.value:
                        where.append("al.created_at >= ?")
                        params.append(sum_from.value)
                    if sum_to.value:
                        try:
                            dt = datetime.strptime(sum_to.value, "%Y-%m-%d") + timedelta(days=1)
                            params.append(dt.strftime("%Y-%m-%d"))
                        except ValueError:
                            params.append(sum_to.value)
                        where.append("al.created_at < ?")
                    if role != "OWNER":
                        where.append("al.entity_type NOT IN ('user', 'location')")
                    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
                    rows = conn.execute(
                        f"""SELECT al.user_id, u.username, u.full_name, COUNT(*) as total,
                                   MAX(al.created_at) as last_activity,
                                   SUM(CASE WHEN al.action='create' THEN 1 ELSE 0 END) as creates,
                                   SUM(CASE WHEN al.action='update' THEN 1 ELSE 0 END) as updates,
                                   SUM(CASE WHEN al.action='deactivate' THEN 1 ELSE 0 END) as deactivates,
                                   SUM(CASE WHEN al.action='inventory_adjust' THEN 1 ELSE 0 END) as adjusts
                            FROM audit_logs al
                            LEFT JOIN users u ON u.id = al.user_id
                            {where_clause}
                            GROUP BY al.user_id
                            ORDER BY total DESC""",
                        params,
                    ).fetchall()
                summary_table.rows = [
                    {
                        "user_id": r["user_id"] or 0,
                        "user": r["user_full_name"] or r["username"] or "Hệ thống",
                        "total": r["total"],
                        "creates": r["creates"] or 0,
                        "updates": r["updates"] or 0,
                        "deactivates": r["deactivates"] or 0,
                        "adjusts": r["adjusts"] or 0,
                        "last": (r["last_activity"] or "")[:19],
                    }
                    for r in rows
                ]
                summary_table.update()

            sum_from.on("update:model-value", refresh_summary)
            sum_to.on("update:model-value", refresh_summary)
            refresh_summary()

        # ===================== Tab: Đáng ngờ =====================
        with ui.tab_panel(tab_suspicious):
            with ui.element("div").classes("custom-card p-4 mb-3"):
                ui.label("⚠️ Các hành động đáng ngờ").classes("section-header")
            with ui.row().classes("w-full gap-2 mb-2"):
                with get_db() as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) as c FROM audit_logs WHERE location_id = ? AND action = 'inventory_adjust' AND (substr(created_at, 12, 2) >= '22' OR substr(created_at, 12, 2) < '06')",
                        (loc_id,),
                    ).fetchone()
                ui.label(f"🌙 Điều chỉnh kho ngoài giờ (22h-6h): {count['c'] if count else 0}").classes("text-sm")

            sus_table = ui.table(
                columns=[
                    {"name": "date", "label": "Thời gian", "field": "date"},
                    {"name": "user", "label": "Người dùng", "field": "user"},
                    {"name": "type", "label": "Loại cảnh báo", "field": "type"},
                    {"name": "action", "label": "Hành động", "field": "action"},
                    {"name": "details", "label": "Chi tiết", "field": "details"},
                    {"name": "severity", "label": "Mức độ", "field": "severity"},
                ],
                rows=[],
                row_key="id",
                pagination={"rowsPerPage": 25},
            ).classes("w-full overflow-x-auto")

            def refresh_suspicious():
                with get_db() as conn:
                    night_rows = conn.execute(
                        """SELECT al.*, u.username, u.full_name as user_full_name
                           FROM audit_logs al
                           LEFT JOIN users u ON u.id = al.user_id
                           WHERE al.location_id = ?
                             AND al.action = 'inventory_adjust'
                             AND (substr(al.created_at, 12, 2) >= '22'
                                  OR substr(al.created_at, 12, 2) < '06')
                           ORDER BY al.created_at DESC LIMIT 50""",
                        (loc_id,),
                    ).fetchall()
                    rapid_rows = conn.execute(
                        """SELECT u.id as user_id, u.username, u.full_name,
                                  COUNT(*) as cnt, MAX(t.created_at) as last_time
                           FROM transactions t
                           JOIN users u ON u.id = t.created_by
                           WHERE t.location_id = ?
                             AND t.created_at >= datetime('now','-1 hour','localtime')
                           GROUP BY u.id
                           HAVING cnt >= 20
                           ORDER BY cnt DESC""",
                        (loc_id,),
                    ).fetchall()
                    user_change_rows = []
                    if is_owner:
                        user_change_rows = conn.execute(
                            """SELECT al.*, u.username, u.full_name as user_full_name
                               FROM audit_logs al
                               LEFT JOIN users u ON u.id = al.user_id
                               WHERE al.entity_type IN ('user', 'location')
                               ORDER BY al.created_at DESC LIMIT 50"""
                        ).fetchall()

                rows = []
                for r in night_rows:
                    rows.append({
                        "id": r["id"],
                        "date": r["created_at"][:19] if r["created_at"] else "",
                        "user": r["user_full_name"] or r["username"] or "Hệ thống",
                        "type": "Điều chỉnh kho ngoài giờ (22h-6h)",
                        "action": ACTION_LABELS.get(r["action"], r["action"]),
                        "details": _format_details(r["details"]),
                        "severity": "⚠️ Cảnh báo",
                    })
                for r in user_change_rows:
                    rows.append({
                        "id": r["id"],
                        "date": r["created_at"][:19] if r["created_at"] else "",
                        "user": r["user_full_name"] or r["username"] or "Hệ thống",
                        "type": f"Thay đổi {ENTITY_LABELS.get(r['entity_type'], r['entity_type'])}",
                        "action": ACTION_LABELS.get(r["action"], r["action"]),
                        "details": _format_details(r["details"]),
                        "severity": "ℹ️ Thông tin",
                    })
                for r in rapid_rows:
                    rows.append({
                        "id": None,
                        "date": (r["last_time"] or "")[:19],
                        "user": r["full_name"] or r["username"] or "Hệ thống",
                        "type": "Tạo nhiều giao dịch",
                        "action": f"{r['cnt']} giao dịch/giờ",
                        "details": f"Phát hiện {r['cnt']} giao dịch trong 1 giờ qua",
                        "severity": "🚨 Nghiêm trọng",
                    })
                rows.sort(key=lambda x: x["date"], reverse=True)
                sus_table.rows = rows
                sus_table.update()

            ui.button("Làm mới", on_click=refresh_suspicious, icon="refresh").props("outlined").classes("mb-2")
            refresh_suspicious()