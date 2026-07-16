"""Main entry point."""
import os
from pathlib import Path

from nicegui import ui, app

from database import init_db, migrate_schema, seed_defaults
from auth import navigate_with_loading, router as auth_router
from customer import router as customer_router
from checkin import router as checkin_router
from drink import router as drink_router
from ingredient import router as ingredient_router
from package import router as package_router
from package_template import router as package_template_router
from package_upgrade import router as package_upgrade_router
from product import router as product_router
from transaction import router as transaction_router
from audit import router as audit_router
from dashboard import router as dashboard_router
from pt import router as pt_router


@ui.page("/")
def index():
    """Redirect to dashboard."""
    from auth import get_current_location_id
    if not app.storage.user.get("token"):
        navigate_with_loading("/login", "Đang tải trang đăng nhập...")
        return
    if not get_current_location_id():
        navigate_with_loading("/select-location", "Đang tải trang chọn cơ sở...")
        return
    navigate_with_loading("/dashboard", "Đang mở trang chính...")


# Allow running under both `python main.py` and multiprocessing contexts
# (e.g. uvicorn workers, Render's WEB_CONCURRENCY).
if __name__ in {"__main__", "__mp_main__"}:
    # Initialize database
    init_db()
    migrate_schema()
    seed_defaults()

    # Register API routers
    app.include_router(auth_router)
    app.include_router(customer_router)
    app.include_router(checkin_router)
    app.include_router(drink_router)
    app.include_router(ingredient_router)
    app.include_router(package_router)
    app.include_router(package_template_router)
    app.include_router(package_upgrade_router)
    app.include_router(product_router)
    app.include_router(transaction_router)
    app.include_router(audit_router)
    app.include_router(dashboard_router)
    app.include_router(pt_router)

    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    # Mount static files for custom CSS
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.add_static_files("/static", static_dir)

    # Viewport meta tag for mobile responsiveness
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0">', shared=True)

    ui.run(
        host=host,
        port=port,
        title="Fitness and yoga Bảo Ngọc",
        favicon="/static/bao_ngoc_logo.png",
        storage_secret="gym-nutrition-secret-key-change-me",
        reload=False,
        show=False,
    )
