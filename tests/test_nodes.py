from expense_agent.graph.nodes import (
    aggregate_stats,
    make_categorize_transactions_node,
    make_extract_transactions_node,
    route_after_categorize,
)
from expense_agent.models.transaction import (
    Category,
    CategoryAssignment,
    ExtractedTransaction,
    Transaction,
    TransactionType,
)

# Los correos reales solo tienen "Compraste" en el texto, pero el prompt de extracción también
# les pide manejar otros verbos. Estas respuestas fijas simulan lo que el LLM debería producir
# para cada correo de la fixture; la fecha "1900-01-01" es deliberadamente incorrecta para
# comprobar que el nodo prioriza la fecha real del header del correo sobre el guess del LLM.
EXTRACTION_RESPONSES = {
    "WOMPI SAS": ExtractedTransaction(
        merchant="WOMPI SAS", amount=12000.0, transaction_type=TransactionType.COMPRA,
        date="1900-01-01", card_last4="0782",
    ),
    "NOVAVENTA": ExtractedTransaction(
        merchant="NOVAVENTA", amount=2500.0, transaction_type=TransactionType.COMPRA,
        date="1900-01-01", card_last4="0782",
    ),
    "TIENDA D1 EL RECUERD": ExtractedTransaction(
        merchant="TIENDA D1 EL RECUERD", amount=75800.0, transaction_type=TransactionType.COMPRA,
        date="1900-01-01", card_last4="0782",
    ),
    "MARIA STELLA MARIN S": ExtractedTransaction(
        merchant="MARIA STELLA MARIN S", amount=54780.0, transaction_type=TransactionType.COMPRA,
        date="1900-01-01", card_last4="0782",
    ),
}


def test_extract_transactions_parses_real_emails_and_prefers_header_date(
    bancolombia_emails, fake_chat_model
):
    node = make_extract_transactions_node(fake_chat_model(EXTRACTION_RESPONSES))

    result = node({"raw_emails": bancolombia_emails, "transactions": []})
    transactions = {t.message_id: t for t in result["transactions"]}

    assert len(transactions) == 4

    wompi = transactions["19f41e5ecccce71c"]
    assert wompi.merchant == "WOMPI SAS"
    assert wompi.amount == 12000.0
    assert wompi.source_bank == "Bancolombia"
    assert wompi.card_last4 == "0782"
    # La fecha viene del header del correo (2026-07-08), no del "1900-01-01" que devolvió el LLM.
    assert wompi.date == "2026-07-08"

    d1 = transactions["19d8cb425e2df9e2"]
    assert d1.amount == 75800.0
    assert d1.date == "2026-04-14"


def test_extract_transactions_appends_to_existing(bancolombia_emails, fake_chat_model):
    node = make_extract_transactions_node(fake_chat_model(EXTRACTION_RESPONSES))
    existing = Transaction(
        message_id="already-processed",
        source_bank="Bancolombia",
        merchant="OTRO",
        amount=1000.0,
        transaction_type=TransactionType.COMPRA,
        date="2026-01-01",
    )

    result = node({"raw_emails": bancolombia_emails[:1], "transactions": [existing]})

    assert len(result["transactions"]) == 2
    assert result["transactions"][0].message_id == "already-processed"


def test_categorize_transactions_flags_low_confidence_for_review(fake_chat_model):
    responses = {
        "ÉXITO": CategoryAssignment(
            category=Category.MERCADO, confidence="alta",
            reasoning="Cadena de supermercados conocida.",
        ),
        "XYZ CORP SAS": CategoryAssignment(
            category=Category.OTROS, confidence="baja",
            reasoning="Nombre de comercio no reconocido.",
        ),
    }
    node = make_categorize_transactions_node(fake_chat_model(responses))

    clear_tx = Transaction(
        message_id="m1", source_bank="Bancolombia", merchant="ÉXITO", amount=50000.0,
        transaction_type=TransactionType.COMPRA, date="2026-01-01",
    )
    ambiguous_tx = Transaction(
        message_id="m2", source_bank="Bancolombia", merchant="XYZ CORP SAS", amount=30000.0,
        transaction_type=TransactionType.COMPRA, date="2026-01-01",
    )

    result = node({"transactions": [clear_tx, ambiguous_tx]})

    by_id = {t.message_id: t for t in result["transactions"]}
    assert by_id["m1"].category == Category.MERCADO
    assert by_id["m1"].confidence == "alta"

    pending_ids = {t.message_id for t in result["pending_review"]}
    assert pending_ids == {"m2"}

    assert route_after_categorize({"pending_review": result["pending_review"]}) == "human_review"
    assert route_after_categorize({"pending_review": []}) == "aggregate_stats"


def test_categorize_transactions_skips_already_categorized(fake_chat_model):
    # Sin respuestas configuradas: si el nodo intentara volver a categorizar esta transacción,
    # el doble del LLM lanzaría un AssertionError al no encontrar un match.
    node = make_categorize_transactions_node(fake_chat_model({}))
    already_categorized = Transaction(
        message_id="m1", source_bank="Bancolombia", merchant="ÉXITO", amount=50000.0,
        transaction_type=TransactionType.COMPRA, date="2026-01-01",
        category=Category.MERCADO, confidence="alta", reasoning="ya confirmado antes",
    )

    result = node({"transactions": [already_categorized]})

    assert result["transactions"] == [already_categorized]
    assert result["pending_review"] == []


def test_aggregate_stats_computes_totals_by_category_and_merchant():
    transactions = [
        Transaction(
            message_id="m1", source_bank="Bancolombia", merchant="ÉXITO", amount=50000.0,
            transaction_type=TransactionType.COMPRA, date="2026-01-05", category=Category.MERCADO,
        ),
        Transaction(
            message_id="m2", source_bank="Bancolombia", merchant="ÉXITO", amount=20000.0,
            transaction_type=TransactionType.COMPRA, date="2026-01-06", category=Category.MERCADO,
        ),
        Transaction(
            message_id="m3", source_bank="Bancolombia", merchant="NETFLIX", amount=30000.0,
            transaction_type=TransactionType.COMPRA, date="2026-01-06",
            category=Category.SUSCRIPCIONES,
        ),
    ]

    result = aggregate_stats({"transactions": transactions})
    stats = result["stats"]

    assert stats["total"] == 100000.0
    assert stats["count"] == 3
    assert stats["by_category"]["mercado"] == 70000.0
    assert stats["by_category"]["suscripciones"] == 30000.0
    assert stats["by_merchant"]["ÉXITO"] == 70000.0
    assert stats["by_date"]["2026-01-06"] == 50000.0
