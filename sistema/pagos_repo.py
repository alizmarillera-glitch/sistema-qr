# -*- coding: utf-8 -*-
"""Registro de pagos parciales y mixtos para Sistema_QR.

Los montos se guardan en la moneda realmente recibida (USD o VES).
Para calcular el saldo se convierten a USD usando la tasa guardada en cada
movimiento, sin modificar el importe histórico del pago.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import conexion as db

CENT = Decimal("0.01")

def _q(valor):
    return Decimal(str(valor)).quantize(CENT, rounding=ROUND_HALF_UP)

def metodos_activos():
    return db.consulta(
        "SELECT id_metodo_pago, nombre_metodo FROM metodo_pago "
        "WHERE estado=1 ORDER BY nombre_metodo"
    )

def obtener_resumen_pago(id_pago: int):
    pago = db.consulta(
        """SELECT pg.id_pago, pg.id_factura, pg.monto_total, pg.estado,
                  f.nro_factura, f.total AS total_factura, f.tasa_bcv,
                  COALESCE(SUM(CASE WHEN dp.moneda='VES'
                    THEN dp.monto / NULLIF(dp.tasa_aplicada,0)
                    ELSE dp.monto END),0) AS pagado_usd
           FROM pago pg
           JOIN facturas f ON f.id_factura=pg.id_factura
           LEFT JOIN detalle_pago dp ON dp.id_pago=pg.id_pago
             AND dp.estado IN ('REGISTRADO','CONFIRMADO')
           WHERE pg.id_pago=%s
           GROUP BY pg.id_pago, pg.id_factura, pg.monto_total, pg.estado,
                    f.nro_factura, f.total, f.tasa_bcv""",
        (id_pago,), uno=True,
    )
    if not pago:
        raise ValueError("No existe el registro de pago solicitado.")
    total = _q(pago["total_factura"])
    pagado = _q(pago["pagado_usd"])
    saldo = _q(max(Decimal("0.00"), total-pagado))
    pago.update({"total_factura": total, "pagado_usd": pagado, "saldo_usd": saldo})
    return pago

def listar_detalles_pago(id_pago: int):
    return db.consulta(
        """SELECT d.id_detalle_pago, m.nombre_metodo, d.monto, d.moneda,
                  d.tasa_aplicada, d.referencia, d.fecha_pago, d.estado,
                  d.observacion
           FROM detalle_pago d
           JOIN metodo_pago m ON m.id_metodo_pago=d.metodo_pago
           WHERE d.id_pago=%s ORDER BY d.fecha_pago, d.id_detalle_pago""",
        (id_pago,),
    )

def registrar_pago(id_pago: int, id_metodo_pago: int, monto, moneda: str,
                   referencia: str = "", tasa_aplicada=None,
                   observacion: str = "") -> dict:
    monto = _q(monto)
    moneda = moneda.strip().upper()
    referencia = referencia.strip() or None
    if monto <= 0:
        raise ValueError("El monto del pago debe ser mayor que cero.")
    if moneda not in ("USD", "VES"):
        raise ValueError("La moneda debe ser USD o VES.")
    tasa = None
    if moneda == "VES":
        if tasa_aplicada is None or Decimal(str(tasa_aplicada)) <= 0:
            raise ValueError("Para registrar un pago en bolívares se necesita una tasa válida.")
        tasa = Decimal(str(tasa_aplicada))
    with db.transaccion(dictionary=True) as (_conn, cur):
        cur.execute(
            """SELECT pg.id_pago, pg.estado, f.total
               FROM pago pg JOIN facturas f ON f.id_factura=pg.id_factura
               WHERE pg.id_pago=%s FOR UPDATE""", (id_pago,))
        pago = cur.fetchone()
        if not pago:
            raise ValueError("No existe el pago asociado a la factura.")
        if pago["estado"] == "ANULADO":
            raise ValueError("No se pueden registrar pagos en una factura anulada.")
        cur.execute("SELECT estado FROM metodo_pago WHERE id_metodo_pago=%s", (id_metodo_pago,))
        metodo = cur.fetchone()
        if not metodo or not metodo["estado"]:
            raise ValueError("El método de pago no existe o está desactivado.")
        cur.execute(
            """SELECT COALESCE(SUM(CASE WHEN moneda='VES'
                      THEN monto / NULLIF(tasa_aplicada,0) ELSE monto END),0) AS pagado
               FROM detalle_pago WHERE id_pago=%s AND estado IN ('REGISTRADO','CONFIRMADO')""",
            (id_pago,))
        pagado = Decimal(str(cur.fetchone()["pagado"] or 0))
        total = Decimal(str(pago["total"]))
        equivalente = _q(monto / tasa) if moneda == "VES" else monto
        nuevo_pagado = pagado + equivalente
        if nuevo_pagado > total + Decimal("0.01"):
            raise ValueError(
                f"El pago excede el saldo pendiente. Saldo aproximado: "
                f"${_q(max(Decimal('0'), total-pagado))} USD."
            )
        cur.execute(
            """INSERT INTO detalle_pago
               (id_pago, metodo_pago, monto, referencia, estado, moneda,
                tasa_aplicada, observacion)
               VALUES (%s,%s,%s,%s,'REGISTRADO',%s,%s,%s)""",
            (id_pago, id_metodo_pago, monto, referencia, moneda, tasa, observacion.strip() or None))
        detalle_id = cur.lastrowid
        estado = "PAGADO" if nuevo_pagado >= total-Decimal("0.01") else "PARCIAL"
        cur.execute("UPDATE pago SET monto_total=%s, estado=%s WHERE id_pago=%s",
                    (_q(nuevo_pagado), estado, id_pago))
        return {"id_detalle_pago": detalle_id, "estado": estado,
                "pagado_usd": _q(nuevo_pagado), "saldo_usd": _q(max(Decimal("0"),total-nuevo_pagado))}
