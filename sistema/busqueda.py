# -*- coding: utf-8 -*-
"""Búsqueda dinámica del inventario de pistones.

Todo el trabajo se hace en memoria sobre una COPIA de los resultados: la base de datos y la lista original
(``filas``) no se modifican ni se reordenan. ``buscar`` devuelve una lista nueva.

Reglas
------
* No distingue mayúsculas/minúsculas ni tildes («Hyundai» = «hyundai», «Camión» = «camion»).
* La consulta se divide en palabras y TODAS deben aparecer (en cualquier campo): «ford fiesta 1.6».
* Campos donde se busca: código, descripción (aquí viven marca, modelo, motor y aplicación del vehículo) y
  especificación de cámara. Si más adelante la tabla incorpora columnas propias (marca, modelo, motor…), basta
  con nombrarlas en ``CAMPOS_BUSQUEDA``: se usan si existen y se ignoran si no.
* El código también se compara sin guiones ni espacios («epv1725» encuentra «EPV-1725R-060-9»); solo con 4 o más
  caracteres, para que «25» no encuentre «12-54» ni «2.5» (cilindrada) encuentre códigos por casualidad.
* Sin duplicados: cada pistón aparece una sola vez (por su ``id``).

Orden de los resultados
-----------------------
* Si lo escrito coincide con el CÓDIGO de algún resultado (o no se escribió nada): orden natural por código,
  respetando su estructura alfanumérica (``12-54ASU`` < ``14-09ZA`` < ``21-12GRU`` < ``21-22`` < ``1009``;
  los números se comparan como números y no letra a letra: ``9`` < ``10``).
* En cualquier otro caso (marca, modelo, motor, aplicación, descripción): orden alfabético por descripción,
  y a igualdad, por código natural.
"""
from __future__ import annotations

import re
import unicodedata

# Campos donde se busca. Los que no existan en una fila se ignoran (ver nota arriba).
CAMPOS_BUSQUEDA = ("codigo", "descripcion", "especificacion_camara",
                   "marca", "modelo", "motor", "aplicacion", "tipo_auto", "anio")

MODO_CODIGO = "codigo"      # resultados ordenados por código natural
MODO_TEXTO = "texto"        # resultados ordenados alfabéticamente por descripción

_ESPACIOS = re.compile(r"\s+")
_SEP_CODIGO = re.compile(r"[\s\-_/]+")        # separadores que se ignoran al comparar códigos (no el punto: 1.6 != 16)
_NUMEROS = re.compile(r"(\d+)")
_SEPARADORES = re.compile(r"[\s,;]+")


def normalizar(texto) -> str:
    """Minúsculas, sin tildes y con los espacios colapsados."""
    t = unicodedata.normalize("NFKD", "" if texto is None else str(texto)).casefold()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return _ESPACIOS.sub(" ", t).strip()


MIN_COMPACTO = 4        # la comparación «sin guiones» solo se usa con 4 o más caracteres (evita falsos «25» en «12-54»)


def compacto(texto) -> str:
    """Texto normalizado sin guiones, barras ni espacios («EPV-1725R-060-9» -> «epv1725r0609»)."""
    return _SEP_CODIGO.sub("", normalizar(texto))


def _en_compacto(palabra, comp_codigo) -> bool:
    c = compacto(palabra)
    return len(c) >= MIN_COMPACTO and c in comp_codigo


def clave_codigo(codigo) -> tuple:
    """Clave de orden natural de un código alfanumérico.

    Se parte en trozos de dígitos y de texto: los dígitos se comparan como números y, en una misma posición,
    un número va antes que un texto. «EPV-1725R-060-3» -> (texto «epv-», 1725, «r-», 60, «-», 3).
    """
    clave = []
    for i, trozo in enumerate(_NUMEROS.split(normalizar(codigo))):
        if not trozo:
            continue
        clave.append((0, int(trozo), "") if i % 2 else (1, 0, trozo))
    return tuple(clave)


def _orden_codigo(fila):
    cod = fila.get("codigo")
    return clave_codigo(cod), str(cod or "")


def _orden_texto(fila):
    return normalizar(fila.get("descripcion")), _orden_codigo(fila)


def _palabras(consulta) -> list[str]:
    return [p for p in _SEPARADORES.split(normalizar(consulta)) if p]


def _texto_fila(fila) -> str:
    """Texto en el que se busca (todos los campos de ``CAMPOS_BUSQUEDA`` juntos, normalizados)."""
    return " ".join(normalizar(fila.get(c)) for c in CAMPOS_BUSQUEDA if fila.get(c) not in (None, ""))


def _en_codigo(fila, palabras) -> bool:
    """¿Todas las palabras están en el código del pistón?"""
    norm = normalizar(fila.get("codigo"))
    comp = compacto(fila.get("codigo"))
    return all(p in norm or _en_compacto(p, comp) for p in palabras)


def _coincide(fila, palabras) -> bool:
    texto = _texto_fila(fila)
    comp = compacto(fila.get("codigo"))
    return all(p in texto or _en_compacto(p, comp) for p in palabras)


def buscar(filas, consulta="") -> tuple[list[dict], str]:
    """Filtra y ordena ``filas`` según ``consulta``. Devuelve ``(resultados, modo)``.

    ``filas`` no se modifica. ``modo`` es ``MODO_CODIGO`` o ``MODO_TEXTO`` e indica cómo se ordenó.
    """
    palabras = _palabras(consulta)

    vistos, unicos = set(), []              # sin duplicados (un pistón = un id)
    for f in filas:
        ident = f.get("id", f.get("codigo"))
        if ident in vistos:
            continue
        vistos.add(ident)
        unicos.append(f)

    if not palabras:
        return sorted(unicos, key=_orden_codigo), MODO_CODIGO

    hallados = [f for f in unicos if _coincide(f, palabras)]
    por_codigo = any(_en_codigo(f, palabras) for f in hallados)
    if por_codigo:
        return sorted(hallados, key=_orden_codigo), MODO_CODIGO
    return sorted(hallados, key=_orden_texto), MODO_TEXTO
