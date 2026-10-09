import uvicorn
from backend.config.settings import CONSTANTS

if __name__ == '__main__':
    uvicorn.run('backend.api.app:app', host=CONSTANTS['api']['host'], port=CONSTANTS['api']['port'])
