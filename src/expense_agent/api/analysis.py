"""Rutas HTTP: disparar el análisis (streaming SSE), resolver revisión humana, ver dashboard.

El grafo vive en un único thread fijo (`CHECKPOINT_THREAD_ID`): cada corrida de `/analysis/run`
manda solo `{date_after, date_before}` como input, nunca un estado completo. Gracias a cómo
LangGraph mezcla el input con el checkpoint existente, las claves omitidas (`transactions`, etc.)
conservan su valor previo — así es como se logra no reprocesar correos ya vistos entre corridas.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from langgraph.types import Command

from expense_agent.core.config import CATEGORIES, CHECKPOINT_THREAD_ID
from expense_agent.core.sse import format_sse

logger = logging.getLogger(__name__)
router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _thread_config() -> dict:
    return {"configurable": {"thread_id": CHECKPOINT_THREAD_ID}}


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html.jinja", {"categories": CATEGORIES})


@router.get("/analysis/run")
def run_analysis(request: Request, date_after: str, date_before: str):
    graph = request.app.state.graph
    config = _thread_config()

    def events():
        yield {"type": "progress", "node": "start"}

        graph_input = {"date_after": date_after, "date_before": date_before}
        for chunk in graph.stream(graph_input, config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                payload = chunk["__interrupt__"][0].value
                yield {"type": "review_needed", "pending": payload["pending"]}
                return
            for node_name, update in chunk.items():
                count = len(update.get("transactions", [])) if isinstance(update, dict) else None
                yield {"type": "progress", "node": node_name, "transactions_count": count}

        yield {"type": "done"}

    return StreamingResponse(format_sse(events()), media_type="text/event-stream")


@router.post("/analysis/resume")
async def resume_analysis(request: Request):
    graph = request.app.state.graph
    config = _thread_config()

    form = await request.form()
    answers: dict[str, str] = {
        key.removeprefix("category__"): value
        for key, value in form.items()
        if key.startswith("category__")
    }

    graph.invoke(Command(resume=answers), config)
    return RedirectResponse(url="/analysis/dashboard", status_code=303)


@router.get("/analysis/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request):
    graph = request.app.state.graph
    state = graph.get_state(_thread_config())

    dashboard_html = state.values.get("dashboard_html") if state.values else None
    if not dashboard_html:
        return HTMLResponse("<p>Todavía no hay ningún análisis generado.</p>", status_code=404)
    return HTMLResponse(dashboard_html)
