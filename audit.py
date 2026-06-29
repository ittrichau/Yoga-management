"""Audit log viewer."""
from fastapi import APIRouter, Depends
from nicegui import app, ui

from database import get_db
from auth import get_current_user, require_role, render_navbar

router = APIRouter(prefix="/api/audit", tags=["audit"])

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@router.get("/logs")
def list_logs(
    entity_type: str | None = None,
    action: str | None = None,
    limit: int = 100,
    user: dict = Depends(require_role("MANAGER")),
):
    """List audit logs. MANAGER+ only."""
    with get_db() as conn:
        where = []
        params = []
        if entity_type:
            where.append("al.entity_type = ?")
            params.append(entity_type)
        if action:
            where.append("al.action = ?")
            params.append(action)
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT al.*, u.username, u.full_name as user_full_name
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.user_id
                {where_clause}
                ORDER BY al.created_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]

ACTION_LABELS = {
    "create": "Tạo mới",
    "update": "Cập nhật",
    "deactivate": "Vô hiệu hóa",
    "checkin": "Check-in",
    "inventory_adjust": "Điều chỉnh tồn kho",
    "update_recipe": "Cập nhật công thức",
}

# ---------------------------------------------------------------------------
# NiceGUI UI
# ---------------------------------------------------------------------------
def render():
    """Render the audit log page."""
    role = app.storage.user.get("role", "STAFF")
    render_navbar()
    ui.label("Nhật ký kiểm toán").classes("text-2xl font-bold mb-4")

    with ui.row().classes("w-full items-center gap-2 md:gap-4 mb-4 flex-wrap"):
        entity_filter = ui.select(
            [""] + ["customer", "drink", "ingredient", "transaction", "package", "user"],
            label="Đối tượng",
            value="",
        ).props("outlined").classes("w-full md:w-48")
        action_filter = ui.select(
            [""] + list(ACTION_LABELS.keys()),
            label="Hành động",
            value="",
        ).props("outlined").classes("w-full md:w-48")

    log_table = ui.table(
        columns=[
            {"name": "date", "label": "Ngày", "field": "date"},
            {"name": "user", "label": "Người dùng", "field": "user"},
            {"name": "action", "label": "Hành động", "field": "action"},
            {"name": "entity", "label": "Đối tượng", "field": "entity"},
            {"name": "details", "label": "Chi tiết", "field": "details"},
        ],
        rows=[],
        row_key="id",
        pagination={"rowsPerPage": 20},
    ).classes("w-full overflow-x-auto")

    def refresh():
        with get_db() as conn:
            where = []
            params = []
            if entity_filter.value:
                where.append("al.entity_type = ?")
                params.append(entity_filter.value)
            if action_filter.value:
                where.append("al.action = ?")
                params.append(action_filter.value)
            where_clause = ("WHERE " + " AND ".join(where)) if where else ""
            rows = conn.execute(
                f"""SELECT al.*, u.username, u.full_name as user_full_name
                    FROM audit_logs al
                    LEFT JOIN users u ON u.id = al.user_id
                    {where_clause}
                    ORDER BY al.created_at DESC LIMIT 200""",
                params,
            ).fetchall()

        log_table.rows = [
            {
                "id": r["id"],
                "date": r["created_at"][:19],
                "user": r["user_full_name"] or r["username"] or "Hệ thống",
                "action": ACTION_LABELS.get(r["action"], r["action"]),
                "entity": f"{r['entity_type']}#{r['entity_id']}" if r["entity_id"] else r["entity_type"],
                "details": r["details"],
            }
            for r in rows
        ]
        log_table.update()

    entity_filter.on("update:model-value", refresh)
    action_filter.on("update:model-value", refresh)
    ui.button("Làm mới", on_click=refresh, icon="refresh").props("outlined").classes("mb-4")
    refresh()