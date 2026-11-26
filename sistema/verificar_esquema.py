# -*- coding: utf-8 -*-
"""Verifica tablas, columnas y relaciones de instalacion_limpia sin modificar datos."""
from __future__ import annotations
import conexion as db

TABLAS = {
    "ROLES": {"id_rol", "nombre_rol", "descripcion"},
    "USUARIOS": {"id_usuario", "id_rol", "nombre_usuario", "clave_hash", "estado", "fecha_creacion", "etapa_asignada"},
    "LOG_USUARIOS": {"id_log", "id_usuario", "fecha_hora", "accion", "descripcion", "resultado"},
    "DETALLE_PAGO": {"id_detalle_pago", "id_pago", "metodo_pago", "monto", "referencia", "fecha_pago", "estado", "moneda", "tasa_aplicada", "observacion"},
    "METODO_PAGO": {"id_metodo_pago", "nombre_metodo", "estado"},
    "CLIENTES": {"id_cliente", "tipo_documento", "documento", "nombre_razon_social", "telefono", "correo", "direccion", "fecha_registro", "codigo_cliente"},
    "FACTURAS": {"id_factura", "nro_factura", "id_cliente", "id_usuario", "fecha_hora", "subtotal", "monto_iva", "total", "estado", "tasa_bcv", "fecha_tasa", "subtotal_bs", "iva_bs", "total_bs", "moneda_base", "observacion"},
    "PAGO": {"id_pago", "id_factura", "fecha_hora", "monto_total", "estado"},
    "DETALLE_FACTURA": {"id_detalle", "id_factura", "id_piston", "cantidad", "precio_unitario", "subtotal_linea"},
    "PRECIOS_PISTONES": {"id_precio", "id_piston", "precio_base", "moneda", "vigente_desde", "vigente_hasta"},
    "PISTONES": {"id_piston", "codigo_piston", "descripcion", "diametro_mm", "sobremedida_mm", "altura_compresion_mm", "diametro_pasador_mm", "especificacion_camara", "activo", "tipo_auto", "anio", "numero_piezas", "fecha_fabricacion", "offset_mm", "trazabilidad", "diametro_cilindro_mm", "imagen", "stock_actual", "stock_minimo", "fecha_creacion", "fecha_actualizacion"},
    "EXISTENCIAS": {"id_piston", "stock"},
    "TASA_FACTURA": {"id_factura", "tasa_bcv", "fecha_tasa", "subtotal_bs", "monto_iva_bs", "total_bs"},
    "CODIGOS_QR": {"id_qr", "id_piston", "contenido_qr", "ruta_imagen", "fecha_generacion", "estado"},
    "MOVIMIENTOS_INVENTARIO": {"id_movimiento", "id_piston", "tipo", "cantidad", "motivo", "fecha_hora", "id_usuario", "id_factura", "stock_anterior", "stock_nuevo"},
    "TASAS_BCV": {"id_tasa", "moneda_origen", "moneda_destino", "tasa", "fecha_efectiva", "fecha_consulta", "fuente", "validada"},
}


def main():
    conn = db.conectar()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DATABASE()")
        print("Base de datos:", cur.fetchone()[0])
        cur.execute("SHOW TABLES")
        existentes = {r[0].upper() for r in cur.fetchall()}
        errores = []
        for tabla, esperadas in TABLAS.items():
            if tabla not in existentes:
                errores.append(f"Falta la tabla {tabla}")
                continue
            cur.execute(f"SHOW COLUMNS FROM `{tabla}`")
            reales = {r[0].lower() for r in cur.fetchall()}
            faltan = esperadas - reales
            if faltan:
                errores.append(f"{tabla}: faltan columnas {', '.join(sorted(faltan))}")
        cur.execute("""SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
                       WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL""")
        total_fk = cur.fetchone()[0]
        if errores:
            print("RESULTADO: ESQUEMA INCOMPLETO")
            for e in errores:
                print(" -", e)
            raise SystemExit(1)
        print(f"RESULTADO: OK — {len(TABLAS)} tablas detectadas y columnas requeridas presentes.")
        print(f"Relaciones FK registradas: {total_fk}")
        print("Esta comprobación no modifica ni elimina datos.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
