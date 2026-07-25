from expense_agent.providers.gmail_client import _build_query, search_bank_emails


def test_build_query_groups_senders_with_or_and_converts_dates():
    query = _build_query(["a@x.com", "b@y.com"], "2026-01-01", "2026-01-31")

    # Gmail's before: excluye el día indicado, así que se corre un día para que
    # date_before ("2026-01-31") quede incluido en el rango buscado.
    assert query == "{from:a@x.com from:b@y.com} after:2026/01/01 before:2026/02/01"


def test_search_bank_emails_returns_all_when_none_excluded(
    fake_gmail_service_factory, bancolombia_emails
):
    service = fake_gmail_service_factory(bancolombia_emails)

    result = search_bank_emails(
        service,
        senders=["alertasynotificaciones@bancolombia.com.co"],
        date_after="2026-01-01",
        date_before="2026-12-31",
    )

    assert {e["message_id"] for e in result} == {e["message_id"] for e in bancolombia_emails}
    assert all(e["body"] for e in result)


def test_search_bank_emails_skips_already_seen_ids(fake_gmail_service_factory, bancolombia_emails):
    service = fake_gmail_service_factory(bancolombia_emails)
    already_seen = {bancolombia_emails[0]["message_id"], bancolombia_emails[1]["message_id"]}

    result = search_bank_emails(
        service,
        senders=["alertasynotificaciones@bancolombia.com.co"],
        date_after="2026-01-01",
        date_before="2026-12-31",
        exclude_message_ids=already_seen,
    )

    result_ids = {e["message_id"] for e in result}
    assert result_ids == {e["message_id"] for e in bancolombia_emails} - already_seen
