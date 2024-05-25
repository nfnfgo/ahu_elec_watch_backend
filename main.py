from fastapi import FastAPI
import uvicorn

import config
from provider import ahu

# sub routers
from endpoints.info import infoRouter

app = FastAPI()
app.include_router(infoRouter, prefix="/info", tags=['Info'])


@app.get('/test')
async def test_get_ahu_data():
    return await ahu.get_record()


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
