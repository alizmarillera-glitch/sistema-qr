# -*- coding: utf-8 -*-
"""Clientes y facturación (USD como moneda base, con equivalentes en Bs. a la tasa del momento)."""
from __future__ import annotations
import uuid
from decimal import Decimal

import conexion as db
import telefono as tel
import moneda as mon

IVA = Decimal("0.16")
TOLERANCIA = Decimal("0.01")


def buscar_cliente(tipo_documento: str, documento: str):
    return db.consulta(
        """SELECT id_cliente, tipo_documento, documento, nombre_razon_social,
                  telefono, correo, direccion, codigo_cliente
           FROM clientes WHERE tipo_documento=%s AND documento=%s LIMIT 1""",
        (tipo_documento.strip().upper(), documento.strip()), uno=True)


def guardar_cliente(tipo_documento: str, documento: str, nombre: str,
                    direccion: str, telefono: str, correo: str | None = None) -> int:
    tipo_documento = tipo_documento.strip().upper()
    documento, nombre = documento.strip(), nombre.strip()
    direccion, telefono = direccion.strip(), telefono.strip()
    if not all((tipo_documento, documento, nombre, direccion, telefono)):
        raise ValueError("Tipo y número de documento, nombre, dirección y teléfono son obligatorios.")
    error_tel = tel.error_completo(telefono)
    if error_tel:
        raise ValueError(error_tel)
    with db.transaccion() as (_conn, cur):
        cur.execute(
            """INSERT INTO clientes(tipo_documento,documento,nombre_razon_social,telefono,correo,direccion)
               VALUES(%s,%s,%s,%s,%s,%s)""",
            (tipo_documento, documento, nombre, telefono, correo, direccion))
        cid = cur.lastrowid
        cur.execute("UPDATE clientes SET codigo_cliente=%s WHERE id_cliente=%s", (f"CLI-{cid:06d}", cid))
        return cid


def listar_facturas():
    return db.consulta(
        """SELECT f.id_factura, f.nro_factura, f.fecha_hora, c.nombre_razon_social AS cliente,
                  f.subtotal, f.monto_iva, f.total,
                  COALESCE(t.total_bs, f.total_bs) AS total_bs,
                  COALESCE(t.tasa_bcv, f.tasa_bcv) AS tasa_bcv, f.estado
           FROM facturas f JOIN clientes c ON c.id_cliente=f.id_cliente
           LEFT JOIN tasa_factura t ON t.id_factura=f.id_factura
           ORDER BY f.id_factura DESC""")


def obtener_factura(id_factura: int):
    """(cabecera, detalle, pagos). La cabecera trae los importes en USD y en Bs. guardados."""
    f = db.consulta(
        """SELECT f.id_factura, f.nro_factura, f.fecha_hora, f.subtotal, f.monto_iva AS iva, f.total, f.estado,
                  c.nombre_razon_social AS cliente, CONCAT(c.tipo_documento,'-',c.documento) AS documento_cliente,
                  c.tipo_documento, c.documento, c.direccion AS direccion_cliente, c.telefono AS telefono_cliente,
                  c.codigo_cliente,
                  COALESCE(t.tasa_bcv, f.tasa_bcv) AS tasa_bcv,
                  COALESCE(t.fecha_tasa, f.fecha_tasa) AS fecha_tasa,
                  COALESCE(t.subtotal_bs, f.subtotal_bs) AS subtotal_bs,
                  COALESCE(t.monto_iva_bs, f.iva_bs) AS iva_bs,
                  COALESCE(t.total_bs, f.total_bs) AS total_bs,
                  f.observacion
           FROM facturas f JOIN clientes c ON c.id_cliente=f.id_cliente
           LEFT JOIN tasa_factura t ON t.id_factura=f.id_factura
           WHERE f.id_factura=%s""", (id_factura,), uno=True)
    if not f:
        return None, [], []
    detalle = db.consulta(
        """SELECT p.codigo_piston AS codigo, p.descripcion, d.cantidad, d.precio_unitario, d.subtotal_linea
           FROM detalle_factura d JOIN pistones p ON p.id_piston=d.id_piston
           WHERE d.id_factura=%s ORDER BY d.id_detalle""", (id_factura,))
    pagos = db.consulta(
        """SELECT m.nombre_metodo, dp.monto, dp.moneda, dp.tasa_aplicada, dp.referencia,
                  dp.fecha_pago, dp.observacion, dp.estado
           FROM pago pg JOIN detalle_pago dp ON dp.id_pago=pg.id_pago
           JOIN metodo_pago m ON m.id_metodo_pago=dp.metodo_pago
           WHERE pg.id_factura=%s ORDER BY dp.id_detalle_pago""", (id_factura,))
    return f, detalle, pagos


def emitir_factura(id_cliente: int, id_usuario: int, items: list[dict], tasa, fecha_tasa, fuente: str,
                   pagos: list[dict], iva_porcentaje: Decimal = IVA, total_esperado=None) -> dict:
    """Emite la factura completa en UNA transacción: cabecera, detalle, stock, movimientos y pagos.

    items: [{"id_piston": int, "cantidad": int}]
    pagos: [{"id_metodo": int, "monto": Decimal, "moneda": "USD"|"VES", "referencia": str|None}]
           El monto va en la moneda realmente recibida; los VES se convierten con la tasa de la factura.
    Los precios se releen del precio vigente al facturar (no se confía en el que mostraba la pantalla).
    """
    if not items:
        raise ValueError("La factura debe contener al menos un pistón.")
    if not pagos:
        raise ValueError("Debe registrar al menos un pago.")
    tasa = mon.D(tasa)
    if tasa <= 0:
        raise ValueError("No hay una tasa BCV válida para emitir la factura.")
    iva_porcentaje = mon.D(iva_porcentaje)

    with db.transaccion() as (_conn, cur):
        cur.execute("SELECT id_cliente FROM clientes WHERE id_cliente=%s", (id_cliente,))
        if not cur.fetchone():
            raise ValueError("El cliente seleccionado ya no existe en la base de datos.")

        # ---- líneas (con bloqueo de stock)
        lineas, subtotal = [], Decimal("0")
        for item in items:
            pid, cantidad = int(item["id_piston"]), int(item["cantidad"])
            if cantidad <= 0:
                raise ValueError("La cantidad debe ser mayor que cero.")
            cur.execute(db.SQL_STOCK_BLOQUEAR, (pid,))
            fila = cur.fetchone()
            if not fila:
                raise ValueError(f"El pistón con ID {pid} ya no existe en el inventario.")
            stock, activo = int(fila[0]), bool(fila[1])
            cur.execute("SELECT codigo_piston FROM pistones WHERE id_piston=%s", (pid,))
            codigo = cur.fetchone()[0]
            if not activo:
                raise ValueError(f"El pistón {codigo} está desactivado y no se puede facturar. Quítelo de la orden.")
            if stock < cantidad:
                raise ValueError(f"Stock insuficiente para {codigo}. Disponible: {stock}.")
            cur.execute(db.SQL_PRECIO_VIGENTE, (pid,))
            fp = cur.fetchone()
            precio = mon.q2(fp[0]) if fp else Decimal("0")
            if precio <= 0:
                raise ValueError(f"El pistón {codigo} no tiene precio de venta. Asígnelo en Inventario → Modificar precio.")
            linea = mon.q2(precio * cantidad)
            subtotal += linea
            lineas.append({"id_piston": pid, "codigo": codigo, "cantidad": cantidad, "precio": precio,
                           "linea": linea, "stock": stock})

        subtotal = mon.q2(subtotal)
        iva = mon.q2(subtotal * iva_porcentaje)
        total = subtotal + iva
        sub_bs, iva_bs, total_bs = mon.desglose_bs(subtotal, iva, tasa)

        if total_esperado is not None and abs(total - mon.q2(total_esperado)) > TOLERANCIA:
            raise ValueError(f"El total cambió (precio actualizado) de {mon.fmt_usd(total_esperado)} a "
                             f"{mon.fmt_usd(total)}. Cierre este cuadro y vuelva a registrar el pago.")

        # ---- pagos (cada uno en su moneda; se verifica el total en USD)
        pagos_ok, pagado_usd = [], Decimal("0")
        for p in pagos:
            monto = mon.q2(p["monto"])
            moneda = str(p.get("moneda", "USD")).strip().upper()
            if monto <= 0:
                raise ValueError("El monto de cada pago debe ser mayor que cero.")
            if moneda not in ("USD", "VES"):
                raise ValueError("La moneda del pago debe ser USD o VES.")
            equivalente = monto if moneda == "USD" else mon.a_usd(monto, tasa)
            pagado_usd += equivalente
            pagos_ok.append({"id_metodo": int(p["id_metodo"]), "monto": monto, "moneda": moneda,
                             "tasa": tasa if moneda == "VES" else None,
                             "referencia": (p.get("referencia") or None), "usd": equivalente})
        if abs(pagado_usd - total) > TOLERANCIA:
            raise ValueError(f"Los pagos registrados ({mon.fmt_usd(pagado_usd)}) no coinciden con el total de la "
                             f"factura ({mon.fmt_usd(total)}).")

        # ---- factura (número definitivo = id, asignado tras insertar para evitar choques entre cajas)
        cur.execute(
            """INSERT INTO facturas(nro_factura,id_cliente,id_usuario,fecha_hora,subtotal,monto_iva,total,estado,
                  tasa_bcv,fecha_tasa,subtotal_bs,iva_bs,total_bs,moneda_base,observacion)
               VALUES(%s,%s,%s,NOW(),%s,%s,%s,'EMITIDA',%s,%s,%s,%s,%s,'USD',%s)""",
            ("TMP-" + uuid.uuid4().hex[:14], id_cliente, id_usuario, subtotal, iva, total,
             tasa, fecha_tasa, sub_bs, iva_bs, total_bs, f"Tasa consultada: {fuente}"[:250]))
        fid = cur.lastrowid
        numero = f"F-{fid:06d}"
        cur.execute("UPDATE facturas SET nro_factura=%s WHERE id_factura=%s", (numero, fid))
        cur.execute(
            """INSERT INTO tasa_factura(id_factura,tasa_bcv,fecha_tasa,subtotal_bs,monto_iva_bs,total_bs)
               VALUES(%s,%s,%s,%s,%s,%s)""", (fid, tasa, fecha_tasa, sub_bs, iva_bs, total_bs))

        for ln in lineas:
            cur.execute(
                """INSERT INTO detalle_factura(id_factura,id_piston,cantidad,precio_unitario,subtotal_linea)
                   VALUES(%s,%s,%s,%s,%s)""", (fid, ln["id_piston"], ln["cantidad"], ln["precio"], ln["linea"]))
            nuevo = ln["stock"] - ln["cantidad"]
            cur.execute(db.SQL_STOCK_FIJAR, (ln["id_piston"], nuevo))
            cur.execute(
                """INSERT INTO movimientos_inventario(id_piston,tipo,cantidad,motivo,id_usuario,id_factura,
                      stock_anterior,stock_nuevo) VALUES(%s,'SALIDA',%s,%s,%s,%s,%s,%s)""",
                (ln["id_piston"], ln["cantidad"], f"Venta facturada {numero}", id_usuario, fid, ln["stock"], nuevo))

        cur.execute("INSERT INTO pago(id_factura,fecha_hora,monto_total,estado) VALUES(%s,NOW(),%s,'PAGADO')",
                    (fid, total))
        id_pago = cur.lastrowid
        for p in pagos_ok:
            cur.execute(
                """INSERT INTO detalle_pago(id_pago,metodo_pago,monto,referencia,fecha_pago,estado,moneda,
                      tasa_aplicada) VALUES(%s,%s,%s,%s,NOW(),'REGISTRADO',%s,%s)""",
                (id_pago, p["id_metodo"], p["monto"], p["referencia"], p["moneda"], p["tasa"]))

        return {"id_factura": fid, "id_pago": id_pago, "numero": numero, "subtotal": subtotal, "iva": iva,
                "total": total, "tasa": tasa, "fecha_tasa": fecha_tasa, "subtotal_bs": sub_bs, "iva_bs": iva_bs,
                "total_bs": total_bs, "items": lineas, "pagos": pagos_ok}
