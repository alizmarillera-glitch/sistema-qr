"""Pantalla de acceso con el diseño exacto de ``recursos/login_fondo.png``.

Idea: la imagen de diseño (1672x941) se usa como fondo. Lo decorativo (fondo, panel de cristal, título, iconos,
etiquetas, separadores y lema) se conserva tal cual. Lo interactivo (campos, botón «Mostrar», botón «Ingresar» e
interruptor de modo oscuro) se borra de esa copia y se sustituye por controles reales dibujados con el mismo estilo.

Todo se escala con la ventana (ver ``Diseno.geometria``): el panel queda siempre anclado a la derecha.
La pantalla de acceso se ve siempre en oscuro, como el diseño; el interruptor solo guarda el modo del programa.
Las partes de dibujo (clase ``Diseno``) no dependen de tkinter: se pueden probar solo con Pillow.
"""
import os
import tkinter as tk
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import iconos

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_FONDO = os.path.join(BASE, "recursos", "login_fondo.png")
REF_W, REF_H = 1672, 941          # tamaño de la imagen de diseño: todas las medidas están en estos píxeles
BG = "#050b14"

# Rectángulos (x0, y0, x1, y1) en píxeles de la imagen de diseño.
RECT = {
    "campo_u": (1093, 355, 1608, 420),
    "campo_p": (1093, 505, 1440, 568),
    "ver":     (1459, 505, 1608, 568),
    "ing":     (1093, 617, 1608, 695),
    "sw":      (1094, 731, 1153, 763),
}
# Cuánto se amplía cada rectángulo al borrarlo de la imagen (incluye el brillo que rodea al botón).
BORRAR = {"campo_u": 7, "campo_p": 7, "ver": 7, "ing": 18, "sw": 6}
ERR_CENTRO_Y = 593.5              # el aviso de error ocupa el hueco entre la contraseña y el botón
ERR_X0, ERR_X1 = 1093, 1608

TXT = (232, 238, 247)
MARCADOR = (138, 152, 172)


# ------------------------------------------------------------------ dibujo (solo Pillow)
def _fuente(estilo, px):
    nombres = {"n": ("segoeui.ttf", "SegoeUI.ttf", "Inter-Regular.ttf", "NotoSans-Regular.ttf", "DejaVuSans.ttf"),
               "b": ("segoeuib.ttf", "seguisb.ttf", "Inter-Bold.ttf", "NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf")}[estilo]
    for n in nombres:
        try:
            return ImageFont.truetype(n, max(6, int(round(px))))
        except Exception:
            continue
    try:
        return ImageFont.load_default(max(6, int(round(px))))
    except Exception:
        return ImageFont.load_default()


def _gradiente_v(w, h, top, bot):
    col = Image.new("RGBA", (1, max(1, h)))
    for y in range(max(1, h)):
        t = y / max(1, h - 1)
        col.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
    return col.resize((w, h), Image.NEAREST)


def _caja(w, h, radio, top, bot, borde, bw, glow=None, glow_r=0, pad=0):
    """Rectángulo redondeado con degradado, borde fino y (opcional) resplandor. Devuelve RGBA de (w+2pad, h+2pad)."""
    ss = 3
    W, H = (w + 2 * pad) * ss, (h + 2 * pad) * ss
    caja = (pad * ss, pad * ss, (pad + w) * ss - 1, (pad + h) * ss - 1)
    lienzo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if glow:
        g = Image.new("RGBA", (W, H), tuple(glow[:3]) + (0,))
        ImageDraw.Draw(g).rounded_rectangle(caja, radio * ss, fill=tuple(glow))
        lienzo = Image.alpha_composite(lienzo, g.filter(ImageFilter.GaussianBlur(max(0.1, glow_r * ss))))
    mascara = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(caja, radio * ss, fill=255)
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    capa.paste(_gradiente_v(w * ss, h * ss, top, bot), (pad * ss, pad * ss))
    capa.putalpha(mascara)
    lienzo = Image.alpha_composite(lienzo, capa)
    b = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(b).rounded_rectangle(caja, radio * ss, outline=tuple(borde), width=max(1, int(round(bw * ss))))
    lienzo = Image.alpha_composite(lienzo, b)
    return lienzo.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS)


def _icono_entrar(px, color):
    """Icono «iniciar sesión» (flecha entrando a un corchete), trazo redondeado como los de iconos.py."""
    ss = 6
    S = px * ss
    u = S / 24.0
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    gr = max(1, int(round(2 * u * 1.15)))

    def linea(pts):
        pts = [(x * u, y * u) for x, y in pts]
        d.line(pts, fill=color, width=gr, joint="curve")
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - gr / 2, y - gr / 2, x + gr / 2, y + gr / 2), fill=color)

    linea([(15, 3), (19, 3), (21, 5), (21, 19), (19, 21), (15, 21)])
    linea([(10, 17), (15, 12), (10, 7)])
    linea([(15, 12), (3, 12)])
    return img.resize((px, px), Image.LANCZOS)


def _icono(nombre, px, color):
    try:
        return iconos.pil(nombre, px, color).resize((px, px), Image.LANCZOS)
    except Exception:
        return None


def _contenido(img, pad, w, h, partes, color, gap):
    """Dibuja icono y/o texto centrados en el cuerpo (w x h) de un sprite que tiene ``pad`` de margen."""
    d = ImageDraw.Draw(img)
    medidas = []
    for p in partes:
        if p[0] == "icono":
            medidas.append(p[1].width)
        else:
            medidas.append(d.textlength(p[1], font=p[2]))
    total = sum(medidas) + gap * (len(partes) - 1)
    x = pad + (w - total) / 2
    cy = pad + h / 2
    for p, m in zip(partes, medidas):
        if p[0] == "icono":
            img.alpha_composite(p[1], (int(round(x)), int(round(cy - p[1].height / 2))))
        else:
            d.text((x, cy), p[1], font=p[2], fill=color, anchor="lm")
        x += m + gap


def _partir(texto, fuente, ancho_max):
    medir = ImageDraw.Draw(Image.new("L", (4, 4))).textlength
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = (actual + " " + palabra).strip()
        if actual and medir(prueba, font=fuente) > ancho_max:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    return lineas or [""]


class Diseno:
    """Calcula geometría y dibuja el fondo y los controles (con caché). No usa tkinter."""

    def __init__(self):
        self._orig = None
        self._limpia = None
        self._cache = {}

    # ---- fondo
    def _cargar(self):
        if self._limpia is not None:
            return
        src = Image.open(RUTA_FONDO).convert("RGB")
        if src.size != (REF_W, REF_H):
            src = src.resize((REF_W, REF_H), Image.LANCZOS)
        orig = src.copy()
        for nombre, infl in BORRAR.items():
            x0, y0, x1, y1 = RECT[nombre]
            x0, y0, x1, y1 = x0 - infl, y0 - infl, x1 + infl, y1 + infl
            # Se rellena con el color del margen limpio del panel (a la izquierda de los campos), fila por fila.
            f = 6                                   # el parche se funde con la imagen en sus bordes (sin rectángulos visibles)
            ya, yb = y0 - f, y1 + f
            col = orig.crop((1050, ya, 1074, yb)).resize((1, yb - ya), Image.BOX)
            parche = col.resize((x1 - x0 + 2 * f, yb - ya), Image.NEAREST)
            mascara = Image.new("L", parche.size, 0)
            ImageDraw.Draw(mascara).rectangle((f, f, f + x1 - x0 - 1, f + y1 - y0 - 1), fill=255)
            src.paste(parche, (x0 - f, ya), mascara.filter(ImageFilter.GaussianBlur(f / 2)))
        self._orig, self._limpia = orig, src

    def geometria(self, W, H):
        """(escala, desplazamiento x, desplazamiento y): la imagen cubre la ventana y queda anclada a la derecha."""
        s = max(W / REF_W, H / REF_H)
        return s, W - REF_W * s, (H - REF_H * s) / 2

    def fondo(self, W, H, limpio=True):
        self._cargar()
        s, ox, oy = self.geometria(W, H)
        tam = (max(1, round(REF_W * s)), max(1, round(REF_H * s)))
        img = (self._limpia if limpio else self._orig).resize(tam, Image.LANCZOS)
        x, y = tam[0] - W, int(round((tam[1] - H) / 2))        # anclada a la derecha, centrada en vertical
        return img.crop((x, y, x + W, y + H))

    def rect(self, nombre, W, H):
        s, ox, oy = self.geometria(W, H)
        x0, y0, x1, y1 = RECT[nombre]
        a, b = round(ox + x0 * s), round(oy + y0 * s)
        return a, b, round(ox + x1 * s) - a, round(oy + y1 * s) - b      # x, y, ancho, alto

    # ---- sprites
    def sprite(self, nombre, estado, s, texto=None):
        """(imagen RGBA, margen). El margen es el borde extra que dejan los resplandores alrededor del rectángulo."""
        clave = (nombre, estado, round(s, 4), texto)
        if clave not in self._cache:
            if len(self._cache) > 60:
                self._cache.clear()
            self._cache[clave] = getattr(self, "_s_" + nombre.split("_")[0])(nombre, estado, s, texto)
        return self._cache[clave]

    def _tam(self, nombre, s):
        x0, y0, x1, y1 = RECT[nombre]
        return max(4, round((x1 - x0) * s)), max(4, round((y1 - y0) * s))

    def _s_campo(self, nombre, estado, s, texto):
        w, h = self._tam(nombre, s)
        pad = int(round(12 * s)) + 2
        if estado == "foco":
            img = _caja(w, h, round(19 * s), (19, 32, 48), (14, 25, 38), (82, 142, 235, 255), 2.0 * s,
                        glow=(40, 110, 255, 70), glow_r=5 * s, pad=pad)
        else:
            img = _caja(w, h, round(19 * s), (18, 30, 45), (14, 24, 37), (66, 90, 122, 255), 1.6 * s, pad=pad)
        return img, pad

    def _s_ver(self, nombre, estado, s, texto):
        w, h = self._tam(nombre, s)
        pad = int(round(12 * s)) + 2
        top, bot, borde = {"normal": ((16, 26, 40), (12, 21, 33), (66, 90, 122, 255)),
                           "hover": ((21, 36, 56), (15, 28, 45), (100, 156, 236, 255)),
                           "press": ((10, 18, 28), (8, 14, 22), (70, 120, 200, 255))}[estado]
        img = _caja(w, h, round(19 * s), top, bot, borde, 1.6 * s, pad=pad)
        ico = _icono("eye-off" if texto == "Ocultar" else "eye", max(8, round(34 * s)), "#FFFFFF")
        partes = ([("icono", ico)] if ico else []) + [("texto", texto or "Mostrar", _fuente("b", 17 * s))]
        _contenido(img, pad, w, h, partes, (255, 255, 255, 255), round(9 * s))
        return img, pad

    def _s_ing(self, nombre, estado, s, texto):
        w, h = self._tam(nombre, s)
        pad = int(round(20 * s)) + 2
        top, bot, borde, glow, gr = {
            "normal": ((6, 94, 226), (0, 64, 164), (46, 132, 250, 255), (10, 90, 255, 95), 8),
            "hover":  ((20, 112, 244), (2, 78, 190), (96, 168, 255, 255), (20, 110, 255, 150), 10),
            "press":  ((0, 70, 176), (0, 52, 140), (40, 110, 220, 255), (10, 80, 220, 70), 6),
            "off":    ((24, 58, 108), (18, 44, 86), (50, 84, 140, 255), None, 0)}[estado]
        img = _caja(w, h, round(22 * s), top, bot, borde, 1.8 * s, glow=glow, glow_r=gr * s, pad=pad)
        ico = _icono_entrar(max(8, round(34 * s)), (255, 255, 255, 255 if estado != "off" else 140))
        _contenido(img, pad, w, h, [("icono", ico), ("texto", texto or "Ingresar", _fuente("b", 25 * s))],
                   (255, 255, 255, 255 if estado != "off" else 150), round(26 * s))
        return img, pad

    def _s_sw(self, nombre, estado, s, texto):
        w, h = self._tam(nombre, s)
        pad = int(round(7 * s)) + 2
        enc = estado == "on"
        if enc:
            img = _caja(w, h, h // 2, (8, 104, 240), (0, 78, 200), (30, 120, 255, 255), 1.0, glow=(10, 90, 255, 90),
                        glow_r=4 * s, pad=pad)
        else:
            img = _caja(w, h, h // 2, (44, 56, 74), (34, 45, 62), (70, 86, 110, 255), 1.0, pad=pad)
        d = int(round(h * 0.82))
        cx = pad + (w - (h - d) / 2 - d / 2 if enc else (h - d) / 2 + d / 2)
        cy = pad + h / 2
        ss = 4
        perilla = Image.new("RGBA", (d * ss + 8 * ss, d * ss + 8 * ss), (0, 0, 0, 0))
        dd = ImageDraw.Draw(perilla)
        dd.ellipse((4 * ss, 5 * ss, 4 * ss + d * ss, 5 * ss + d * ss), fill=(0, 0, 0, 90))
        perilla = perilla.filter(ImageFilter.GaussianBlur(1.5 * ss))
        dd = ImageDraw.Draw(perilla)
        dd.ellipse((4 * ss, 4 * ss, 4 * ss + d * ss, 4 * ss + d * ss), fill=(231, 236, 241, 255))
        perilla = perilla.resize((d + 8, d + 8), Image.LANCZOS)
        img.alpha_composite(perilla, (int(round(cx - d / 2 - 4)), int(round(cy - d / 2 - 4))))
        return img, pad

    def sprite_error(self, texto, tono, s):
        """Aviso bajo la contraseña. Devuelve (imagen, margen, alto del cuerpo en píxeles de pantalla)."""
        clave = ("err", texto, tono, round(s, 4))
        if clave in self._cache:
            return self._cache[clave]
        fuente = _fuente("n", 14.5 * s)
        w = round((ERR_X1 - ERR_X0) * s)
        ico_px = max(8, round(20 * s))
        lineas = _partir(texto, fuente, w - round(30 * s) - ico_px - round(10 * s))[:2]
        h = round((34 if len(lineas) == 1 else 44) * s)
        pad = 2
        fondo, borde, color = {"danger": ((58, 26, 34), (150, 60, 74, 255), (255, 135, 145)),
                               "warn": ((58, 45, 20), (160, 120, 40, 255), (243, 179, 79))}.get(
            tono, ((58, 26, 34), (150, 60, 74, 255), (255, 135, 145)))
        img = _caja(w, h, round(12 * s), fondo, fondo, borde, 1.2 * s, pad=pad)
        d = ImageDraw.Draw(img)
        ico = _icono("triangle-alert", ico_px, "#%02X%02X%02X" % color)
        if ico:
            img.alpha_composite(ico, (pad + round(14 * s), int(pad + h / 2 - ico_px / 2)))
        alto_l = fuente.size * 1.25
        y = pad + h / 2 - alto_l * (len(lineas) - 1) / 2
        for ln in lineas:
            d.text((pad + round(14 * s) + ico_px + round(10 * s), y), ln, font=fuente, fill=color + (255,), anchor="lm")
            y += alto_l
        self._cache[clave] = (img, pad, h)
        return self._cache[clave]


# ------------------------------------------------------------------ campo de texto con marcador
class _Entrada(tk.Entry):
    """tk.Entry con texto de ayuda («placeholder») que desaparece al escribir. ``get()`` devuelve '' si solo hay marcador."""

    def __init__(self, master, marcador, oculto=False, **kw):
        super().__init__(master, **kw)
        self._m, self._oculto, self._ver, self._vacio = marcador, oculto, False, False
        self._c_t, self._c_m = "#%02X%02X%02X" % TXT, "#%02X%02X%02X" % MARCADOR
        self.bind("<FocusIn>", lambda _e: self._al_enfocar(), add="+")
        self.bind("<FocusOut>", lambda _e: self._al_salir(), add="+")
        self.bind("<Key>", self._tecla, add="+")
        self.bind("<<Paste>>", lambda _e: self._quitar_marcador(), add="+")
        self.bind("<ButtonRelease-1>", lambda _e: self._al_cursor(), add="+")
        self._poner_marcador()

    def _show(self):
        return "•" if self._oculto and not self._ver else ""

    def _poner_marcador(self):
        self._vacio = True
        tk.Entry.delete(self, 0, "end")
        tk.Entry.insert(self, 0, self._m)
        tk.Entry.configure(self, fg=self._c_m, show="")
        self.icursor(0)

    def _quitar_marcador(self):
        if self._vacio:
            self._vacio = False
            tk.Entry.delete(self, 0, "end")
            tk.Entry.configure(self, fg=self._c_t, show=self._show())

    def _tecla(self, e):
        if not self._vacio:
            return None
        if e.keysym in ("BackSpace", "Delete"):
            return "break"
        if e.char and ord(e.char[0]) >= 32 and not (e.state & 0x4):
            self._quitar_marcador()
        return None

    def _al_cursor(self):
        if self._vacio:
            self.selection_clear()
            self.icursor(0)

    def _al_enfocar(self):
        if self._vacio:
            self.after_idle(self._al_cursor)

    def _al_salir(self):
        if not tk.Entry.get(self):
            self._poner_marcador()

    def get(self):
        return "" if self._vacio else tk.Entry.get(self)

    def delete(self, a, b=None):
        if self._vacio:
            return
        tk.Entry.delete(self, a, b)
        if not tk.Entry.get(self):
            try:
                enfocado = self.focus_get() is self
            except Exception:
                enfocado = False
            if not enfocado:
                self._poner_marcador()

    def ver(self, visible):
        self._ver = visible
        if not self._vacio:
            tk.Entry.configure(self, show=self._show())


# ------------------------------------------------------------------ ventana
def _crear_login():
    import customtkinter as ctk
    from PIL import ImageTk
    import conexion as db
    from estilos import modo_actual, guardar_modo
    from ui import centrar, messagebox, pantalla_completa

    class Login(ctk.CTk):
        """Acceso con el diseño de login_fondo.png (ver el texto del módulo)."""

        def __init__(self):
            super().__init__()
            self.title("Acceso · Manufacturas de Aluminio I, C.A.")
            self.configure(fg_color=BG)
            self.minsize(960, 540)
            self.usuario = None
            self._dis = Diseno()
            self._fotos = {}
            self._est = {"campo_u": "normal", "campo_p": "normal", "ver": "normal", "ing": "normal"}
            self._txt = {"ver": "Mostrar", "ing": "Ingresar"}
            self._oscuro = modo_actual() == "dark"
            self._clave_visible = False
            self._error_actual = None
            self._tarea = None
            self._dim = (0, 0)

            cv = self.cv = tk.Canvas(self, highlightthickness=0, bd=0, bg=BG)
            cv.pack(fill="both", expand=True)
            self._it = {"bg": cv.create_image(0, 0, anchor="nw")}
            for n in ("campo_u", "campo_p"):
                self._it[n] = cv.create_image(0, 0, anchor="nw")
            kw = dict(bd=0, highlightthickness=0, relief="flat", bg="#101b28", fg="#%02X%02X%02X" % TXT,
                      insertbackground="#FFFFFF", selectbackground="#1F4FA8", selectforeground="#FFFFFF")
            self.u = _Entrada(cv, "Nombre de usuario", **kw)
            self.p = _Entrada(cv, "Tu contraseña", oculto=True, **kw)
            self._it["e_u"] = cv.create_window(0, 0, window=self.u, anchor="w")
            self._it["e_p"] = cv.create_window(0, 0, window=self.p, anchor="w")
            for n in ("ver", "ing", "sw", "err"):
                self._it[n] = cv.create_image(0, 0, anchor="nw")
            cv.itemconfigure(self._it["err"], state="hidden")

            self.u.bind("<FocusIn>", lambda _e: self._foco("campo_u", True), add="+")
            self.u.bind("<FocusOut>", lambda _e: self._foco("campo_u", False), add="+")
            self.p.bind("<FocusIn>", lambda _e: self._foco("campo_p", True), add="+")
            self.p.bind("<FocusOut>", lambda _e: self._foco("campo_p", False), add="+")
            for n, cmd in (("ver", self._alternar_clave), ("ing", self.entrar), ("sw", self._cambiar_modo)):
                self._enlazar(n, cmd)
            cv.bind("<Configure>", self._al_cambiar_tamano)
            self.bind("<Return>", lambda _e: self.entrar())
            centrar(self, 1280, 720)
            pantalla_completa(self)
            self.update_idletasks()
            self._disponer()
            self.u.focus_set()

        # ---- botones del lienzo (hover / pulsado / clic)
        def _enlazar(self, n, cmd):
            it = self._it[n]
            self.cv.tag_bind(it, "<Enter>", lambda _e: self._hover(n, True))
            self.cv.tag_bind(it, "<Leave>", lambda _e: self._hover(n, False))
            self.cv.tag_bind(it, "<ButtonPress-1>", lambda _e: self._presionar(n, True))
            self.cv.tag_bind(it, "<ButtonRelease-1>", lambda _e: self._soltar(n, cmd))

        def _activo(self, n):
            return not (n == "ing" and self._est["ing"] == "off")

        def _hover(self, n, dentro):
            if not self._activo(n):
                return
            self.cv.configure(cursor="hand2" if dentro else "")
            self._est[n] = "hover" if dentro else "normal"
            self._pintar(n)

        def _presionar(self, n, _x):
            if self._activo(n):
                self._est[n] = "press"
                self._pintar(n)

        def _soltar(self, n, cmd):
            if not self._activo(n):
                return
            self._est[n] = "hover"
            self._pintar(n)
            cmd()

        def _foco(self, n, si):
            self._est[n] = "foco" if si else "normal"
            self._pintar(n)

        # ---- dibujo y distribución
        def _al_cambiar_tamano(self, _e=None):
            if self._tarea:
                self.after_cancel(self._tarea)
            self._tarea = self.after(60, self._disponer)

        def _disponer(self):
            self._tarea = None
            W, H = self.cv.winfo_width(), self.cv.winfo_height()
            if W < 100 or H < 100:
                return
            if (W, H) != self._dim:
                self._dim = (W, H)
                self._fotos["bg"] = ImageTk.PhotoImage(self._dis.fondo(W, H))
                self.cv.itemconfigure(self._it["bg"], image=self._fotos["bg"])
            s = self._dis.geometria(W, H)[0]
            for n in ("campo_u", "campo_p", "ver", "ing", "sw", "err"):
                self._pintar(n)
            fuente = ("Segoe UI", -max(8, round(22 * s)))
            for clave, campo, nombre in (("e_u", self.u, "campo_u"), ("e_p", self.p, "campo_p")):
                x, y, w, h = self._dis.rect(nombre, W, H)
                izq, der = round(28 * s), round(22 * s)
                campo.configure(font=fuente)
                self.cv.coords(self._it[clave], x + izq, y + h / 2)
                self.cv.itemconfigure(self._it[clave], width=max(10, w - izq - der), height=max(10, round(36 * s)))

        def _pintar(self, n):
            W, H = self.cv.winfo_width(), self.cv.winfo_height()
            if W < 100:
                return
            s = self._dis.geometria(W, H)[0]
            if n == "err":
                if not self._error_actual:
                    self.cv.itemconfigure(self._it["err"], state="hidden")
                    return
                img, pad, alto = self._dis.sprite_error(self._error_actual[0], self._error_actual[1], s)
                ox, oy = self._dis.geometria(W, H)[1:]
                x, y = round(ox + ERR_X0 * s) - pad, round(oy + ERR_CENTRO_Y * s - alto / 2) - pad
            else:
                estado = {"sw": "on" if self._oscuro else "off"}.get(n, self._est.get(n, "normal"))
                img, pad = self._dis.sprite(n, estado, s, self._txt.get(n))
                x, y, _w, _h = self._dis.rect(n, W, H)
                x, y = x - pad, y - pad
            self._fotos[n] = ImageTk.PhotoImage(img)
            self.cv.itemconfigure(self._it[n], image=self._fotos[n], state="normal")
            self.cv.coords(self._it[n], x, y)

        # ---- acciones
        def _alternar_clave(self):
            self._clave_visible = not self._clave_visible
            self.p.ver(self._clave_visible)
            self._txt["ver"] = "Ocultar" if self._clave_visible else "Mostrar"
            self._pintar("ver")

        def _cambiar_modo(self):
            self._oscuro = not self._oscuro
            m = "dark" if self._oscuro else "light"
            ctk.set_appearance_mode(m)
            guardar_modo(m)
            self._pintar("sw")

        def _error(self, texto, tono="danger"):
            """Muestra (o limpia) el aviso bajo la contraseña. ``tono``: danger (rojo) | warn (ámbar)."""
            self._error_actual = (texto, tono) if texto else None
            self._pintar("err")

        def _boton_ingresar(self, texto, activo):
            self._txt["ing"] = texto
            self._est["ing"] = "normal" if activo else "off"
            self._pintar("ing")

        def _restaurar_boton(self):
            self._boton_ingresar("Ingresar", True)

        def entrar(self):
            if self._est["ing"] == "off":
                return
            usuario, clave = self.u.get().strip(), self.p.get()
            if not usuario or not clave:
                return self._error("Escribe tu usuario y tu contraseña.")
            self._error("")
            self._boton_ingresar("Verificando…", False)
            self.update_idletasks()
            try:
                r = db.verificar_credenciales(usuario, clave)     # sin filtrar por estado: así se distingue la cuenta desactivada
            except Exception as e:
                self._restaurar_boton()
                return messagebox.showerror("Base de datos", f"No se pudo conectar a MySQL.\n¿Está encendido XAMPP?\n\n{e}", parent=self)
            if r and not r["activo"]:
                # Credenciales válidas, pero la cuenta fue desactivada por el administrador.
                self.p.delete(0, "end")
                db.log(r["id"], "LOGIN", f"Intento de acceso con la cuenta desactivada «{usuario}»", "FALLIDO")
                self._restaurar_boton()
                self.p.focus_set()
                return self._error(db.MSG_USUARIO_DESACTIVADO, "warn")
            if not r:
                self.p.delete(0, "end")
                try:
                    conocido = db.consulta("SELECT id_usuario FROM usuarios WHERE nombre_usuario=%s", (usuario,), uno=True)
                except Exception:
                    conocido = None
                db.log(conocido["id_usuario"] if conocido else None, "LOGIN",
                       f"Intento de acceso con el usuario «{usuario}»", "FALLIDO")
                self._restaurar_boton()
                self.p.focus_set()
                return self._error("Usuario o contraseña incorrectos.")
            self.usuario = r
            db.log(r["id"], "LOGIN", "Inicio de sesión", "OK")
            try:                                   # cancela tareas pendientes de CTk para evitar «invalid command name»
                for tarea in self.tk.call("after", "info"):
                    try:
                        self.after_cancel(tarea)
                    except Exception:
                        pass
            except Exception:
                pass
            self.destroy()

    return Login


def Login():
    """Crea la ventana de acceso (la clase se arma al primer uso para no importar customtkinter al cargar el módulo)."""
    return _crear_login()()
