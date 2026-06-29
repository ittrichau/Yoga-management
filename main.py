"""App startup, route registration, navbar."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from nicegui import ui
from nicegui import app as ng_app

from database import init_db, seed_defaults
from auth import router as auth_router
from customer import router as customer_router, render as render_customers
from drink import router as drink_router, render as render_drinks
from ingredient import router as ingredient_router, render as render_ingredients
from package import router as package_router, render as render_packages
from transaction import router as transaction_router, render as render_transactions
from audit import router as audit_router, render as render_audit
from dashboard import router as dashboard_router, render as render_dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    seed_defaults()
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(title="Quản lý Dinh dưỡng Yoga", version="0.2.0", lifespan=lifespan)
ui.run_with(
    app,
    title="Quản lý Dinh dưỡng Yoga",
    storage_secret=os.environ.get("STORAGE_SECRET", "gym-nutrition-secret"),
)
app.include_router(auth_router)
app.include_router(customer_router)
app.include_router(drink_router)
app.include_router(ingredient_router)
app.include_router(package_router)
app.include_router(transaction_router)
app.include_router(audit_router)
app.include_router(dashboard_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@ui.page("/")
def index():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    render_dashboard()


@ui.page("/customers")
def customers_page():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    render_customers()


@ui.page("/drinks")
def drinks_page():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    render_drinks()


@ui.page("/ingredients")
def ingredients_page():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    render_ingredients()


@ui.page("/packages")
def packages_page():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    render_packages()


@ui.page("/sales")
def sales_page():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    render_transactions()


@ui.page("/audit")
def audit_page():
    if not ng_app.storage.user.get("token"):
        ui.navigate.to("/login")
        return
    role = ng_app.storage.user.get("role", "STAFF")
    if role not in ("MANAGER", "OWNER"):
        ui.label("Từ chối truy cập. Chỉ MANAGER+ mới được xem.").classes("text-red-500 text-xl")
        return
    render_audit()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
