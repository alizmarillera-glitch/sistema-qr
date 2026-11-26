# -*- coding: utf-8 -*-
"""Operaciones de inventario compatibles con el esquema relacional nuevo.

Todas las variaciones de stock se registran en movimientos_inventario y se
aplican dentro de una única transacción para evitar descuadres.
"""
from __future__ import annotations

import conexion as db


def listar_movimientos(limite: int = 500) -> list[dict]:
    limite = max(1, min(int(limite), 2000))
    return db.consulta(
        """SELECT m.id_movimiento, m.fecha_hora, p.codigo_piston, m.tipo,
                  m.cantidad, m.stock_anterior, m.stock_nuevo, m.motivo,
                  f.nro_factura, u.nombre_usuario
           FROM movimientos_inventario m
           INNER JOIN pistones p ON p.id_piston = m.id_piston
           LEFT JOIN facturas f ON f.id_factura = m.id_factura
           LEFT JOIN usuarios u ON u.id_usuario = m.id_usuario
           ORDER BY m.id_movimiento DESC LIMIT %s""",
        (limite,),
    )


def registrar_movimiento(id_piston: int, tipo: str, cantidad: int,
                         motivo: str, id_usuario: int | None,
                         id_factura: int | None = None) -> tuple[int, int]:
    tipo = tipo.strip().upper()
    if tipo not in {"ENTRADA", "SALIDA"}:
        raise ValueError("El movimiento debe ser ENTRADA o SALIDA.")
    cantidad = int(cantidad)
    motivo = (motivo or "").strip()
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    if not motivo:
        raise ValueError("El motivo del movimiento es obligatorio.")

    with db.transaccion() as (_conn, cur):
        cur.execute(db.SQL_STOCK_BLOQUEAR, (id_piston,))
        fila = cur.fetchone()
        if not fila:
            raise ValueError("El pistón seleccionado no existe.")
        anterior, activo = int(fila[0]), bool(fila[1])
        if not activo:
            raise ValueError("El pistón está desactivado y no admite movimientos.")
        if tipo == "SALIDA" and cantidad > anterior:
            raise ValueError(f"Stock insuficiente. Disponible: {anterior}.")
        nuevo = anterior + cantidad if tipo == "ENTRADA" else anterior - cantidad
        cur.execute(db.SQL_STOCK_FIJAR, (id_piston, nuevo))
        cur.execute(
            """INSERT INTO movimientos_inventario
               (id_piston,tipo,cantidad,motivo,id_usuario,id_factura,stock_anterior,stock_nuevo)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (id_piston, tipo, cantidad, motivo, id_usuario, id_factura, anterior, nuevo),
        )
        return anterior, nuevo


def ajustar_existencia(id_piston: int, nuevo_stock: int,
                        motivo: str, id_usuario: int | None) -> tuple[int, int]:
    nuevo_stock = int(nuevo_stock)
    motivo = (motivo or "").strip()
    if nuevo_stock < 0:
        raise ValueError("Las existencias no pueden ser negativas.")
    if not motivo:
        raise ValueError("El motivo del ajuste es obligatorio.")

    with db.transaccion() as (_conn, cur):
        cur.execute(db.SQL_STOCK_BLOQUEAR, (id_piston,))
        fila = cur.fetchone()
        if not fila:
            raise ValueError("El pistón seleccionado no existe.")
        anterior = int(fila[0])
        delta = abs(nuevo_stock - anterior)
        cur.execute(db.SQL_STOCK_FIJAR, (id_piston, nuevo_stock))
        cur.execute(
            """INSERT INTO movimientos_inventario
               (id_piston,tipo,cantidad,motivo,id_usuario,stock_anterior,stock_nuevo)
               VALUES(%s,'AJUSTE',%s,%s,%s,%s,%s)""",
            (id_piston, delta, motivo, id_usuario, anterior, nuevo_stock),
        )
        return anterior, nuevo_stock


def registrar_apertura(id_piston: int, id_usuario: int | None = None) -> None:
    """Deja constancia de la creación sin alterar el stock inicial (cero)."""
    with db.transaccion() as (_conn, cur):
        cur.execute(
            """INSERT INTO movimientos_inventario
               (id_piston,tipo,cantidad,motivo,id_usuario,stock_anterior,stock_nuevo)
               VALUES(%s,'APERTURA',0,'Registro inicial del pistón',%s,0,0)""",
            (id_piston, id_usuario),
        )
