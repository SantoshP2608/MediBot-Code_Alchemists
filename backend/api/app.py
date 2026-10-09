from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config.settings import CONSTANTS
from backend.services.conversation import process_message
from backend.services.sessions import SessionCapacityError, SessionStore

API = CONSTANTS['api']


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    message: str = Field(min_length=1, max_length=API['max_message_length'])
    session_id: UUID | None = None
    request_id: UUID

    @field_validator('session_id', 'request_id', mode='before')
    @classmethod
    def parse_uuid(cls, value):
        return UUID(value) if isinstance(value, str) else value

    @field_validator('message')
    @classmethod
    def clean_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError(CONSTANTS['messages']['empty_chat_message'])
        return value


def create_app(store=None):
    application = FastAPI(title=API['title'])
    application.state.sessions = store if store is not None else SessionStore()
    application.add_middleware(CORSMiddleware, allow_origins=API['cors_origins'],
                               allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @application.get(API['prefix'] + '/health')
    def health():
        return {'status': 'ok'}

    @application.post(API['prefix'] + '/chat')
    def chat(request: ChatRequest, response: Response):
        session_id = str(request.session_id or uuid4())
        request_id = str(request.request_id)
        response.headers['Cache-Control'] = 'no-store'
        try:
            with application.state.sessions.acquire(session_id) as session:
                if request_id in session.replies:
                    original, result = session.replies[request_id]
                    if original != request.message:
                        raise HTTPException(409, CONSTANTS['messages']['request_id_conflict'])
                else:
                    _, result = process_message(session.conversation, request.message)
                    if result['action'] != 'error':
                        session.replies[request_id] = (request.message, result)
                        while len(session.replies) > API['cached_replies']:
                            session.replies.popitem(last=False)
                return {'session_id': session_id, 'result': result}
        except SessionCapacityError:
            raise HTTPException(503, CONSTANTS['messages']['session_capacity']) from None

    return application


app = create_app()
