# -*- coding: utf-8 -*-
"""Prueba del comprobante PDF SIN base de datos: dibuja facturas de ejemplo (no se guardan en ningún sitio).

Uso (desde la carpeta Sistema_QR_V3):   py pruebas/probar_comprobante_pdf.py
Crea los PDF en la carpeta «pruebas/salida_pdf». Sirve para revisar el diseño y que ningún texto se corte.
"""
import datetime
import os
import sys
import types
from decimal import Decimal as D

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "sistema"))
try:                                      # si mysql-connector no está instalado, se simula: aquí no se usa la base
    import mysql.connector  # noqa: F401
except ImportError:
    m = types.ModuleType("mysql"); mc = types.ModuleType("mysql.connector"); m.connector = mc
    sys.modules.update({"mysql": m, "mysql.connector": mc})

import comprobante_pdf as cp  # noqa: E402

SALIDA = os.path.join(AQUI, "salida_pdf")
os.makedirs(SALIDA, exist_ok=True)
EMPRESA = {"razon_social": "MANUFACTURAS DE ALUMINIO I, C.A.", "rif": "J-3108592-3",
           "direccion_fiscal": "Calle D, local N° 48, urbanización Agroindustrial, El Recreo, Valencia, Carabobo. Código postal 2001.",
           "telefono": "", "correo": ""}
CLIENTE = {"nombre": "Cliente de Prueba", "tipo": "V", "numero": "12345678", "documento": "V-12345678",
           "direccion": "Av. Principal, edificio X, piso 2, oficina 5, sector Centro, Caracas", "telefono": "0412-1234567",
           "codigo": "CLI-000012"}


def base(nro, lineas, pagos, tasa="886.2271"):
    sub = sum(D(l["importe_usd"]) for l in lineas)
    iva = (sub * D("0.16")).quantize(D("0.01"))
    d = {"empresa": EMPRESA, "nro_factura": nro, "numero_comprobante": nro[2:], "estado": "EMITIDA",
         "fecha_emision": datetime.datetime(2026, 10, 26, 8, 17), "cliente": CLIENTE, "lineas": lineas, "pagos": pagos,
         "subtotal_usd": sub, "iva_usd": iva, "total_usd": sub + iva, "tasa": D(tasa) if tasa else None,
         "fecha_tasa": datetime.date(2026, 10, 23)}
    if tasa:
        t = D(tasa)
        d["subtotal_bs"], d["iva_bs"] = (sub * t).quantize(D("0.01")), (iva * t).quantize(D("0.01"))
        d["total_bs"] = d["subtotal_bs"] + d["iva_bs"]
    else:
        d["subtotal_bs"] = d["iva_bs"] = d["total_bs"] = None
    return d


def linea(cod, desc, cant, precio):
    return {"codigo": cod, "descripcion": desc, "cantidad": cant, "precio_usd": D(precio),
            "importe_usd": D(precio) * cant}


L1 = [linea("EPV-4029R-STD-3", "Pistón de aluminio EPV-4029R estándar", 5, "20.00")]
LMUCHAS = [linea(f"EPV-{1000 + i}-STD", "Pistón de aluminio de alto rendimiento con descripción larga para comprobar "
                 "que el texto se ajusta en varias líneas sin cortarse", 1 + i % 4, f"{12 + i}.50") for i in range(40)]
P1 = [{"metodo": "Zelle", "monto": D("60.00"), "moneda": "USD", "tasa": None, "referencia": "ZL-884412",
       "fecha": datetime.datetime(2026, 10, 26, 8, 17), "observacion": "Titular: J. Pérez", "estado": "REGISTRADO"},
      {"metodo": "Pago móvil", "monto": D("49626.37"), "moneda": "VES", "tasa": D("886.2271"), "referencia": "00123456",
       "fecha": datetime.datetime(2026, 10, 26, 8, 17), "observacion": None, "estado": "REGISTRADO"},
      {"metodo": "Divisa", "monto": D("0.01"), "moneda": "USD", "tasa": None, "referencia": None,
       "fecha": datetime.datetime(2026, 10, 26, 8, 17), "observacion": None, "estado": "REGISTRADO"}]

CASOS = {
    "Comprobante_Pago_000015.pdf": base("F-000015", L1, P1),
    "prueba_muchas_lineas.pdf": base("F-000016", LMUCHAS, P1),
    "prueba_historica_sin_tasa.pdf": base("F-000001", L1, [], tasa=None),
}
if __name__ == "__main__":
    for nombre, datos in CASOS.items():
        print(cp.generar_pdf(datos, os.path.join(SALIDA, nombre)))
    print("Nombre sugerido:", cp.nombre_sugerido("F-000125"))
