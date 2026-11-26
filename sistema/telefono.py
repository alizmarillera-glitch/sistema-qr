"""Teléfonos móviles venezolanos: prefijo + siete dígitos.

El número se guarda COMPLETO en ``clientes.telefono`` (por ejemplo ``04121234567``); el prefijo y los
siete dígitos solo se separan en pantalla. Para aceptar otro prefijo, agréguelo a ``PREFIJOS_MOVIL``.
"""
import re

PREFIJOS_MOVIL = ("0412", "0414", "0416", "0422", "0424", "0426")
PREFIJO_PREDETERMINADO = "0412"
DIGITOS_NUMERO = 7


def dividir(texto):
    """'(prefijo, número)' de un teléfono guardado, o None si no tiene el formato móvil venezolano.

    Acepta guiones, espacios, paréntesis, +58 y la forma sin cero inicial (4121234567).
    """
    dig = re.sub(r"\D", "", "" if texto is None else str(texto))
    if dig.startswith("58") and len(dig) == 12:
        dig = "0" + dig[2:]
    elif len(dig) == 10 and dig.startswith("4"):
        dig = "0" + dig
    if len(dig) == 4 + DIGITOS_NUMERO and dig.startswith("04"):
        return dig[:4], dig[4:]
    return None


def unir(prefijo, numero):
    return f"{prefijo}{numero}" if numero else ""


def error_partes(prefijo, numero, prefijos=PREFIJOS_MOVIL):
    """Mensaje para el usuario si prefijo + número no se pueden guardar; None si están bien."""
    numero = (numero or "").strip()
    if prefijo not in prefijos:
        return "Seleccione un prefijo telefónico válido."
    if not numero:
        return "El teléfono es obligatorio."
    if not numero.isdigit():
        return "El número telefónico solo puede contener dígitos."
    if len(numero) != DIGITOS_NUMERO:
        return (f"El teléfono está incompleto: después del prefijo {prefijo} debe escribir "
                f"exactamente {DIGITOS_NUMERO} dígitos (escribió {len(numero)}).")
    return None


def error_completo(telefono, prefijos=PREFIJOS_MOVIL):
    """Misma validación sobre un teléfono completo (última barrera antes de guardar en MySQL)."""
    partes = dividir(telefono)
    if partes is None:
        return (f"El teléfono debe tener prefijo y {DIGITOS_NUMERO} dígitos (ejemplo: "
                f"{PREFIJO_PREDETERMINADO}1234567).")
    return error_partes(partes[0], partes[1], prefijos)
