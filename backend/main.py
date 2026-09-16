import datetime
import os
from fastapi import FastAPI, Request
from sqlmodel import SQLModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routers.apps.auth import router as userauth_router
from routers.aiagent.generic import router as aiagent_router
from routers.aiagent.dual_lobe import router as dual_lobe_router
from routers.apps.threads import router as threads_router
from routers.aiagent.suggestor import router as suggestor_aiagent_router
from routers.aiagent.background import router as bg_mode_aiagent_router
from utils.procedures import CustomError
from db.database import DATABASE_URL, engine

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(
    title='Tasker'
)


@app.on_event('startup')
def create_local_development_schema():
    dev_bypass = os.getenv('TASKER_DEV_AUTH_BYPASS', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if dev_bypass and DATABASE_URL.startswith('sqlite'):
        SQLModel.metadata.create_all(engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        '*',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.exception_handler(CustomError)
async def custom_http_exception_handler(request: Request, exc: CustomError):
    return JSONResponse(
        status_code=exc.status_code,
        content={'message': exc.message},
    )


app.include_router(userauth_router)
app.include_router(threads_router)
app.include_router(suggestor_aiagent_router)
app.include_router(bg_mode_aiagent_router)
app.include_router(aiagent_router)
app.include_router(dual_lobe_router)

# @app.on_event('startup')
# async def startup():
#     await broadcast.connect()
#
#
# @app.on_event('shutdown')
# async def shutdown():
#     await broadcast.disconnect()


@app.get('/')
async def index():
    return {'message': datetime.datetime.now()}
