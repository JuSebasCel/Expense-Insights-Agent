"""Fixtures y dobles de prueba compartidos.

Nada aquí hace llamadas de red: la API de Gmail y el LLM se reemplazan por dobles simples que
devuelven respuestas predefinidas, para que los tests corran rápido y sin credenciales.
"""

import json
from pathlib import Path

import pytest

from expense_agent.models.state import RawEmail

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def bancolombia_emails() -> list[RawEmail]:
    data = json.loads((FIXTURES_DIR / "bancolombia_emails.json").read_text(encoding="utf-8"))
    return [RawEmail(**item) for item in data]


class FakeStructuredLLM:
    """Doble de un LLM ya "bindeado" a `with_structured_output(Schema)`.

    `responses` mapea una subcadena del prompt (ej. el nombre de un comercio) a la instancia
    pydantic que debe devolverse cuando esa subcadena aparece en el prompt.
    """

    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        for key, response in self.responses.items():
            if key in prompt:
                return response
        raise AssertionError(
            f"FakeStructuredLLM: no hay respuesta configurada para el prompt:\n{prompt}"
        )


class FakeChatModel:
    """Doble de `ChatGoogleGenerativeAI`: solo implementa `with_structured_output`."""

    def __init__(self, responses: dict[str, object]):
        self._responses = responses

    def with_structured_output(self, schema):  # noqa: ARG002 - firma compatible con el real
        return FakeStructuredLLM(self._responses)


@pytest.fixture
def fake_chat_model():
    return FakeChatModel


class FakeExecutable:
    def __init__(self, data: dict):
        self._data = data

    def execute(self):
        return self._data


class FakeMessagesResource:
    def __init__(self, emails_by_id: dict[str, RawEmail]):
        self._emails_by_id = emails_by_id

    def list(self, userId, q, pageToken=None):  # noqa: ARG002
        ids = list(self._emails_by_id.keys())
        return FakeExecutable({"messages": [{"id": message_id} for message_id in ids]})

    def get(self, userId, id, format):  # noqa: ARG002
        email = self._emails_by_id[id]
        return FakeExecutable(
            {
                "id": id,
                "snippet": email["body"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": email["sender"]},
                        {"name": "Date", "value": email["date"]},
                    ]
                },
            }
        )


class FakeUsersResource:
    def __init__(self, emails_by_id: dict[str, RawEmail]):
        self._messages = FakeMessagesResource(emails_by_id)

    def messages(self):
        return self._messages


class FakeGmailService:
    """Doble del objeto devuelto por `googleapiclient.discovery.build('gmail', 'v1', ...)`."""

    def __init__(self, emails: list[RawEmail]):
        self._users = FakeUsersResource({email["message_id"]: email for email in emails})

    def users(self):
        return self._users


@pytest.fixture
def fake_gmail_service_factory():
    return FakeGmailService
