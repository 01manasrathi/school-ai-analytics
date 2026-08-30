from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import auth
from ..agent import agent as agent_module
from ..schemas import ChatMessage

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat")
def chat(payload: ChatMessage, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    try:
        result = agent_module.chat(payload.message, payload.history)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AI agent error: {e}. Is Ollama running?")
    return result
