from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import routes_import
from app.infra.db import close_pool, init_pool
from app.infra.mpxj import shutdown_jvm, start_jvm
from app.infra.storage import close_supabase_client, init_supabase_client

# Ponto de entrada da aplicação FastAPI: inicializa o app e registra os routers de api/v1


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_jvm()
    await init_pool()
    await init_supabase_client()
    yield
    close_supabase_client()
    await close_pool()
    shutdown_jvm()


app = FastAPI(lifespan=lifespan)
app.include_router(routes_import.router, prefix="/api/v1")
