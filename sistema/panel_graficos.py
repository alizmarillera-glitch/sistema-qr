"""Dibujo (solo Pillow) de las piezas gráficas del panel «Resumen general»: tarjetas de indicadores con curva,
gráfico de líneas de ventas y dona del estado del inventario.

Todas las funciones reciben el tamaño en píxeles reales, el factor de escala de pantalla ``esc`` (1.0 = 96 ppp) y un
diccionario de colores ``col`` (hex) del modo vigente: bg, surface, borde, text, muted. Devuelven una imagen RGB lista
para mostrarse en un tk.Canvas.
"""
import math
from PIL import Image, ImageDraw, ImageFilter

import iconos
from login_visual import _fuente

AZUL, TURQUESA, AMBAR, ROJO, GRIS = "#3B82FF", "#19C7A5", "#FBBF24", "#F0505F", "#8EA0C0"


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mezcla(a, b, t):
    a, b = rgb(a), rgb(b)
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _degradado_v(w, h, c1, c2, a1=255, a2=255):
    """RGBA vertical de c1 (arriba) a c2 (abajo)."""
    m = Image.linear_gradient("L").resize((w, h))
    a = Image.new("RGBA", (w, h), tuple(c1) + (a1,))
    b = Image.new("RGBA", (w, h), tuple(c2) + (a2,))
    return Image.composite(b, a, m)


def _mascara_redonda(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    return m


# ---------------------------------------------------------------------------------------- tarjeta de indicador
def tarjeta_kpi(w, h, esc, col, acento, onda, titulo, valor, nota, nota_color, icono, fase=0.0):
    """Tarjeta de cristal con sello de icono, título, cifra, nota y una curva suave en la parte baja."""
    ss = 2
    W, H = w * ss, h * ss
    r = int(20 * esc * ss)
    cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # fondo: degradado con un toque del color del indicador
    sup = rgb(col["surface"])
    fondo = _degradado_v(W, H, mezcla(col["surface"], acento, 0.10), sup)
    cap.paste(fondo, (0, 0), _mascara_redonda(W, H, r))
    # curva y relleno bajo la curva
    pts = []
    for i in range(W + 1):
        x = i / W
        s = x * x * (3 - 2 * x)
        y = H * (0.80 - 0.24 * s) + H * 0.045 * math.sin(x * 2 * math.pi * 1.3 + fase)
        pts.append((i, y))
    relleno = Image.new("L", (W, H), 0)
    ImageDraw.Draw(relleno).polygon(pts + [(W, H), (0, H)], fill=255)
    tinte = _degradado_v(W, H, rgb(onda), rgb(onda), 70, 0)
    tinte.putalpha(ImageChops_multiplicar(tinte.getchannel("A"), relleno))
    cap = Image.alpha_composite(cap, _recortar(tinte, _mascara_redonda(W, H, r)))
    linea = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(linea).line(pts, fill=rgb(onda) + (220,), width=max(2, int(2.4 * esc * ss)), joint="curve")
    cap = Image.alpha_composite(cap, _recortar(linea, _mascara_redonda(W, H, r)))
    # borde teñido
    borde = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(borde).rounded_rectangle((0, 0, W - 1, H - 1), r, outline=mezcla(col["borde"], acento, 0.45) + (255,),
                                             width=max(2, int(1.6 * esc * ss)))
    cap = Image.alpha_composite(cap, borde)
    # sello del icono
    lado = int(60 * esc * ss)
    x0, y0 = int(12 * esc * ss), int(16 * esc * ss)
    sello = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(sello)
    d.rounded_rectangle((x0, y0, x0 + lado, y0 + lado), int(16 * esc * ss), fill=mezcla(col["surface"], acento, 0.20) + (255,),
                        outline=mezcla(col["surface"], acento, 0.45) + (255,), width=max(1, int(1.4 * esc * ss)))
    cap = Image.alpha_composite(cap, sello)
    tam_i = int(34 * esc * ss)
    try:
        ico = iconos.pil(icono, tam_i // iconos.ESCALA if hasattr(iconos, "ESCALA") else tam_i, acento).resize((tam_i, tam_i), Image.LANCZOS)
        cap.alpha_composite(ico, (x0 + (lado - tam_i) // 2, y0 + (lado - tam_i) // 2))
    except Exception:
        pass
    img = cap.resize((w, h), Image.LANCZOS)
    base = Image.new("RGB", (w, h), rgb(col["bg"]))
    base.paste(img, (0, 0), img)
    d = ImageDraw.Draw(base)
    tx = int((12 + 60 + 14) * esc)
    d.text((tx, int(30 * esc)), titulo, font=_fuente("n", 15.5 * esc), fill=rgb(col["text"]), anchor="lm")
    d.text((tx, int(70 * esc)), str(valor), font=_fuente("b", 38 * esc), fill=rgb(col["text"]), anchor="lm")
    d.text((tx, int(111 * esc)), nota, font=_fuente("b", 14 * esc), fill=rgb(nota_color), anchor="lm")
    return base


def tarjeta_existencia(w, h, esc, col, acento, titulo, valor, nota, icono, dual=None):
    """Tarjeta de cristal para «Existencias»: degradado teñido, borde del color del indicador, sello de icono,
    título, cifra y nota (sin curva)."""
    ss = 2
    W, H = w * ss, h * ss
    r = int(18 * esc * ss)
    cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cap.paste(_degradado_v(W, H, mezcla(col["surface"], acento, 0.16), mezcla(col["surface"], acento, 0.04)), (0, 0),
              _mascara_redonda(W, H, r))
    borde = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(borde).rounded_rectangle((0, 0, W - 1, H - 1), r, outline=mezcla(col["borde"], acento, 0.75) + (255,),
                                             width=max(2, int(1.6 * esc * ss)))
    cap = Image.alpha_composite(cap, borde)
    lado = int(62 * esc * ss)
    x0, y0 = int(16 * esc * ss), (H - lado) // 2
    d = ImageDraw.Draw(cap)
    d.rounded_rectangle((x0, y0, x0 + lado, y0 + lado), int(16 * esc * ss), fill=mezcla(col["surface"], acento, 0.16) + (255,),
                        outline=mezcla(col["surface"], acento, 0.40) + (255,), width=max(1, int(1.4 * esc * ss)))
    tam_i = int(38 * esc * ss)
    try:
        ico = iconos.pil(icono, tam_i // iconos.ESCALA, acento).resize((tam_i, tam_i), Image.LANCZOS)
        cap.alpha_composite(ico, (x0 + (lado - tam_i) // 2, y0 + (lado - tam_i) // 2))
    except Exception:
        pass
    img = cap.resize((w, h), Image.LANCZOS)
    base = Image.new("RGB", (w, h), rgb(col["bg"]))
    base.paste(img, (0, 0), img)
    d = ImageDraw.Draw(base)
    tx = int((16 + 62 + 16) * esc)
    d.text((tx, int(h * 0.26)), titulo, font=_fuente("n", 15 * esc), fill=rgb(col["text"]), anchor="lm")
    if dual:
        # Dos cifras separadas, cada una con su propio rótulo: ((rótulo, valor, color), (rótulo, valor, color)).
        ancho_col = (w - tx - int(12 * esc)) / 2
        for i, (rotulo, cifra, color) in enumerate(dual):
            x = int(tx + i * ancho_col)
            d.text((x, int(h * 0.54)), str(cifra), font=_fuente("b", 30 * esc), fill=rgb(color or col["text"]), anchor="lm")
            d.text((x, int(h * 0.81)), rotulo, font=_fuente("n", 13.5 * esc), fill=rgb(col["muted"]), anchor="lm")
        xs = int(tx + ancho_col - 10 * esc)
        d.line((xs, int(h * 0.42), xs, int(h * 0.90)), fill=rgb(col["borde"]), width=max(1, int(esc)))
        return base
    d.text((tx, int(h * 0.54)), str(valor), font=_fuente("b", 34 * esc), fill=rgb(col["text"]), anchor="lm")
    d.text((tx, int(h * 0.81)), nota, font=_fuente("n", 13.5 * esc), fill=rgb(col["muted"]), anchor="lm")
    return base


def ImageChops_multiplicar(a, b):
    from PIL import ImageChops
    return ImageChops.multiply(a, b)


def _recortar(img, mascara):
    img = img.copy()
    from PIL import ImageChops
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mascara))
    return img


# ---------------------------------------------------------------------------------------- gráfico de líneas
def _escala(vmax):
    if vmax <= 0:
        return 10, 4
    crudo = vmax / 4.0
    mag = 10 ** math.floor(math.log10(crudo))
    for m in (1, 2, 2.5, 5, 10):
        if crudo <= m * mag:
            paso = m * mag
            break
    n = max(1, math.ceil(vmax / paso - 1e-9))
    return paso, n


def _fmt(v):
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def grafico_lineas(w, h, esc, col, valores, etiquetas, cada=1):
    """Línea con área degradada, cuadrícula y puntos luminosos. ``cada``: se rotula una de cada ``cada`` fechas."""
    ss = 2
    base = Image.new("RGB", (w, h), rgb(col["surface"]))
    izq, der, sup, inf = int(50 * esc), int(24 * esc), int(14 * esc), int(34 * esc)
    x0, x1, y0, y1 = izq, w - der, sup, h - inf
    paso, n = _escala(max(valores) if valores else 0)
    tope = paso * n
    f = _fuente("n", 13.5 * esc)
    d = ImageDraw.Draw(base)
    c_grid = mezcla(col["surface"], col["text"], 0.10)
    c_eje = mezcla(col["surface"], col["text"], 0.22)
    c_txt = rgb(col["muted"]) if not col.get("dark") else mezcla(col["muted"], "#FFFFFF", 0.35)
    for i in range(n + 1):
        y = y1 - (y1 - y0) * i / n
        d.line((x0, y, x1, y), fill=c_eje if i == 0 else c_grid, width=1)
        d.text((x0 - 12 * esc, y), _fmt(paso * i), font=f, fill=c_txt, anchor="rm")
    k = len(valores)
    xs = [x0 + (x1 - x0) * i / max(1, k - 1) for i in range(k)] if k > 1 else [(x0 + x1) / 2]
    for i, x in enumerate(xs):
        d.line((x, y0, x, y1), fill=c_grid, width=1)
        if i % cada == 0 or i == k - 1:
            d.text((x, y1 + 8 * esc), etiquetas[i], font=f, fill=c_txt, anchor="mt")
    d.line((x0, y0, x0, y1), fill=c_eje, width=1)
    if not valores:
        return base
    ys = [y1 - (y1 - y0) * (v / tope if tope else 0) for v in valores]
    azul = rgb(AZUL)
    # área bajo la línea
    W, H = w * ss, h * ss
    pol = [(x * ss, y * ss) for x, y in zip(xs, ys)]
    area = Image.new("L", (W, H), 0)
    ImageDraw.Draw(area).polygon(pol + [(xs[-1] * ss, y1 * ss), (xs[0] * ss, y1 * ss)], fill=255)
    tinte = _degradado_v(W, H, azul, azul, 120, 10)
    from PIL import ImageChops
    tinte.putalpha(ImageChops.multiply(tinte.getchannel("A"), area))
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    capa = Image.alpha_composite(capa, tinte)
    dl = ImageDraw.Draw(capa)
    dl.line(pol, fill=azul + (255,), width=max(2, int(3.2 * esc * ss)), joint="curve")
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dh = ImageDraw.Draw(halo)
    for x, y in pol:
        rr = 11 * esc * ss
        dh.ellipse((x - rr, y - rr, x + rr, y + rr), fill=azul + (90,))
    halo = halo.filter(ImageFilter.GaussianBlur(3 * esc * ss))
    capa = Image.alpha_composite(capa, halo)
    dl = ImageDraw.Draw(capa)
    for x, y in pol:
        rr = 5.5 * esc * ss
        dl.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(90, 160, 255, 255), outline=(200, 225, 255, 255), width=max(1, int(esc * ss)))
    capa = capa.resize((w, h), Image.LANCZOS)
    base.paste(capa, (0, 0), capa)
    return base


# ---------------------------------------------------------------------------------------- dona
def dona(lado, esc, col, partes):
    """Anillo de porcentajes. ``partes``: lista de (cantidad, color hex). Sin datos: anillo gris."""
    ss = 3
    S = lado * ss
    cap = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(cap)
    grosor = int(S * 0.15)
    caja = (grosor // 2 + 2, grosor // 2 + 2, S - grosor // 2 - 2, S - grosor // 2 - 2)
    total = sum(max(0, v) for v, _c in partes)
    if total <= 0:
        d.arc(caja, 0, 360, fill=mezcla(col["surface"], col["text"], 0.18) + (255,), width=grosor)
    else:
        ang = -90.0
        for v, c in partes:
            if v <= 0:
                continue
            fin = ang + 360.0 * v / total
            d.arc(caja, ang, fin, fill=rgb(c) + (255,), width=grosor)
            ang = fin
    cap = cap.resize((lado, lado), Image.LANCZOS)
    base = Image.new("RGB", (lado, lado), rgb(col["surface"]))
    base.paste(cap, (0, 0), cap)
    return base
