"""Identidad visual de la empresa: logo «Manufacturas de Aluminio I, C.A.» y banner de la pantalla de acceso.

Los archivos están en ``recursos/``:
  * ``logo_empresa.png``  logo con fondo transparente y tinta negra. Para fondos oscuros se genera solo una variante blanca.
  * ``banner_login.jpg``  imagen del panel izquierdo del acceso.
Para cambiar el logo o el banner basta reemplazar esos archivos (mismo nombre). Si alguno falta, las funciones
devuelven None y la interfaz usa su marca de texto anterior, así el programa nunca deja de abrir.
"""
import os
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_LOGO = os.path.join(BASE, "recursos", "logo_empresa.png")
RUTA_BANNER = os.path.join(BASE, "recursos", "banner_login.jpg")

_cache = {}


def _logo_base():
    """Logo recortado a su contenido (sin márgenes transparentes)."""
    if "logo" not in _cache:
        try:
            img = Image.open(RUTA_LOGO).convert("RGBA")
            caja = img.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
            _cache["logo"] = img.crop(caja) if caja else img
        except Exception:
            _cache["logo"] = None
    return _cache["logo"]


def _tinta(img, rgb):
    """Misma silueta del logo pintada del color ``rgb`` (conserva la transparencia)."""
    plano = Image.new("RGBA", img.size, rgb + (255,))
    plano.putalpha(img.getchannel("A"))
    return plano


def logo_pil(ancho, claro=False):
    """Logo escalado al ancho dado. ``claro=True``: tinta blanca (para fondos oscuros o azules)."""
    base = _logo_base()
    if base is None:
        return None
    alto = max(1, round(base.height * ancho / base.width))
    img = base.resize((ancho, alto), Image.LANCZOS)
    return _tinta(img, (255, 255, 255)) if claro else img


def logo_ctk(ancho):
    """CTkImage del logo: tinta oscura en modo claro y blanca en modo oscuro (cambia sola con el tema)."""
    import customtkinter as ctk
    negro, blanco = logo_pil(ancho), logo_pil(ancho, claro=True)
    if negro is None:
        return None
    return ctk.CTkImage(light_image=negro, dark_image=blanco, size=negro.size)


def banner_pil(ancho, alto, radio=18):
    """Banner recortado al tamaño dado (sin deformarlo), con esquinas redondeadas y un filo fino."""
    clave = ("banner", ancho, alto, radio)
    if clave in _cache:
        return _cache[clave]
    try:
        if "banner_src" not in _cache:       # se reduce una vez: redimensionar la foto original en cada resize sería lento
            fuente = Image.open(RUTA_BANNER).convert("RGB")
            if fuente.width > 1200:
                fuente = fuente.resize((1200, round(fuente.height * 1200 / fuente.width)), Image.LANCZOS)
            _cache["banner_src"] = fuente
        src = _cache["banner_src"]
        esc = max(ancho / src.width, alto / src.height)
        img = src.resize((max(ancho, round(src.width * esc)), max(alto, round(src.height * esc))), Image.LANCZOS)
        x, y = (img.width - ancho) // 2, (img.height - alto) // 2
        img = img.crop((x, y, x + ancho, y + alto)).convert("RGBA")
        sup = 3                                # máscara sobremuestreada: bordes redondeados sin dientes de sierra
        mascara = Image.new("L", (ancho * sup, alto * sup), 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, ancho * sup - 1, alto * sup - 1), radio * sup, fill=255)
        img.putalpha(mascara.resize((ancho, alto), Image.LANCZOS))
        filo = Image.new("RGBA", (ancho * sup, alto * sup), (0, 0, 0, 0))
        ImageDraw.Draw(filo).rounded_rectangle((0, 0, ancho * sup - 1, alto * sup - 1), radio * sup,
                                               outline=(255, 255, 255, 70), width=sup)
        img.alpha_composite(filo.resize((ancho, alto), Image.LANCZOS))
    except Exception:
        img = None
    if len(_cache) > 40:
        _cache.clear()
    _cache[clave] = img
    return img
