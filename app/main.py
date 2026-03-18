import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from db import init_db, seed_default_asset_groups
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from routers.api.app import router as app_api
from routers.pages.app import router as app_pages

load_dotenv()

log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            os.path.join(log_dir, "hodl_engine.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        ),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up: initializing resources")
    init_db()
    seed_default_asset_groups()

    yield

    logger.info("Shutting down: cleaning up resources")


app = FastAPI(title="Hodl Engine", lifespan=lifespan)

app.include_router(app_api)
app.include_router(app_pages)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return RedirectResponse(url="/portfolio")
