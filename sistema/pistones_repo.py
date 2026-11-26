# -*- coding: utf-8 -*-
"""Repositorio del catálogo de pistones para el modelo relacional nuevo.

Centraliza el mapeo entre los nombres de la GUI V2 y las columnas oficiales:
PISTONES, precios_pistones y CODIGOS_QR. No crea ni modifica tablas.
"""
from __future__ import annotations

import os
from typing import Any
import conexion as db
from generador_qr import datos_qr


SELECT_PISTON = """
SELECT p.id_piston AS id,
       p.codigo_piston AS codigo,
       COALESCE(p.descripcion, '') AS tipo_auto,
       COALESCE(p.anio, '') AS anio,
       p.numero_piezas AS num_piezas,
       COALESCE(p.fecha_fabricacion, '') AS fecha,
       COALESCE(p.offset_mm, '') AS offset_mm,
       COALESCE(p.trazabilidad, '') AS trazabilidad,
       p.diametro_mm AS diam_piston,
       p.diametro_cilindro_mm AS diam_cilindro,
       COALESCE(e.stock, 0) AS stock,
       p.stock_minimo AS stock_minimo,
       p.activo AS activo,
       COALESCE(pr.precio_base, 0) AS precio,
       COALESCE(p.imagen, '') AS imagen,
       COALESCE(q.ruta_imagen, '') AS qr
FROM pistones p
LEFT JOIN existencias e ON e.id_piston = p.id_piston
LEFT JOIN precios_pistones pr
       ON pr.id_piston = p.id_piston AND pr.vigente_hasta IS NULL
LEFT JOIN codigos_qr q
       ON q.id_piston = p.id_piston AND q.estado = 'ACTIVO'
"""


def _normalizar(filas):
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fila in filas:
        fila["etiqueta"] = os.path.join(base, "etiquetas_generadas", f"ETQ-{fila['codigo']}.png")
    return filas


def listar(busqueda: str = "") -> list[dict[str, Any]]:
    if busqueda:
        patron = f"%{busqueda.strip()}%"
        return _normalizar(db.consulta(SELECT_PISTON + " WHERE p.codigo_piston LIKE %s OR p.descripcion LIKE %s ORDER BY p.codigo_piston", (patron, patron)))
    return _normalizar(db.consulta(SELECT_PISTON + " ORDER BY p.codigo_piston"))


def obtener(id_piston: int | str) -> dict[str, Any] | None:
    fila = db.consulta(SELECT_PISTON + " WHERE p.id_piston=%s LIMIT 1", (id_piston,), uno=True)
    return _normalizar([fila])[0] if fila else None


def buscar_codigo(codigo: str) -> dict[str, Any] | None:
    fila = db.consulta(SELECT_PISTON + " WHERE p.codigo_piston=%s LIMIT 1", (codigo.strip().upper(),), uno=True)
    return _normalizar([fila])[0] if fila else None


def resumen() -> dict[str, Any]:
    return db.consulta(
        "SELECT COUNT(*) AS referencias, COALESCE(SUM(e.stock),0) AS unidades, "
        "COALESCE(SUM(CASE WHEN p.activo=0 THEN 1 ELSE 0 END),0) AS desactivados "
        "FROM pistones p LEFT JOIN existencias e ON e.id_piston=p.id_piston",
        uno=True,
    ) or {"referencias": 0, "unidades": 0, "desactivados": 0}


def _guardar_qr(cursor, id_piston: int, piston: dict[str, Any], ruta_qr: str) -> None:
    """Registra el QR vigente en codigos_qr dentro de la misma transacción."""
    # Este módulo usa nombres de la GUI antigua (tipo_auto, diam_piston): se traducen a los del QR actual.
    dato = dict(piston)
    dato.setdefault("descripcion", piston.get("tipo_auto"))
    dato.setdefault("diametro_mm", piston.get("diam_piston"))
    contenido = datos_qr(dato)
    ruta = os.path.relpath(ruta_qr, db.BASE).replace("\\", "/") if os.path.isabs(ruta_qr) else ruta_qr
    cursor.execute("UPDATE codigos_qr SET estado='INACTIVO' WHERE id_piston=%s AND estado='ACTIVO' AND contenido_qr<>%s",
                   (id_piston, contenido))
    cursor.execute("SELECT id_qr FROM codigos_qr WHERE contenido_qr=%s", (contenido,))
    fila = cursor.fetchone()
    if fila:
        cursor.execute("UPDATE codigos_qr SET estado='ACTIVO', ruta_imagen=%s, fecha_generacion=CURRENT_TIMESTAMP "
                       "WHERE id_qr=%s", (ruta, fila[0]))
    else:
        cursor.execute("INSERT INTO codigos_qr(id_piston, contenido_qr, ruta_imagen, estado) VALUES(%s,%s,%s,'ACTIVO')",
                       (id_piston, contenido, ruta))


def crear(p: dict[str, Any], ruta_imagen: str, ruta_qr: str) -> int:
    """Crea pistón, precio inicial (0) y QR en una sola transacción."""
    with db.transaccion() as (_conn, cur):
        cur.execute(
            """INSERT INTO pistones
               (codigo_piston, descripcion, diametro_mm, anio, numero_piezas,
                fecha_fabricacion, offset_mm, trazabilidad, diametro_cilindro_mm,
                imagen, stock_actual, stock_minimo, activo)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,1)""",
            (p["codigo"], p["tipo_auto"], _decimal_or_none(p.get("diam_piston")),
             p.get("anio"), p["num_piezas"], p.get("fecha"), p.get("offset_mm"),
             p.get("trazabilidad"), _decimal_or_none(p.get("diam_cilindro")), ruta_imagen),
        )
        id_piston = cur.lastrowid
        cur.execute("INSERT INTO existencias(id_piston, stock) VALUES(%s,0)", (id_piston,))
        cur.execute(
            "INSERT INTO movimientos_inventario(id_piston,tipo,cantidad,motivo,stock_anterior,stock_nuevo) "
            "VALUES(%s,'APERTURA',0,'Registro inicial del pistón',0,0)", (id_piston,))
        piston = dict(p)
        piston.update({"id": id_piston, "imagen": ruta_imagen})
        _guardar_qr(cur, id_piston, piston, ruta_qr)
        return id_piston


def actualizar_tecnicos(id_piston: int, p: dict[str, Any], ruta_qr: str) -> None:
    with db.transaccion() as (_conn, cur):
        cur.execute(
            """UPDATE pistones SET descripcion=%s, anio=%s, numero_piezas=%s,
               fecha_fabricacion=%s, offset_mm=%s, trazabilidad=%s,
               diametro_mm=%s, diametro_cilindro_mm=%s WHERE id_piston=%s""",
            (p["tipo_auto"], p.get("anio"), p["num_piezas"], p.get("fecha"),
             p.get("offset_mm"), p.get("trazabilidad"), _decimal_or_none(p.get("diam_piston")),
             _decimal_or_none(p.get("diam_cilindro")), id_piston),
        )
        cur.execute(SELECT_PISTON + " WHERE p.id_piston=%s LIMIT 1", (id_piston,))
        row = cur.fetchone()
        # Se consulta como tupla aquí para mantener el cursor simple.
        if row:
            cols = [d[0] for d in cur.description]
            piston = dict(zip(cols, row))
            _guardar_qr(cur, id_piston, piston, ruta_qr)


def actualizar_imagen(id_piston: int, ruta_imagen: str, piston: dict[str, Any], ruta_qr: str) -> None:
    with db.transaccion() as (_conn, cur):
        cur.execute("UPDATE pistones SET imagen=%s WHERE id_piston=%s", (ruta_imagen, id_piston))
        piston = dict(piston)
        piston["imagen"] = ruta_imagen
        _guardar_qr(cur, id_piston, piston, ruta_qr)


def cambiar_estado(id_piston: int, estado: int) -> None:
    db.consulta("UPDATE pistones SET activo=%s WHERE id_piston=%s", (int(bool(estado)), id_piston), commit=True)


def cambiar_stock(id_piston: int, nuevo_stock: int, id_usuario: int | None, motivo: str = "Ajuste de inventario") -> None:
    """Actualiza existencias y deja movimiento auditable, de forma atómica."""
    with db.transaccion() as (_conn, cur):
        cur.execute(db.SQL_STOCK_BLOQUEAR, (id_piston,))
        fila = cur.fetchone()
        if not fila:
            raise ValueError("El pistón ya no existe.")
        anterior = int(fila[0])
        if nuevo_stock < 0:
            raise ValueError("Las existencias no pueden ser negativas.")
        delta = nuevo_stock - anterior
        cur.execute(db.SQL_STOCK_FIJAR, (id_piston, nuevo_stock))
        cur.execute(
            "INSERT INTO movimientos_inventario(id_piston,tipo,cantidad,motivo,id_usuario,stock_anterior,stock_nuevo) "
            "VALUES(%s,'AJUSTE',%s,%s,%s,%s,%s)",
            (id_piston, abs(delta), motivo, id_usuario, anterior, nuevo_stock),
        )


def actualizar_precio(id_piston: int, precio: float) -> None:
    if precio < 0:
        raise ValueError("El precio no puede ser negativo.")
    db.establecer_precio(id_piston, precio, "USD")


def _decimal_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip().replace(",", ".")
