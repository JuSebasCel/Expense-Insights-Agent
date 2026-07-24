"""Prueba el grafo completo ensamblado con dobles de Gmail/LLM: idempotencia entre corridas
(no reprocesar correos ya vistos) y la pausa/reanudación de human-in-the-loop."""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from expense_agent.graph.build import assemble_graph, make_checkpoint_serde
from expense_agent.models.transaction import (
    Category,
    CategoryAssignment,
    ExtractedTransaction,
    TransactionType,
)
from expense_agent.services.dashboard_service import render_dashboard

EXTRACTION_RESPONSES = {
    "WOMPI SAS": ExtractedTransaction(
        merchant="WOMPI SAS", amount=12000.0,
        transaction_type=TransactionType.COMPRA, date="2026-07-08",
    ),
    "NOVAVENTA": ExtractedTransaction(
        merchant="NOVAVENTA", amount=2500.0,
        transaction_type=TransactionType.COMPRA, date="2026-07-08",
    ),
    "TIENDA D1 EL RECUERD": ExtractedTransaction(
        merchant="TIENDA D1 EL RECUERD", amount=75800.0,
        transaction_type=TransactionType.COMPRA, date="2026-04-14",
    ),
    "MARIA STELLA MARIN S": ExtractedTransaction(
        merchant="MARIA STELLA MARIN S", amount=54780.0,
        transaction_type=TransactionType.COMPRA, date="2026-04-13",
    ),
}

# "MARIA STELLA MARIN S" parece un nombre de persona: a propósito queda con confianza "baja"
# para forzar el camino de human_review.
CATEGORIZATION_RESPONSES = {
    "WOMPI SAS": CategoryAssignment(
        category=Category.SERVICIOS_FACTURAS, confidence="alta", reasoning="Pasarela de pagos."
    ),
    "NOVAVENTA": CategoryAssignment(
        category=Category.OTROS, confidence="alta", reasoning="Catálogo por catálogo conocido."
    ),
    "TIENDA D1 EL RECUERD": CategoryAssignment(
        category=Category.MERCADO, confidence="alta", reasoning="Cadena de tiendas de descuento."
    ),
    "MARIA STELLA MARIN S": CategoryAssignment(
        category=Category.OTROS, confidence="baja", reasoning="Parece un nombre de persona."
    ),
}


def _build_test_graph(fake_gmail_service_factory, fake_chat_model, emails):
    gmail_service = fake_gmail_service_factory(emails)
    extract_llm = fake_chat_model(EXTRACTION_RESPONSES)
    categorize_llm = fake_chat_model(CATEGORIZATION_RESPONSES)

    # extract_transactions y categorize_transactions piden cada uno su propio
    # `with_structured_output`, así que necesitan LLMs separados con las respuestas correctas.
    class DualLLM:
        def with_structured_output(self, schema):
            if schema is ExtractedTransaction:
                return extract_llm.with_structured_output(schema)
            return categorize_llm.with_structured_output(schema)

    graph = assemble_graph(
        gmail_service=gmail_service,
        llm=DualLLM(),
        senders=["alertasynotificaciones@bancolombia.com.co"],
        render_dashboard_fn=render_dashboard,
    )
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn, serde=make_checkpoint_serde())
    return graph.compile(checkpointer=checkpointer)


def test_full_run_pauses_for_review_then_resumes_and_generates_dashboard(
    fake_gmail_service_factory, fake_chat_model, bancolombia_emails
):
    compiled = _build_test_graph(fake_gmail_service_factory, fake_chat_model, bancolombia_emails)
    config = {"configurable": {"thread_id": "test-thread"}}
    graph_input = {"date_after": "2026-01-01", "date_before": "2026-12-31"}

    compiled.invoke(graph_input, config)

    state = compiled.get_state(config)
    assert state.next == ("human_review",)
    pending = state.tasks[0].interrupts[0].value["pending"]
    assert {p["message_id"] for p in pending} == {"19d88e5e1b8b32cc"}

    result = compiled.invoke(Command(resume={"19d88e5e1b8b32cc": "otros"}), config)

    assert result["dashboard_html"]
    assert "WOMPI SAS" in result["dashboard_html"]
    assert result["stats"]["total"] == 12000.0 + 2500.0 + 75800.0 + 54780.0
    assert result["stats"]["count"] == 4

    final_state = compiled.get_state(config)
    assert final_state.next == ()


def test_second_run_does_not_reprocess_already_seen_emails(
    fake_gmail_service_factory, fake_chat_model, bancolombia_emails
):
    compiled = _build_test_graph(fake_gmail_service_factory, fake_chat_model, bancolombia_emails)
    config = {"configurable": {"thread_id": "test-thread-2"}}
    graph_input = {"date_after": "2026-01-01", "date_before": "2026-12-31"}

    compiled.invoke(graph_input, config)
    compiled.invoke(Command(resume={"19d88e5e1b8b32cc": "otros"}), config)

    # Misma búsqueda otra vez: el servicio de Gmail sigue devolviendo los 4 mismos correos,
    # pero fetch_emails debe filtrarlos todos porque ya están en `transactions`.
    result = compiled.invoke(graph_input, config)

    assert result["stats"]["count"] == 4
    assert result["stats"]["total"] == 12000.0 + 2500.0 + 75800.0 + 54780.0
