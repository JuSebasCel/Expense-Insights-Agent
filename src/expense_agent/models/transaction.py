"""Esquemas de datos para transacciones extraídas de correos bancarios."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class TransactionType(StrEnum):
    COMPRA = "compra"
    TRANSFERENCIA = "transferencia"
    PAGO = "pago"
    RETIRO = "retiro"
    OTRO = "otro"


class Category(StrEnum):
    MERCADO = "mercado"
    TRANSPORTE = "transporte"
    RESTAURANTES = "restaurantes"
    SUSCRIPCIONES = "suscripciones"
    SALUD = "salud"
    ENTRETENIMIENTO = "entretenimiento"
    SERVICIOS_FACTURAS = "servicios_facturas"
    TRANSFERENCIAS = "transferencias"
    OTROS = "otros"


Confidence = Literal["alta", "media", "baja"]


class ExtractedTransaction(BaseModel):
    """Lo que el LLM extrae del texto crudo de un correo bancario."""

    merchant: str = Field(description="Comercio o contraparte de la transacción")
    amount: float = Field(description="Monto en pesos colombianos, sin símbolos ni separadores")
    transaction_type: TransactionType
    date: str = Field(description="Fecha en formato ISO 8601, YYYY-MM-DD")
    card_last4: str | None = Field(
        default=None, description="Últimos 4 dígitos de la tarjeta, si aplica"
    )


class CategoryAssignment(BaseModel):
    """Lo que el LLM produce al categorizar una transacción."""

    category: Category
    confidence: Confidence
    reasoning: str = Field(description="Explicación breve de por qué se eligió esta categoría")


class Transaction(BaseModel):
    """Una transacción completa: correo crudo + extracción + categorización."""

    message_id: str
    source_bank: str
    merchant: str
    amount: float
    currency: str = "COP"
    transaction_type: TransactionType
    date: str
    card_last4: str | None = None
    category: Category | None = None
    confidence: Confidence | None = None
    reasoning: str | None = None
