from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config.settings import CONSTANTS
from backend.services.conversation import process_message, process_selection
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


class SelectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    session_id: UUID
    request_id: UUID
    product_id: UUID
    selection_offer: UUID

    @field_validator('session_id', 'request_id', 'product_id', 'selection_offer', mode='before')
    @classmethod
    def parse_uuid(cls, value):
        return UUID(value) if isinstance(value, str) else value


def create_app(store=None):
    application = FastAPI(title=API['title'])
    application.state.sessions = store if store is not None else SessionStore()
    application.add_middleware(CORSMiddleware, allow_origins=API['cors_origins'],
                               allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @application.get(API['prefix'] + '/health')
    def health():
        return {'status': 'ok'}

    def execute(request, response, signature, handler):
        session_id = str(request.session_id or uuid4())
        request_id = str(request.request_id)
        response.headers['Cache-Control'] = 'no-store'
        try:
            with application.state.sessions.acquire(session_id) as session:
                if request_id in session.replies:
                    original, result = session.replies[request_id]
                    if original != signature:
                        raise HTTPException(409, CONSTANTS['messages']['request_id_conflict'])
                else:
                    try:
                        _, result = handler(session.conversation)
                    except ValueError as error:
                        raise HTTPException(409, str(error)) from None
                    if result['action'] != 'error':
                        session.replies[request_id] = (signature, result)
                        while len(session.replies) > API['cached_replies']:
                            session.replies.popitem(last=False)
                return {'session_id': session_id, 'result': result}
        except SessionCapacityError:
            raise HTTPException(503, CONSTANTS['messages']['session_capacity']) from None

    @application.post(API['prefix'] + '/chat')
    def chat(request: ChatRequest, response: Response):
        return execute(request, response, ('chat', request.message),
                       lambda state: process_message(state, request.message))

    @application.post(API['prefix'] + '/select')
    def select(request: SelectionRequest, response: Response):
        return execute(request, response, ('select', str(request.product_id), str(request.selection_offer)),
                       lambda state: process_selection(state, str(request.product_id), str(request.selection_offer)))

    return application


app = create_app()
