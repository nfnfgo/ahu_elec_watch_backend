from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import HTTPException
from fastapi.exception_handlers import http_exception_handler

import uvicorn

from exception.error import BaseError, BaseErrorOut

import config
from provider import ahu

# sub routers
from endpoints.info import infoRouter

# CORS
middlewares = [
    Middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = FastAPI(middleware=middlewares)
app.include_router(infoRouter, prefix="/info", tags=['Info'])


@app.get('/test')
async def test_get_ahu_data():
    return await ahu.get_record()


@app.get('/test_error')
async def test_error_handling(name: str, message: str, status: int):
    raise BaseError(name, message, status)


@app.exception_handler(BaseError)
async def base_error_handler(request: Request, exc: BaseError):
    return await http_exception_handler(request, HTTPException(
        status_code=exc.status,
        detail=exc.to_pydantic_base_error().model_dump()
    ))


# Start uvicorn server
if __name__ == "__main__":
    # determine host
    host = '127.0.0.1'
    if config.general.ON_CLOUD:
        host = '0.0.0.0'

    # start uvicorn server with directory monitor
    uvicorn.run(
        app="main:app",
        host='0.0.0.0',
        port=config.general.PORT,
        reload=True,
        server_header=False,
    )
