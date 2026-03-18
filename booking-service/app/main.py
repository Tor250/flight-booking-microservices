from fastapi import FastAPI
from app.routes import router
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    force=True
)


app = FastAPI()
app.include_router(router)