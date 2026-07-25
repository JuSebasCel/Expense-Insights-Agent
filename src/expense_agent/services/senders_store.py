"""Persistencia simple (JSON) de los remitentes bancarios configurados por el usuario.

Arranca sembrado con `BANK_SENDERS` (los remitentes con evidencia real al momento de escribir
esto) para que instalaciones nuevas no empiecen vacías; a partir de ahí el usuario administra
la lista desde el front sin tocar código ni reiniciar el servidor.
"""

import json
import os

from expense_agent.core.config import BANK_SENDERS


def _read(path: str) -> list[str]:
    if not os.path.exists(path):
        return list(BANK_SENDERS)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path: str, senders: list[str]) -> None:
    db_dir = os.path.dirname(path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(senders, f, ensure_ascii=False, indent=2)


def load_senders(path: str) -> list[str]:
    return _read(path)


def add_sender(path: str, sender: str) -> list[str]:
    sender = sender.strip().lower()
    senders = _read(path)
    if sender and sender not in senders:
        senders.append(sender)
        _write(path, senders)
    return senders


def remove_sender(path: str, sender: str) -> list[str]:
    senders = [s for s in _read(path) if s != sender]
    _write(path, senders)
    return senders
