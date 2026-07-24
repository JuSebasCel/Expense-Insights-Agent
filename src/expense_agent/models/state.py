"""Estado compartido por los nodos del grafo de LangGraph."""

from typing import TypedDict

from expense_agent.models.transaction import Transaction


class RawEmail(TypedDict):
    message_id: str
    sender: str
    date: str
    body: str


class GraphState(TypedDict):
    date_after: str
    date_before: str
    raw_emails: list[RawEmail]
    transactions: list[Transaction]
    pending_review: list[Transaction]
    stats: dict
    dashboard_html: str
