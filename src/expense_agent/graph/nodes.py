"""Nodos del grafo. Cada `make_*_node` recibe sus dependencias (LLM, cliente de Gmail,
servicio de dashboard) y devuelve una función `(GraphState) -> dict` lista para usarse
en el `StateGraph` — así los nodos se pueden probar con dobles de prueba sin tocar red."""

import logging
from collections import defaultdict
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from langgraph.types import interrupt

from expense_agent.models.state import GraphState
from expense_agent.models.transaction import (
    Category,
    CategoryAssignment,
    ExtractedTransaction,
    Transaction,
)
from expense_agent.providers.gmail_client import search_bank_emails

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Eres un extractor de datos de notificaciones bancarias colombianas.
Lee el siguiente texto de un correo de alerta bancaria y extrae la transacción que describe.

Los verbos que puedes encontrar y su tipo correspondiente:
- "Compraste" -> compra
- "Transferiste" / "Enviaste" -> transferencia
- "Pagaste" -> pago
- "Retiraste" -> retiro
- cualquier otro caso -> otro

El monto viene en pesos colombianos con formato "$12.000,00" (punto = miles, coma = decimales).
Devuelve el monto como número (ej: 12000.00).

Texto del correo:
{body}
"""

CATEGORIZATION_PROMPT = """Eres un asistente que categoriza gastos personales colombianos.

Transacción:
- Comercio/contraparte: {merchant}
- Tipo: {transaction_type}
- Monto: ${amount:,.0f} COP

Elige la categoría que mejor describa este gasto entre: mercado, transporte, restaurantes,
suscripciones, salud, entretenimiento, servicios_facturas, transferencias, otros.

Si el nombre del comercio es ambiguo, genérico o no te da suficiente información para estar
razonablemente seguro (por ejemplo un nombre propio de persona, una razón social poco clara, o
una sigla que no reconoces), responde con confidence="baja" para que un humano lo confirme.
Solo usa confidence="alta" cuando el comercio sea inequívoco (ej. una cadena de supermercados
conocida, un servicio de streaming reconocido, etc.).
"""

BANK_NAME_HINTS = {
    "bancolombia": "Bancolombia",
    "nequi": "Nequi",
}


def _guess_source_bank(sender: str) -> str:
    sender_lower = sender.lower()
    for hint, name in BANK_NAME_HINTS.items():
        if hint in sender_lower:
            return name
    return "Desconocido"


def _email_date_to_iso(raw_date: str, fallback: str) -> str:
    try:
        return parsedate_to_datetime(raw_date).date().isoformat()
    except (TypeError, ValueError):
        return fallback


def make_fetch_emails_node(gmail_service: Any, senders: list[str] | Callable[[], list[str]]):
    """`senders` puede ser una lista fija (tests, scripts) o un callable que se resuelve en
    cada corrida (uso real: lee el archivo administrado desde el front, sin necesidad de
    reiniciar el proceso cuando el usuario agrega o quita un remitente)."""

    def fetch_emails(state: GraphState) -> dict:
        resolved_senders = senders() if callable(senders) else senders
        already_seen = {t.message_id for t in state.get("transactions", [])}
        emails = search_bank_emails(
            gmail_service,
            resolved_senders,
            state["date_after"],
            state["date_before"],
            exclude_message_ids=already_seen,
        )
        logger.info("fetch_emails: %d correos nuevos", len(emails))
        return {"raw_emails": emails}

    return fetch_emails


def make_extract_transactions_node(llm: Any):
    structured_llm = llm.with_structured_output(ExtractedTransaction)

    def extract_transactions(state: GraphState) -> dict:
        transactions = list(state.get("transactions", []))

        for email in state["raw_emails"]:
            extracted: ExtractedTransaction = structured_llm.invoke(
                EXTRACTION_PROMPT.format(body=email["body"])
            )
            transactions.append(
                Transaction(
                    message_id=email["message_id"],
                    source_bank=_guess_source_bank(email["sender"]),
                    merchant=extracted.merchant,
                    amount=extracted.amount,
                    transaction_type=extracted.transaction_type,
                    date=_email_date_to_iso(email["date"], fallback=extracted.date),
                    card_last4=extracted.card_last4,
                )
            )

        logger.info("extract_transactions: %d transacciones totales", len(transactions))
        return {"transactions": transactions}

    return extract_transactions


def make_categorize_transactions_node(llm: Any):
    structured_llm = llm.with_structured_output(CategoryAssignment)

    def categorize_transactions(state: GraphState) -> dict:
        transactions = []
        pending_review = []

        for transaction in state["transactions"]:
            if transaction.category is not None:
                transactions.append(transaction)
                continue

            assignment: CategoryAssignment = structured_llm.invoke(
                CATEGORIZATION_PROMPT.format(
                    merchant=transaction.merchant,
                    transaction_type=transaction.transaction_type.value,
                    amount=transaction.amount,
                )
            )
            transaction = transaction.model_copy(
                update={
                    "category": assignment.category,
                    "confidence": assignment.confidence,
                    "reasoning": assignment.reasoning,
                }
            )
            transactions.append(transaction)
            if assignment.confidence == "baja":
                pending_review.append(transaction)

        logger.info(
            "categorize_transactions: %d categorizadas, %d requieren revisión",
            len(transactions),
            len(pending_review),
        )
        return {"transactions": transactions, "pending_review": pending_review}

    return categorize_transactions


def route_after_categorize(state: GraphState) -> Literal["human_review", "aggregate_stats"]:
    return "human_review" if state["pending_review"] else "aggregate_stats"


def human_review(state: GraphState) -> dict:
    """Pausa el grafo y expone las transacciones ambiguas para confirmación humana.

    Al reanudar (`Command(resume=answers)`), `answers` es un dict `{message_id: category}`
    con la categoría final elegida por el humano para cada transacción pendiente.
    """
    payload = {
        "pending": [
            {
                "message_id": t.message_id,
                "merchant": t.merchant,
                "amount": t.amount,
                "suggested_category": t.category,
                "reasoning": t.reasoning,
            }
            for t in state["pending_review"]
        ]
    }
    answers: dict[str, str] = interrupt(payload)

    updated_transactions = []
    for transaction in state["transactions"]:
        if transaction.message_id in answers:
            # model_copy no valida el `update`, así que hay que convertir el string crudo
            # (viene de Command(resume=...) o de un <select> del formulario) al enum a mano.
            transaction = transaction.model_copy(
                update={
                    "category": Category(answers[transaction.message_id]),
                    "confidence": "alta",
                    "reasoning": "Confirmado manualmente por el usuario.",
                }
            )
        updated_transactions.append(transaction)

    return {"transactions": updated_transactions, "pending_review": []}


def aggregate_stats(state: GraphState) -> dict:
    transactions = state["transactions"]

    by_category: dict[str, float] = defaultdict(float)
    by_merchant: dict[str, float] = defaultdict(float)
    by_date: dict[str, float] = defaultdict(float)

    for t in transactions:
        category = t.category.value if t.category else "sin_categoria"
        by_category[category] += t.amount
        by_merchant[t.merchant] += t.amount
        by_date[t.date] += t.amount

    stats = {
        "total": sum(t.amount for t in transactions),
        "count": len(transactions),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "by_merchant": dict(sorted(by_merchant.items(), key=lambda kv: -kv[1])[:10]),
        "by_date": dict(sorted(by_date.items())),
    }
    return {"stats": stats}


def make_generate_dashboard_node(render_dashboard: Any):
    def generate_dashboard(state: GraphState) -> dict:
        html = render_dashboard(state["stats"], state["transactions"])
        return {"dashboard_html": html}

    return generate_dashboard
