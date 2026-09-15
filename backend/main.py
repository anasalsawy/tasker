import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routers.apps.auth import router as userauth_router
from routers.aiagent.generic import router as aiagent_router
from routers.apps.threads import router as threads_router
from routers.aiagent.suggestor import router as suggestor_aiagent_router
from routers.aiagent.background import router as bg_mode_aiagent_router
from utils.procedures import CustomError

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(
    title='NeuralAgent'
)

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
