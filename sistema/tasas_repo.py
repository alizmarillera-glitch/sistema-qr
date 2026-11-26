# -*- coding: utf-8 -*-
"""Persistencia del historial de tasas de cambio (tabla tasas_bcv)."""
from __future__ import annotations
from decimal import Decimal
import conexion as db


def guardar_tasa(tasa, fecha_efectiva, fuente: str, moneda_origen="USD", moneda_destino="VES"):
    """Guarda la tasa consultada o ingresada. No duplica si es idéntica a la última guardada."""
    valor = Decimal(str(tasa))
    if valor <= 0:
        raise ValueError("La tasa debe ser mayor que cero.")
    ultima = db.consulta(
        "SELECT tasa, fecha_efectiva, fuente FROM tasas_bcv WHERE moneda_origen=%s AND moneda_destino=%s "
        "ORDER BY fecha_consulta DESC, id_tasa DESC LIMIT 1", (moneda_origen, moneda_destino), uno=True)
    if (ultima and Decimal(str(ultima["tasa"])) == valor and str(ultima["fecha_efectiva"]) == str(fecha_efectiva)
            and ultima["fuente"] == fuente):
        return
    db.consulta(
        "INSERT INTO tasas_bcv(moneda_origen,moneda_destino,tasa,fecha_efectiva,fuente,validada) "
        "VALUES(%s,%s,%s,%s,%s,1)", (moneda_origen, moneda_destino, valor, fecha_efectiva, fuente), commit=True)


def historial_tasas(limite=30):
    limite = max(1, min(int(limite), 365))
    return db.consulta(
        f"""SELECT id_tasa, moneda_origen, moneda_destino, tasa, fecha_efectiva, fecha_consulta, fuente, validada
            FROM tasas_bcv ORDER BY fecha_consulta DESC, id_tasa DESC LIMIT {limite}""")


def ultima_tasa():
    """Última tasa guardada (la más recientemente consultada o ingresada)."""
    return db.consulta(
        """SELECT tasa, fecha_efectiva, fecha_consulta, fuente FROM tasas_bcv
           WHERE validada=1 AND moneda_origen='USD' AND moneda_destino='VES'
           ORDER BY fecha_consulta DESC, id_tasa DESC LIMIT 1""", uno=True)
