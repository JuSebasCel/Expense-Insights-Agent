"""Construcción y compilación del grafo de LangGraph."""

import os
import sqlite3
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from expense_agent.core.config import BANK_SENDERS, Settings
from expense_agent.graph.nodes import (
    aggregate_stats,
    human_review,
    make_categorize_transactions_node,
    make_extract_transactions_node,
    make_fetch_emails_node,
    make_generate_dashboard_node,
    route_after_categorize,
)
from expense_agent.models.state import GraphState
from expense_agent.providers.gmail_client import build_gmail_service
from expense_agent.providers.llm import get_chat_model
from expense_agent.services.dashboard_service import render_dashboard


def make_checkpoint_serde() -> JsonPlusSerializer:
    """El estado del grafo guarda instancias de `Transaction`/`Category`/`TransactionType`
    (pydantic/enums propios). El serializador por defecto de LangGraph solo permite tipos
    externos que estén en una allowlist explícita; como estos tipos son de este mismo
    proyecto (nunca deserializamos algo que no hayamos escrito nosotros), confiamos en
    todos los módulos en vez de mantener la lista a mano."""
    return JsonPlusSerializer(allowed_msgpack_modules=True)


def build_checkpointer(settings: Settings) -> SqliteSaver:
    db_dir = os.path.dirname(settings.checkpoint_db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    # check_same_thread=False: FastAPI puede servir requests en distintos threads;
    # SqliteSaver ya está diseñado para usarse así (ver su propio from_conn_string).
    conn = sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    return SqliteSaver(conn, serde=make_checkpoint_serde())


def assemble_graph(
    gmail_service: Any,
    llm: Any,
    senders: list[str],
    render_dashboard_fn: Callable[[dict, list], str],
) -> StateGraph:
    """Arma el `StateGraph` (sin compilar) a partir de sus dependencias ya construidas.

    Separado de `build_graph` para poder ensamblar el mismo grafo en los tests con dobles de
    prueba en vez del cliente de Gmail y el LLM reales.
    """
    graph = StateGraph(GraphState)
    graph.add_node("fetch_emails", make_fetch_emails_node(gmail_service, senders))
    graph.add_node("extract_transactions", make_extract_transactions_node(llm))
    graph.add_node("categorize_transactions", make_categorize_transactions_node(llm))
    graph.add_node("human_review", human_review)
    graph.add_node("aggregate_stats", aggregate_stats)
    graph.add_node("generate_dashboard", make_generate_dashboard_node(render_dashboard_fn))

    graph.add_edge(START, "fetch_emails")
    graph.add_edge("fetch_emails", "extract_transactions")
    graph.add_edge("extract_transactions", "categorize_transactions")
    graph.add_conditional_edges(
        "categorize_transactions",
        route_after_categorize,
        {"human_review": "human_review", "aggregate_stats": "aggregate_stats"},
    )
    graph.add_edge("human_review", "aggregate_stats")
    graph.add_edge("aggregate_stats", "generate_dashboard")
    graph.add_edge("generate_dashboard", END)

    return graph


def build_graph(settings: Settings, checkpointer: SqliteSaver) -> CompiledStateGraph:
    gmail_service = build_gmail_service(settings)
    llm = get_chat_model(settings)
    graph = assemble_graph(gmail_service, llm, BANK_SENDERS, render_dashboard)
    return graph.compile(checkpointer=checkpointer)
