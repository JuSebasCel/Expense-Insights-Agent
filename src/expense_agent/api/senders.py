"""Rutas HTTP para que el usuario administre, desde el front, los remitentes bancarios que
el agente busca en Gmail (evita tener que tocar código cuando aparece un banco nuevo)."""

from fastapi import APIRouter
from pydantic import BaseModel

from expense_agent.core.config import get_settings
from expense_agent.services.senders_store import add_sender, load_senders, remove_sender

router = APIRouter(prefix="/senders")


class SenderPayload(BaseModel):
    sender: str


@router.get("")
def list_senders() -> list[str]:
    settings = get_settings()
    return load_senders(settings.senders_db_path)


@router.post("")
def create_sender(payload: SenderPayload) -> list[str]:
    settings = get_settings()
    return add_sender(settings.senders_db_path, payload.sender)


@router.delete("/{sender}")
def delete_sender(sender: str) -> list[str]:
    settings = get_settings()
    return remove_sender(settings.senders_db_path, sender)
