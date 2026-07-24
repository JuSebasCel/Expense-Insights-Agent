"""Punto de entrada de la app FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from expense_agent.api.analysis import router as analysis_router
from expense_agent.core.config import get_settings
from expense_agent.graph.build import build_checkpointer, build_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    checkpointer = build_checkpointer(settings)
    # Si es la primera vez que corre, esto abre el navegador para el consentimiento OAuth de Gmail.
    app.state.graph = build_graph(settings, checkpointer)
    logger.info("Grafo listo.")
    yield


app = FastAPI(title="Expense Insights Agent", lifespan=lifespan)
app.include_router(analysis_router)
