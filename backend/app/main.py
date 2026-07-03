from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import routes_import, routes_users
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

# Primeira vez que o frontend (localhost:3000) chama este backend direto
# (ver frontend/lib/api/backend-client.ts) — precisa de CORS liberado pro
# preflight (OPTIONS) não ser rejeitado. Só dev por enquanto; produção vai
# precisar de uma origem real configurável.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_import.router, prefix="/api/v1")
app.include_router(routes_users.router, prefix="/api/v1")
