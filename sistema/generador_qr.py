import os
import json
import qrcode

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(BASE, "qrs_generados")

# Datos técnicos del pistón según la tabla PISTONES del modelo relacional.
CAMPOS_QR = [
    ("codigo", "Código"), ("descripcion", "Descripción"), ("diametro_mm", "Diámetro (mm)"),
    ("sobremedida_mm", "Sobremedida (mm)"), ("altura_compresion_mm", "Altura de compresión (mm)"),
    ("diametro_pasador_mm", "Diámetro del pasador (mm)"), ("especificacion_camara", "Especificación de cámara"),
]

# Claves cortas = mismo contenido, menos módulos del QR y mejor lectura.
CLAVES = {
    "codigo": "c", "descripcion": "d", "diametro_mm": "dm", "sobremedida_mm": "sm",
    "altura_compresion_mm": "ac", "diametro_pasador_mm": "dp", "especificacion_camara": "ec",
}
INV_CLAVES = {v: k for k, v in CLAVES.items()}

# Etiquetas ya impresas con formatos anteriores (solo se usa para leer el código).
CLAVES_V4 = {"c": "codigo", "a": "descripcion", "dp": "diametro_mm"}
CAMPOS_TEXTO_ANTIGUO = [("codigo", "Código"), ("descripcion", "Tipo de auto / motor"), ("diametro_mm", "Diámetro pistón (mm)")]


def _txt(v):
    return "" if v is None else str(v)


def datos_qr(p):
    datos = {CLAVES[k]: _txt(p.get(k)) for k, _ in CAMPOS_QR}
    return "PISTON_QR_V5|" + json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def crear_qr(p):
    os.makedirs(CARPETA, exist_ok=True)
    ruta = os.path.join(CARPETA, f"{p['codigo']}.png")
    qr = qrcode.QRCode(
        version=None,
        box_size=12,
        border=4,
        error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    qr.add_data(datos_qr(p)); qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(ruta)
    return ruta


def leer_datos(texto):
    if not texto:
        return {}
    texto = texto.strip()

    # Formato actual.
    if texto.startswith("PISTON_QR_V5|"):
        try:
            raw = json.loads(texto.split("|", 1)[1])
            return {INV_CLAVES[k]: str(v) for k, v in raw.items() if k in INV_CLAVES}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

    # Compatibilidad con etiquetas anteriores (V4 compacto).
    if texto.startswith("PISTON_QR_V4|"):
        try:
            raw = json.loads(texto.split("|", 1)[1])
            return {CLAVES_V4[k]: str(v) for k, v in raw.items() if k in CLAVES_V4}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

    if texto.startswith("PIST:"):
        return {"codigo": texto[5:].strip()}
    if not (texto.startswith("PISTON_QR_V2") or texto.startswith("PISTON_QR_V3")):
        return {"codigo": texto}
    datos = {}
    for linea in texto.splitlines()[1:]:
        if ":" not in linea:
            continue
        etiqueta, valor = linea.split(":", 1)
        etiqueta, valor = etiqueta.strip(), valor.strip()
        for clave, nombre in CAMPOS_TEXTO_ANTIGUO:
            if etiqueta == nombre:
                datos[clave] = valor
                break
    return datos


def leer_codigo(texto):
    return leer_datos(texto).get("codigo", "")
