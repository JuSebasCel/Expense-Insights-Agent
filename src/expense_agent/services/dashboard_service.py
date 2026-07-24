"""Construye las figuras de Plotly y renderiza el dashboard final en HTML."""

from pathlib import Path

import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader, select_autoescape

from expense_agent.models.transaction import Transaction

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "jinja"]),
)


def _category_pie(stats: dict) -> str:
    by_category = stats["by_category"]
    fig = go.Figure(
        data=[go.Pie(labels=list(by_category.keys()), values=list(by_category.values()))]
    )
    fig.update_layout(title="Gasto por categoría", margin={"t": 40, "b": 10, "l": 10, "r": 10})
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def _merchant_bar(stats: dict) -> str:
    by_merchant = stats["by_merchant"]
    fig = go.Figure(
        data=[go.Bar(x=list(by_merchant.values()), y=list(by_merchant.keys()), orientation="h")]
    )
    fig.update_layout(
        title="Top comercios",
        margin={"t": 40, "b": 10, "l": 10, "r": 10},
        yaxis={"autorange": "reversed"},
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _date_trend(stats: dict) -> str:
    by_date = stats["by_date"]
    fig = go.Figure(data=[go.Bar(x=list(by_date.keys()), y=list(by_date.values()))])
    fig.update_layout(title="Gasto por fecha", margin={"t": 40, "b": 10, "l": 10, "r": 10})
    return fig.to_html(full_html=False, include_plotlyjs=False)


def render_dashboard(stats: dict, transactions: list[Transaction]) -> str:
    template = _env.get_template("dashboard.html.jinja")
    return template.render(
        stats=stats,
        transactions=transactions,
        category_pie=_category_pie(stats),
        merchant_bar=_merchant_bar(stats),
        date_trend=_date_trend(stats),
    )
