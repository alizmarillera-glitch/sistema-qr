# -*- coding: utf-8 -*-
"""Consulta de la tasa oficial USD/Bs. del BCV.

Orden de consulta:
  1. Página oficial del BCV (bcv.org.ve). Su certificado SSL suele fallar en
     muchos equipos; si eso ocurre se reintenta SIN verificar el certificado
     (solo para esta lectura pública de un número) y la fuente lo indica.
  2. ve.dolarapi.com (tasa oficial).
  3. pydolarve.org (monitor BCV).
  4. bcv.today (respaldo anterior del sistema).

obtener_tasa() devuelve (tasa: Decimal, fecha_efectiva: date, fuente: str) o
lanza RuntimeError con el detalle de lo que falló en cada fuente.
"""
from __future__ import annotations
import datetime
import json
import re
import ssl
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

BCV_URL = "https://www.bcv.org.ve/"
DOLARAPI_URL = "https://ve.dolarapi.com/v1/dolares/oficial"
PYDOLAR_URL = "https://pydolarve.org/api/v2/dollar?page=bcv&monitor=usd"
INTERMEDIARIO_URL = "https://bcv.today/api/v1/rate.json"
TIMEOUT = 10
_UA = "Mozilla/5.0 (compatible; SistemaQR/1.0; consulta de tasa BCV)"


# --------------------------------------------------------------------------- red
def _get(url, verificar_ssl=True):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    ctx = None if verificar_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _es_error_ssl(exc):
    if isinstance(exc, ssl.SSLError):
        return True
    return isinstance(exc, urllib.error.URLError) and isinstance(getattr(exc, "reason", None), ssl.SSLError)


# --------------------------------------------------------------------------- análisis
_NUM_VE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+),(\d{2,8})")
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
          "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def _a_decimal(valor):
    """'36,5023' / '1.234,56' / 36.5 / '36.5' -> Decimal positivo o None."""
    try:
        if isinstance(valor, (int, float, Decimal)):
            d = Decimal(str(valor))
        else:
            s = str(valor).strip()
            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return d if d > 0 else None


def _fecha_texto(texto):
    """Busca una fecha en ISO (2026-11-16), dd/mm/aaaa o '16 Noviembre 2026'."""
    if not texto:
        return None
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", str(texto))
    try:
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.search(r"([0-3]?\d)[/\-]([01]?\d)[/\-](20\d{2})", str(texto))
        if m:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.search(r"([0-3]?\d)\s+(?:de\s+)?([A-Za-zñÑáéíóú]+)\s+(?:de\s+)?(20\d{2})", str(texto))
        if m and m.group(2).lower() in _MESES:
            return datetime.date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None
    return None


def parsear_bcv_html(html):
    """Extrae (tasa USD, fecha_valor|None) del HTML del BCV. Lanza ValueError si no la encuentra."""
    m = re.search(r'id=["\']dolar["\']', html, re.I)
    if not m:
        raise ValueError("no se encontró el bloque del dólar en la página")
    bloque = html[m.end(): m.end() + 1500]
    n = _NUM_VE.search(bloque)
    if not n:
        raise ValueError("no se encontró el valor del dólar en la página")
    tasa = _a_decimal(n.group(0))
    if not tasa:
        raise ValueError("el valor del dólar no es válido")
    # Fecha valor: atributo content="2026-11-17T00:00:00-04:00" o texto con la fecha.
    fecha = None
    fm = re.search(r'content=["\'](20\d{2}-\d{2}-\d{2})T', html)
    if fm:
        fecha = _fecha_texto(fm.group(1))
    if not fecha:
        fv = re.search(r"Fecha\s+Valor[^0-9A-Za-z]*(.{0,60})", html, re.I | re.S)
        fecha = _fecha_texto(fv.group(1)) if fv else None
    return tasa, fecha


def _buscar_numero(obj, claves):
    """Busca (en profundidad) el primer valor numérico válido bajo alguna de las claves."""
    if isinstance(obj, dict):
        for k in claves:
            for kk, vv in obj.items():
                if str(kk).lower() == k and not isinstance(vv, (dict, list)):
                    d = _a_decimal(vv)
                    if d:
                        return d
        for vv in obj.values():
            if isinstance(vv, (dict, list)):
                r = _buscar_numero(vv, claves)
                if r:
                    return r
    elif isinstance(obj, list):
        for vv in obj:
            r = _buscar_numero(vv, claves)
            if r:
                return r
    return None


def _buscar_fecha(obj):
    if isinstance(obj, dict):
        for k in ("fechaactualizacion", "last_update", "effective_date", "date", "updated_at", "fecha"):
            for kk, vv in obj.items():
                if str(kk).lower() == k and not isinstance(vv, (dict, list)):
                    f = _fecha_texto(vv)
                    if f:
                        return f
        for vv in obj.values():
            if isinstance(vv, (dict, list)):
                f = _buscar_fecha(vv)
                if f:
                    return f
    elif isinstance(obj, list):
        for vv in obj:
            f = _buscar_fecha(vv)
            if f:
                return f
    return None


def parsear_json_tasa(texto):
    """Para las APIs JSON: devuelve (tasa, fecha|None)."""
    data = json.loads(texto)
    tasa = _buscar_numero(data, ("promedio", "price", "venta", "rate", "tasa", "usd", "value", "dolar"))
    if not tasa:
        raise ValueError("la respuesta no contiene una tasa válida")
    return tasa, _buscar_fecha(data)


# --------------------------------------------------------------------------- consulta
def _consultar_bcv():
    try:
        html = _get(BCV_URL, True)
        nota = "BCV (sitio oficial)"
    except Exception as exc:
        if not _es_error_ssl(exc):
            raise
        html = _get(BCV_URL, False)
        nota = "BCV (sitio oficial; certificado SSL no verificado en este equipo)"
    tasa, fecha = parsear_bcv_html(html)
    return tasa, fecha or datetime.date.today(), nota


def _consultar_json(url, nombre):
    tasa, fecha = parsear_json_tasa(_get(url))
    return tasa, fecha or datetime.date.today(), nombre


_FUENTES = (
    ("bcv.org.ve", _consultar_bcv),
    ("dolarapi", lambda: _consultar_json(DOLARAPI_URL, "BCV vía ve.dolarapi.com (verificar en bcv.org.ve)")),
    ("pydolarve", lambda: _consultar_json(PYDOLAR_URL, "BCV vía pydolarve.org (verificar en bcv.org.ve)")),
    ("bcv.today", lambda: _consultar_json(INTERMEDIARIO_URL, "BCV vía bcv.today (verificar en bcv.org.ve)")),
)


def obtener_tasa():
    """Devuelve (tasa Decimal, fecha_efectiva, fuente). Falla con el detalle de cada fuente."""
    errores = []
    for nombre, funcion in _FUENTES:
        try:
            tasa, fecha, fuente = funcion()
            if tasa and tasa > 0:
                return tasa, fecha, fuente
            errores.append(f"{nombre}: valor no válido")
        except Exception as exc:
            errores.append(f"{nombre}: {type(exc).__name__}: {exc}")
    raise RuntimeError("No se pudo consultar la tasa BCV en línea.\n\n" + "\n".join(f" • {e}" for e in errores))
