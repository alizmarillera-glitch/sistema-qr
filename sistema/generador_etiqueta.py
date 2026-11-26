import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from PIL import Image, ImageDraw, ImageFont
from generador_qr import crear_qr

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(BASE, "etiquetas_generadas")

NAVY = "#102A43"; BLUE = "#1F5A85"; GRAY = "#627D98"; LINE = "#D7DEE6"


def _f(size, bold=False):
    for n in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _txt(v):
    return " ".join(str(v).split()) if v not in (None, "") else ""


def _medida(v):
    """100.789 -> «100,789 mm (3.9681")»: milímetros con coma y pulgadas con punto. Vacío -> «—»."""
    try:
        mm = Decimal(str(v).replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        return "—"
    pulgadas = (mm / Decimal("25.4")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f'{mm:.3f}'.replace(".", ",") + f' mm ({pulgadas}")'


def _lineas(d, texto, fuente, ancho, max_lineas):
    """Parte el texto en líneas que caben en ``ancho`` píxeles; la última termina en «…» si sobra texto."""
    palabras, lineas, actual = texto.split(), [], ""
    for pal in palabras:
        prueba = (actual + " " + pal).strip()
        if d.textlength(prueba, font=fuente) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = pal
    if actual:
        lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        ultima = lineas[-1]
        while ultima and d.textlength(ultima + "…", font=fuente) > ancho:
            ultima = ultima[:-1]
        lineas[-1] = ultima.rstrip() + "…"
    for i, ln in enumerate(lineas):                       # una sola palabra demasiado larga: se recorta
        while len(ln) > 1 and d.textlength(ln, font=fuente) > ancho:
            ln = ln[:-2] + "…"
        lineas[i] = ln
    return lineas or ["—"]


def _ajustar_imagen(ruta, max_size):
    try:
        im = Image.open(ruta).convert("RGB")
        im.thumbnail(max_size)
        return im
    except Exception:
        return None


def crear_etiqueta(p):
    """Etiqueta del pistón con los mismos datos del formulario de registro.

    1 Información general: número de piezas, offset, fecha, código del pistón y su código QR.
    2 Información del motor: aplicación y características adicionales.
    3 Tipo de cabeza: imagen del pistón.
    4 Medidas: diámetro del pistón y del cilindro (mm y pulgadas).
    5 Trazabilidad.
    """
    os.makedirs(CARPETA, exist_ok=True)
    qr_path = crear_qr(p)
    W, H = 1000, 730
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)

    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=16, outline=NAVY, width=4)
    d.rectangle([12, 12, W - 12, 82], fill=NAVY)
    d.text((32, 26), "MANUFACTURAS DE ALUMINIO I, C.A.", font=_f(28, True), fill="white")
    d.text((32, 61), "IDENTIFICACIÓN Y TRAZABILIDAD DEL PISTÓN", font=_f(13, True), fill="#DCE6F0")

    XL, ANCHO_L = 32, 536          # columna de datos
    X0, X1 = 596, 968              # columna visual (imagen y QR)

    def seccion(y, titulo):
        d.text((XL, y), titulo, font=_f(13, True), fill=BLUE)
        d.line([XL, y + 22, XL + ANCHO_L, y + 22], fill=LINE, width=2)

    def dato(x, y, rotulo, valor, tam=24, ancho=ANCHO_L, max_lineas=1, color=NAVY):
        """Rótulo gris + valor en negrita (hasta ``max_lineas``). Devuelve la y siguiente al dato."""
        d.text((x, y), rotulo, font=_f(12, True), fill=GRAY)
        fuente = _f(tam, True)
        y += 19
        for ln in _lineas(d, valor or "—", fuente, ancho, max_lineas):
            d.text((x, y), ln, font=fuente, fill=color)
            y += tam + 6
        return y

    # Columna izquierda: cada bloque empieza donde termina el anterior, así no quedan huecos ni se solapan.
    # 1 · INFORMACIÓN GENERAL
    seccion(98, "1 · INFORMACIÓN GENERAL")
    y = dato(XL, 128, "CÓDIGO DEL PISTÓN", _txt(p.get("codigo")), tam=36) + 6
    y2 = dato(XL, y, "NÚMERO DE PIEZAS", _txt(p.get("numero_piezas")), ancho=150)
    dato(XL + 180, y, "OFFSET", _txt(p.get("offset_mm")), ancho=150)
    dato(XL + 340, y, "FECHA", _txt(p.get("fecha_fabricacion")), ancho=196)

    # 2 · INFORMACIÓN DEL MOTOR
    y = y2 + 12
    seccion(y, "2 · INFORMACIÓN DEL MOTOR")
    y = dato(XL, y + 32, "APLICACIÓN", _txt(p.get("descripcion")), tam=22, max_lineas=2)
    y = dato(XL, y + 4, "CARACTERÍSTICAS ADICIONALES", _txt(p.get("caracteristicas_adicionales")),
             tam=22, max_lineas=2)

    # 4 · MEDIDAS
    y += 12
    seccion(y, "4 · MEDIDAS")
    y = dato(XL, y + 32, "DIÁMETRO DEL PISTÓN", _medida(p.get("diametro_mm")), tam=22)
    y = dato(XL, y + 4, "DIÁMETRO DEL CILINDRO", _medida(p.get("diametro_cilindro_mm")), tam=22)

    # 5 · TRAZABILIDAD
    y += 12
    seccion(y, "5 · TRAZABILIDAD")
    dato(XL, y + 32, "TRAZABILIDAD", _txt(p.get("trazabilidad")), tam=24)

    # 3 · TIPO DE CABEZA (imagen del pistón)
    d.rounded_rectangle([X0, 100, X1, 350], radius=12, outline=LINE, width=2, fill="#F7F9FB")
    d.text((X0 + 16, 112), "3 · TIPO DE CABEZA", font=_f(13, True), fill=BLUE)
    foto = _ajustar_imagen(p.get("imagen", ""), (X1 - X0 - 24, 195))
    if foto:
        im.paste(foto, (X0 + ((X1 - X0) - foto.width) // 2, 140 + (195 - foto.height) // 2))
    else:
        d.text((X0 + 128, 228), "Sin imagen", font=_f(18), fill=GRAY)

    # Código QR (representación gráfica del código del pistón)
    d.rounded_rectangle([X0, 364, X1, 700], radius=12, outline=LINE, width=2, fill="white")
    d.text((X0 + 16, 376), "CÓDIGO QR", font=_f(13, True), fill=BLUE)
    q = Image.open(qr_path).convert("RGB")
    q.thumbnail((250, 250))
    im.paste(q, (X0 + ((X1 - X0) - q.width) // 2, 402))
    codigo = _txt(p.get("codigo"))
    f_cod = _f(16, True)
    d.text((X0 + ((X1 - X0) - d.textlength(codigo, font=f_cod)) / 2, 662), codigo, font=f_cod, fill=NAVY)

    ruta = os.path.join(CARPETA, f"ETQ-{p['codigo']}.png")
    im.save(ruta)
    return qr_path, ruta
