from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infra.mpxj import shutdown_jvm, start_jvm

# Ponto de entrada da aplicação FastAPI: inicializa o app e registra os routers de api/v1


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_jvm()
    yield
    shutdown_jvm()


app = FastAPI(lifespan=lifespan)
