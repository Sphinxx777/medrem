from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import api_router

app = FastAPI(title="MedRem – рецепт → календарь")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router)

Path("static/ics").mkdir(parents=True, exist_ok=True)
Path("static/qr").mkdir(parents=True, exist_ok=True)
