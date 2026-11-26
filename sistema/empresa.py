# -*- coding: utf-8 -*-
"""Datos de la empresa que se imprimen en el comprobante de pago en PDF.

La base de datos de Sistema_QR no guarda los datos fiscales de la empresa (solo clientes, facturas, pagos, etc.),
así que se leen de ``recursos/empresa.json``. Para completarlos basta abrir ese archivo con el Bloc de notas,
escribir el RIF y la dirección fiscal reales entre las comillas y guardar. No hace falta tocar la base de datos.

    {
      "razon_social": "MANUFACTURAS DE ALUMINIO I, C.A.",
      "rif": "J-00000000-0",
      "direccion_fiscal": "Calle, zona, ciudad, estado",
      "telefono": "",
      "correo": ""
    }

Nada se inventa: lo que esté vacío simplemente no se imprime (y el programa avisa antes de generar el PDF).
"""
from __future__ import annotations
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_EMPRESA = os.path.join(BASE, "recursos", "empresa.json")

RAZON_SOCIAL_POR_DEFECTO = "MANUFACTURAS DE ALUMINIO I, C.A."   # el nombre que ya usa el sistema en todas sus pantallas
CAMPOS = ("razon_social", "rif", "direccion_fiscal", "telefono", "correo")


def cargar() -> dict:
    """Devuelve los datos de la empresa (todas las claves de CAMPOS, como texto; vacío si no están registrados)."""
    datos = {k: "" for k in CAMPOS}
    try:
        with open(RUTA_EMPRESA, "r", encoding="utf-8-sig") as f:
            leido = json.load(f)
        if isinstance(leido, dict):
            for k in CAMPOS:
                v = leido.get(k)
                datos[k] = " ".join(str(v).split()) if v is not None else ""
    except (OSError, ValueError):
        pass          # archivo ausente o mal escrito: se usa solo el nombre por defecto
    if not datos["razon_social"]:
        datos["razon_social"] = RAZON_SOCIAL_POR_DEFECTO
    return datos


def faltantes(datos: dict | None = None) -> list[str]:
    """Nombres legibles de los datos obligatorios que todavía no están registrados."""
    datos = datos or cargar()
    etiquetas = (("rif", "RIF"), ("direccion_fiscal", "Dirección fiscal"))
    return [nombre for clave, nombre in etiquetas if not datos.get(clave)]
