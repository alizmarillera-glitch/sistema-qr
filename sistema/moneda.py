# -*- coding: utf-8 -*-
"""Utilidades de dinero: conversión USD <-> Bs., redondeo y formato.

Todo el sistema usa Decimal para los importes. Un solo lugar define cómo se
muestran los montos, de modo que USD y Bs. se vean igual en todas las pantallas.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")
CERO = Decimal("0")


def D(valor, defecto="0") -> Decimal:
    """Convierte cualquier número (int, float, str, Decimal, None) a Decimal."""
    if valor is None or valor == "":
        return Decimal(defecto)
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return Decimal(defecto)


def q2(valor) -> Decimal:
    return D(valor).quantize(CENT, rounding=ROUND_HALF_UP)


def a_bs(usd, tasa):
    """USD -> Bs. Devuelve None si no hay tasa válida."""
    t = D(tasa)
    return q2(D(usd) * t) if t > 0 else None


def a_usd(bs, tasa):
    """Bs. -> USD. Devuelve None si no hay tasa válida."""
    t = D(tasa)
    return q2(D(bs) / t) if t > 0 else None


def desglose_bs(subtotal, iva, tasa):
    """(subtotal_bs, iva_bs, total_bs) con total = subtotal + iva para que la factura cuadre."""
    s, i = a_bs(subtotal, tasa), a_bs(iva, tasa)
    if s is None:
        return None, None, None
    return s, i, s + i


def fmt_usd(valor) -> str:
    return f"${q2(valor):,.2f}"


def fmt_bs(valor, sin_tasa="Sin tasa") -> str:
    return sin_tasa if valor is None else f"Bs. {q2(valor):,.2f}"


def fmt_tasa(tasa) -> str:
    return f"{D(tasa):,.4f}"


def parse_monto(texto) -> Decimal:
    """Interpreta '1234.56', '1.234,56', '1,234.56' o '12,5'. Lanza ValueError si no es número."""
    s = str(texto).strip().replace(" ", "").replace("$", "")
    s = s.upper().replace("BS.", "").replace("BS", "")
    if not s:
        raise ValueError("Monto vacío")
    if "," in s and "." in s:
        # El separador que aparece último es el decimal; el otro es de miles.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"«{texto}» no es un número válido")
