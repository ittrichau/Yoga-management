"""Main entry point."""
from nicegui import ui

from database import init_db, seed_defaults
from auth import router as auth_router
from customer import router as customer_router
from drink import router as drink_router
from ingredient import router as ingredient_router
from package import router as package_router
from transaction import router as transaction_router
from audit import router as audit_router
from dashboard import router as dashboard_router

# Initialize database
init_db()
seed_defaults()

# Register API routers
from nicegui import app
app.include_router(auth_router)
app.include_router(customer_router)
app.include_router(drink_router)
app.include_router(ingredient_router)
app.include_router(package_router)
app.include_router(transaction_router)
app.include_router(audit_router)
app.include_router(dashboard_router)

# Dashboard page
@ui.page("/")
def index():
    """Redirect to dashboard."""
    from auth import get_current_location_id
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    if not get_current_location_id():
        ui.navigate.to("/select-location")
        return
    ui.navigate.to("/dashboard")

ui.run(
    title="Quản lý Dinh dưỡng Gym",
    favicon="🏋️",
    storage_secret="gym-nutrition-secret-key-change-me",
)