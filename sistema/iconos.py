# -*- coding: utf-8 -*-
"""Iconografía de Sistema QR.

Los iconos siguen el estilo de **Lucide** (https://lucide.dev, licencia ISC): rejilla de 24 x 24, trazo
redondeado y sin relleno. Cada icono se guarda como los elementos SVG originales y este módulo los dibuja
con Pillow (sin dependencias nuevas), de modo que:

* todos comparten el mismo grosor de trazo en píxeles, sea cual sea su tamaño;
* cada icono se pinta en el color que pida la interfaz (activo, inactivo, tono de la tarjeta…);
* se entregan las variantes de modo claro y oscuro como ``CTkImage`` (nítidas también con escala de pantalla alta).

Para añadir o cambiar un icono basta con pegar en ``ICONOS`` el contenido interno del SVG de lucide.dev
(se admiten path, circle, ellipse, rect, line, polyline y polygon).

Uso:
    from iconos import icono
    boton.configure(image=icono("shopping-cart", 20, C["primary"]))
"""
import functools
import math
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

GROSOR_PX = 1.6       # grosor de trazo en píxeles lógicos (igual en todos los iconos)
ESCALA = 3            # resolución extra de la imagen entregada (nitidez con pantallas de alta densidad)
_SS = 4               # supersampling interno para suavizar los bordes

# --------------------------------------------------------------------------------------- geometría (Lucide)
ICONOS = {
    # ---- navegación
    "layout-dashboard": '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/>'
                        '<rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    # Pieza mecánica propia (en el estilo Lucide): corona con anillo, falda y orificio del bulón.
    "piston": '<path d="M4 2.5h16v5.5H4z"/><path d="M4 5.25h16"/><path d="M6.5 8v11a2.5 2.5 0 0 0 2.5 2.5h6a2.5 2.5 0 0 0 2.5-2.5V8"/>'
              '<circle cx="12" cy="14" r="2.2"/>',
    "boxes": '<path d="M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z"/>'
             '<path d="m7 16.5-4.74-2.85"/><path d="m7 16.5 5-3"/><path d="M7 16.5v5.17"/>'
             '<path d="M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z"/>'
             '<path d="m17 16.5-5-3"/><path d="m17 16.5 4.74-2.85"/><path d="M17 16.5v5.17"/>'
             '<path d="M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z"/>'
             '<path d="M12 8 7.26 5.15"/><path d="m12 8 4.74-2.85"/><path d="M12 13.5V8"/>',
    "arrow-left-right": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "shopping-cart": '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/>'
                     '<path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>',
    "receipt-text": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/>'
                    '<path d="M14 8H8"/><path d="M16 12H8"/><path d="M13 16H8"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "user-plus": '<path d="M2 21a8 8 0 0 1 13.292-6"/><circle cx="10" cy="8" r="5"/><path d="M19 16v6"/><path d="M22 19h-6"/>',
    "id-card": '<path d="M16 10h2"/><path d="M16 14h2"/><path d="M6.17 15a3 3 0 0 1 5.66 0"/><circle cx="9" cy="11" r="2"/>'
               '<rect x="2" y="5" width="20" height="14" rx="2"/>',
    "sliders-horizontal": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/>'
                          '<line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/>'
                          '<line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/>'
                          '<line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/>'
                          '<line x1="16" x2="16" y1="18" y2="22"/>',
    # ---- QR
    "qr-code": '<rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/>'
               '<rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/>'
               '<path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/>'
               '<path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/>',
    "scan-qr-code": '<path d="M17 12v4a1 1 0 0 1-1 1h-4"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M17 8V7"/>'
                    '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M7 17h.01"/>'
                    '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/><rect x="7" y="7" width="5" height="5" rx="1"/>',
    # ---- indicadores
    "tag": '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0'
           'l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5"/>',
    "package": '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/>'
               '<path d="M12 22V12"/><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"/><path d="m7.5 4.27 9 5.15"/>',
    "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
                      '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "ban": '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    # ---- acciones
    "refresh-cw": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
                  '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "minus": '<path d="M5 12h14"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/>'
               '<line x1="21" x2="9" y1="12" y2="12"/>',
    "eye": '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/>'
           '<circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/>'
               '<path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>'
               '<path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/>'
               '<path d="m2 2 20 20"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.34-4.34"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "circle-help": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    # ---- panel (resumen general)
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "circle-dollar-sign": '<circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 18V6"/>',
    "trophy": '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/>'
              '<path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/>'
              '<path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
    "zap": '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    "chart-column": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "circle-plus": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/>',
    "circle-x": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    # ---- producción y existencias
    "factory": '<path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/>'
               '<path d="M17 18h1"/><path d="M12 18h1"/><path d="M7 18h1"/>',
    "clipboard-list": '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
                      '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
                      '<path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
                 '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "list": '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/>'
            '<path d="M8 6h13"/>',
}

# --------------------------------------------------------------------------------------- lector de trazados SVG
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _arco(x1, y1, rx, ry, rot, gran, barrido, x2, y2):
    """Convierte un arco SVG (notación de extremos) en una lista de puntos (sin el inicial)."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    fi = math.radians(rot % 360)
    c, s = math.cos(fi), math.sin(fi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = c * dx + s * dy, -s * dx + c * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        k = math.sqrt(lam)
        rx, ry = rx * k, ry * k
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if gran == barrido:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = c * cxp - s * cyp + (x1 + x2) / 2, s * cxp + c * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not barrido and dt > 0:
        dt -= 2 * math.pi
    elif barrido and dt < 0:
        dt += 2 * math.pi
    pasos = max(6, math.ceil(abs(dt) / (math.pi / 20)))
    pts = []
    for i in range(1, pasos + 1):
        t = t1 + dt * i / pasos
        pts.append((c * rx * math.cos(t) - s * ry * math.sin(t) + cx,
                    s * rx * math.cos(t) + c * ry * math.sin(t) + cy))
    pts[-1] = (x2, y2)
    return pts


def _bezier(p0, p1, p2, p3, pasos=20):
    pts = []
    for i in range(1, pasos + 1):
        t = i / pasos
        u = 1 - t
        pts.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return pts


def _cuadratica(p0, p1, p2, pasos=16):
    return _bezier(p0, ((p0[0] + 2 * p1[0]) / 3, (p0[1] + 2 * p1[1]) / 3),
                   ((p2[0] + 2 * p1[0]) / 3, (p2[1] + 2 * p1[1]) / 3), p2, pasos)


def _trazado(d):
    """Atributo ``d`` de un <path> -> lista de subtrazados [(puntos, cerrado)]."""
    i, n = 0, len(d)
    subs, pts, cerrado = [], [], False
    x = y = ix = iy = 0.0
    cmd = None
    ult_c = ult_q = None          # último punto de control (para S y T)

    def cierra():
        nonlocal pts, cerrado
        if pts:
            subs.append((pts, cerrado))
        pts, cerrado = [], False

    def saltar():
        nonlocal i
        while i < n and d[i] in " ,\t\r\n":
            i += 1

    def numero():
        nonlocal i
        saltar()
        m = _NUM.match(d, i)
        if not m:
            raise ValueError(f"trazado SVG no válido cerca de «{d[i:i + 12]}»")
        i = m.end()
        return float(m.group())

    def bandera():                # las banderas de los arcos pueden venir pegadas: «a1 1 0 011 1»
        nonlocal i
        saltar()
        v = d[i]
        i += 1
        return v == "1"

    while True:
        saltar()
        if i >= n:
            break
        if d[i].isalpha():
            cmd = d[i]
            i += 1
            if cmd in "Zz":
                if pts:
                    cerrado = True
                    x, y = ix, iy
                    cierra()
                    pts = [(x, y)]            # un nuevo subtrazado parte del punto inicial
                ult_c = ult_q = None
                continue
        elif cmd is None:
            raise ValueError("el trazado SVG debe empezar con una orden")
        rel = cmd.islower()
        c = cmd.upper()
        a = [None] * _ARGS[c]
        for k in range(len(a)):
            a[k] = bandera() if (c == "A" and k in (3, 4)) else numero()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "M":
            cierra()
            x, y = a[0] + ox, a[1] + oy
            ix, iy = x, y
            pts = [(x, y)]
            cmd = "l" if rel else "L"             # los pares siguientes son líneas
            ult_c = ult_q = None
        elif c == "L":
            x, y = a[0] + ox, a[1] + oy
            pts.append((x, y)); ult_c = ult_q = None
        elif c == "H":
            x = a[0] + ox
            pts.append((x, y)); ult_c = ult_q = None
        elif c == "V":
            y = a[0] + oy
            pts.append((x, y)); ult_c = ult_q = None
        elif c == "C":
            p1, p2, p3 = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy), (a[4] + ox, a[5] + oy)
            pts += _bezier((x, y), p1, p2, p3)
            ult_c, ult_q = p2, None
            x, y = p3
        elif c == "S":
            p1 = (2 * x - ult_c[0], 2 * y - ult_c[1]) if ult_c else (x, y)
            p2, p3 = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            pts += _bezier((x, y), p1, p2, p3)
            ult_c, ult_q = p2, None
            x, y = p3
        elif c == "Q":
            p1, p2 = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            pts += _cuadratica((x, y), p1, p2)
            ult_q, ult_c = p1, None
            x, y = p2
        elif c == "T":
            p1 = (2 * x - ult_q[0], 2 * y - ult_q[1]) if ult_q else (x, y)
            p2 = (a[0] + ox, a[1] + oy)
            pts += _cuadratica((x, y), p1, p2)
            ult_q, ult_c = p1, None
            x, y = p2
        elif c == "A":
            ex, ey = a[5] + ox, a[6] + oy
            pts += _arco(x, y, a[0], a[1], a[2], a[3], a[4], ex, ey)
            x, y = ex, ey
            ult_c = ult_q = None
    cierra()
    return [s for s in subs if len(s[0]) >= 2]


def _elipse(cx, cy, rx, ry, pasos=72):
    return [(cx + rx * math.cos(2 * math.pi * k / pasos), cy + ry * math.sin(2 * math.pi * k / pasos))
            for k in range(pasos)]


def _rect(x, y, w, h, rx=0.0, ry=None):
    ry = rx if ry is None else ry
    rx, ry = min(rx, w / 2), min(ry, h / 2)
    if rx <= 0 or ry <= 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts = []
    for (cx, cy, a0) in ((x + w - rx, y + ry, -90), (x + w - rx, y + h - ry, 0),
                         (x + rx, y + h - ry, 90), (x + rx, y + ry, 180)):
        for k in range(0, 11):
            t = math.radians(a0 + 9 * k)
            pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def _flt(el, nombre, defecto=0.0):
    v = el.get(nombre)
    return float(v) if v not in (None, "") else defecto


def _formas(cuerpo):
    """Contenido SVG -> lista de (puntos, cerrado)."""
    raiz = ET.fromstring(f"<g>{cuerpo}</g>")
    formas = []
    for el in raiz.iter():
        etq = el.tag.split("}")[-1]
        if etq == "path":
            formas += _trazado(el.get("d", ""))
        elif etq == "circle":
            r = _flt(el, "r")
            formas.append((_elipse(_flt(el, "cx"), _flt(el, "cy"), r, r), True))
        elif etq == "ellipse":
            formas.append((_elipse(_flt(el, "cx"), _flt(el, "cy"), _flt(el, "rx"), _flt(el, "ry")), True))
        elif etq == "rect":
            rx = _flt(el, "rx") if el.get("rx") else _flt(el, "ry")
            ry = _flt(el, "ry") if el.get("ry") else rx
            formas.append((_rect(_flt(el, "x"), _flt(el, "y"), _flt(el, "width"), _flt(el, "height"), rx, ry), True))
        elif etq == "line":
            formas.append(([(_flt(el, "x1"), _flt(el, "y1")), (_flt(el, "x2"), _flt(el, "y2"))], False))
        elif etq in ("polyline", "polygon"):
            v = [float(t) for t in _NUM.findall(el.get("points", ""))]
            formas.append((list(zip(v[0::2], v[1::2])), etq == "polygon"))
    return formas


# --------------------------------------------------------------------------------------- dibujo
def _rgb(color):
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[k:k + 2], 16) for k in (0, 2, 4))


@functools.lru_cache(maxsize=512)
def _pintar(nombre, tam, color, grosor):
    """Imagen RGBA (tam*ESCALA px) del icono ``nombre`` en ``color`` (#RRGGBB)."""
    if nombre not in ICONOS:
        raise KeyError(f"icono desconocido: {nombre}")
    final = tam * ESCALA
    W = final * _SS
    u = W / 24.0
    ancho = max(1, round(grosor * ESCALA * _SS))
    r = ancho / 2.0
    mascara = Image.new("L", (W, W), 0)
    dib = ImageDraw.Draw(mascara)
    for pts, cerrado in _formas(ICONOS[nombre]):
        p = [(a * u, b * u) for a, b in pts]
        if len(p) > 1:
            seg = p + [p[0]] if cerrado else p
            dib.line(seg, fill=255, width=ancho)
        for a, b in p:                               # uniones y extremos redondeados
            dib.ellipse((a - r, b - r, a + r, b + r), fill=255)
    mascara = mascara.resize((final, final), Image.LANCZOS)
    img = Image.new("RGBA", (final, final), _rgb(color) + (0,))
    img.putalpha(mascara)
    return img


def pil(nombre, tam=20, color="#000000", grosor=GROSOR_PX):
    """Imagen PIL (RGBA) del icono, ``tam*ESCALA`` píxeles de lado."""
    return _pintar(nombre, int(tam), color, float(grosor))


def icono(nombre, tam=20, color="#000000", grosor=GROSOR_PX):
    """``CTkImage`` del icono. ``color`` puede ser «#RRGGBB» o la tupla (claro, oscuro) de la paleta.

    Si algo falla (icono desconocido, Pillow, etc.) devuelve None: el widget simplemente se muestra sin icono.
    """
    try:
        import customtkinter as ctk
        claro, oscuro = (color if isinstance(color, (tuple, list)) else (color, color))
        return ctk.CTkImage(light_image=pil(nombre, tam, claro, grosor),
                            dark_image=pil(nombre, tam, oscuro, grosor), size=(tam, tam))
    except Exception:
        return None


def foto_tk(nombre, tam=20, color="#000000", grosor=GROSOR_PX):
    """``ImageTk.PhotoImage`` para usar en un Canvas de tkinter (pantalla de acceso). None si falla."""
    try:
        from PIL import ImageTk
        img = pil(nombre, tam, color, grosor).resize((tam, tam), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None
