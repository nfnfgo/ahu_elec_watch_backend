from fastapi import FastAPI

from provider import ahu

# sub routers
from endpoints.info import infoRouter

app = FastAPI()
app.include_router(infoRouter, prefix="/info", tags=['Info'])


@app.get('/test')
async def test_get_ahu_data():
    return await ahu.get_record()
