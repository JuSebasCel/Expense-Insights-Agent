"""Cliente de Gmail: OAuth de solo lectura + búsqueda de correos bancarios."""

import os
from datetime import date, timedelta
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from expense_agent.core.config import Settings
from expense_agent.models.state import RawEmail

# Solo lectura: el agente nunca necesita enviar, borrar ni modificar correos.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_credentials(settings: Settings) -> Credentials:
    creds: Credentials | None = None

    if os.path.exists(settings.gmail_token_path):
        creds = Credentials.from_authorized_user_file(settings.gmail_token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.gmail_credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(settings.gmail_token_path), exist_ok=True)
        with open(settings.gmail_token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


def build_gmail_service(settings: Settings):
    creds = get_credentials(settings)
    return build("gmail", "v1", credentials=creds)


def _build_query(senders: list[str], date_after: str, date_before: str) -> str:
    sender_group = "{" + " ".join(f"from:{sender}" for sender in senders) + "}"
    # Gmail espera las fechas como YYYY/MM/DD; el resto del sistema usa ISO (YYYY-MM-DD).
    gmail_after = date_after.replace("-", "/")
    # El "before:" de Gmail excluye el día indicado (corta a las 00:00 de esa fecha), pero
    # `date_before` se trata como fecha límite inclusiva en el resto del sistema (así lo
    # espera el front: "Hasta" = último día a incluir). Sumamos un día para compensar.
    inclusive_before = date.fromisoformat(date_before) + timedelta(days=1)
    gmail_before = inclusive_before.strftime("%Y/%m/%d")
    return f"{sender_group} after:{gmail_after} before:{gmail_before}"


def _header(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def search_bank_emails(
    service: Any,
    senders: list[str],
    date_after: str,
    date_before: str,
    exclude_message_ids: set[str] | None = None,
) -> list[RawEmail]:
    """Busca correos de los remitentes bancarios conocidos en el rango de fechas dado.

    `date_after`/`date_before` van en formato ISO (YYYY-MM-DD); se convierten internamente a la
    sintaxis de búsqueda de Gmail. Los correos cuyo id ya esté en `exclude_message_ids` se omiten
    (evita reprocesar en corridas repetidas).
    """
    exclude_message_ids = exclude_message_ids or set()
    query = _build_query(senders, date_after, date_before)

    message_ids: list[str] = []
    page_token = None
    while True:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        message_ids.extend(m["id"] for m in response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    emails: list[RawEmail] = []
    for message_id in message_ids:
        if message_id in exclude_message_ids:
            continue
        # format="full" para garantizar que "snippet" venga poblado (en "metadata" no siempre está).
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = msg.get("payload", {}).get("headers", [])
        emails.append(
            RawEmail(
                message_id=message_id,
                sender=_header(headers, "From"),
                date=_header(headers, "Date"),
                body=msg.get("snippet", ""),
            )
        )

    return emails
