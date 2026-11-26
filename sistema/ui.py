"""Componentes visuales reutilizables de Sistema QR (CustomTkinter).

Importante: los widgets de CustomTkinter NO aceptan ``.config()``; hay que usar ``.configure()``.
Este módulo concentra los componentes para que todas las pantallas se vean igual:
tarjetas, botones, campos, selector, contador, tablas, diálogos modales, avisos y «toasts».
"""
import math
import re
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from estilos import C, FUENTE, fuente, colorear_filas
from iconos import icono as _icono
import telefono as tel

R_TARJETA = 18     # radio de las tarjetas
R_CAMPO = 10       # radio de campos y botones
ALTO_CAMPO = 42


# ------------------------------------------------------------------ utilidades
def centrar(win, ancho, alto, parent=None):
    """Centra una ventana (en píxeles lógicos) sobre su padre o sobre la pantalla."""
    win.update_idletasks()
    try:
        esc = float(win.winfo_fpixels("1i")) / 96.0
    except Exception:
        esc = 1.0
    ancho = int(min(ancho, win.winfo_screenwidth() / esc - 30))
    alto = int(min(alto, win.winfo_screenheight() / esc - 80))
    w, h = int(ancho * esc), int(alto * esc)
    try:
        if parent is not None and parent.winfo_exists() and parent.winfo_viewable():
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        else:
            raise ValueError
    except Exception:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2 - 20
    win.geometry(f"{ancho}x{alto}+{max(0, int(x))}+{max(0, int(y))}")


def pantalla_completa(win, activar=True):
    """Abre la ventana maximizada: ocupa toda la pantalla pero conserva la barra de título
    (minimizar, maximizar y cerrar) y la barra de tareas. F11 alterna maximizada/normal.

    customtkinter reinicia la ventana unos instantes después de crearla, lo que deshace el
    maximizado; por eso se reintenta hasta que quede aplicado."""
    win._pc_manual = False       # True cuando el usuario cambió el tamaño con F11: se dejan de reintentar

    def maximizada():
        try:
            return win.state() == "zoomed"
        except Exception:
            return False

    def poner(valor):
        try:
            win.state("zoomed" if valor else "normal")
        except Exception:
            try:
                win.attributes("-zoomed", bool(valor))     # Linux
            except Exception:
                pass

    def alternar(_e=None):
        win._pc_manual = True
        poner(not maximizada())
        return "break"

    def intentar(n=0):
        try:
            if not win.winfo_exists() or win._pc_manual:
                return
            if not maximizada():
                poner(True)
            if n < 12:                           # ~3 s de reintentos por si CTk la revierte
                win.after(250, lambda: intentar(n + 1))
        except Exception:
            pass

    win.bind("<F11>", alternar, add="+")
    if activar:
        win.after(50, intentar)


def tags_fila(i, *extra):
    """Etiquetas de una fila de tabla: la de estado si existe; si no, par/impar (cebra)."""
    extra = tuple(e for e in extra if e)
    return extra if extra else (("par",) if i % 2 == 0 else ("impar",))


# ------------------------------------------------------------------ contenedores
def tarjeta(padre, **kw):
    kw.setdefault("fg_color", C["surface"])
    kw.setdefault("corner_radius", R_TARJETA)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", C["border"])
    return ctk.CTkFrame(padre, **kw)


def transparente(padre, **kw):
    return ctk.CTkFrame(padre, fg_color="transparent", **kw)


def etiqueta(padre, texto="", tam=13, peso="normal", color=None, **kw):
    kw.setdefault("anchor", "w")
    return ctk.CTkLabel(padre, text=texto, font=fuente(tam, peso),
                        text_color=color or C["text"], **kw)


def tenue(padre, texto="", tam=12, **kw):
    return etiqueta(padre, texto, tam, "normal", C["muted"], **kw)


def titulo_seccion(padre, texto, **kw):
    return etiqueta(padre, texto, 16, "bold", **kw)


def separador(padre, **kw):
    return ctk.CTkFrame(padre, height=1, fg_color=C["border"], corner_radius=0, **kw)


def insignia(padre, texto, tono="primary", **kw):
    """Pastilla de color (estado, rol…). tono: primary | ok | danger | warn."""
    return ctk.CTkLabel(padre, text=texto, font=fuente(11, "bold"), corner_radius=20,
                        fg_color=C[tono + "_soft"], text_color=C[tono], height=24, **kw)


# ------------------------------------------------------------------ botones
# Sistema de botones de TRES ESTADOS (más «deshabilitado»):
#   normal     fondo blanco/transparente, borde fino, texto oscuro        -> reposo
#   hover      fondo azul muy suave, borde e texto azul cobalto           -> «puedes pulsarme»
#   presionado azul cobalto #0047AB completo, texto e icono blancos       -> acción activada / opción seleccionada
#
# Tipos (parámetro ``estilo``):
#   "accion"     acción puntual (Registrar entrada, Buscar cliente…): se ilumina, parpadea en cobalto al pulsar y vuelve a reposo.
#   "pri"        principal (Guardar, Ingresar, Facturar…): conserva el relleno cobalto; solo uno destacado por pantalla/ventana.
#   "danger"     acción destructiva (Eliminar, Cancelar orden, Cerrar sesión): mismos tres estados, en rojo.
#   "ghost"      acción discreta sin borde (Actualizar).
#   "nav"        navegación (menú lateral): la opción ACTIVA queda en cobalto (``seleccionar``).
#   "seleccion"  selección persistente (interruptores, filtros): cada clic alterna; seleccionado = cobalto.
# Alias por compatibilidad: "sec" y "outline" = "accion".
_BLANCO = ("#FFFFFF", "#FFFFFF")
_FLASH_MS = 160          # cuánto dura el azul cobalto al pulsar un botón de acción puntual

_ACCION = {
    "normal":     dict(fg=C["surface"], borde=C["btn_borde"], txt=C["btn_texto"]),
    "hover":      dict(fg=C["cobalto_soft"], borde=C["btn_borde_h"], txt=C["cobalto_txt"]),
    "presionado": dict(fg=C["cobalto"], borde=C["cobalto"], txt=_BLANCO),
    "off":        dict(fg=C["surface2"], borde=C["border"], txt=C["muted"]),
}
_SIN_BORDE = {      # base de «ghost» y «nav»: transparentes, con el mismo hover y selección azules
    "normal":     dict(fg="transparent", borde=C["border"], txt=C["muted"]),
    "hover":      dict(fg=C["cobalto_soft"], borde=C["border"], txt=C["cobalto_txt"]),
    "presionado": dict(fg=C["cobalto"], borde=C["cobalto"], txt=_BLANCO),
    "off":        dict(fg="transparent", borde=C["border"], txt=C["muted"]),
}
_NAV = {            # menú lateral: la opción activa va en azul eléctrico, como en el diseño del panel
    "normal":     dict(fg="transparent", borde=C["border"], txt=C["btn_texto"]),
    "hover":      dict(fg=C["hover"], borde=C["border"], txt=C["cobalto_txt"]),
    "presionado": dict(fg=C["nav_sel"], borde=C["nav_sel"], txt=_BLANCO),
    "off":        dict(fg="transparent", borde=C["border"], txt=C["muted"]),
}
_ESTILOS_BTN = {
    "accion": dict(ancho_borde=1, estados=_ACCION),
    "seleccion": dict(ancho_borde=1, estados=_ACCION),
    "pri": dict(ancho_borde=0, estados={
        "normal":     dict(fg=C["cobalto"], borde=C["cobalto"], txt=_BLANCO),
        "hover":      dict(fg=C["cobalto_h"], borde=C["cobalto_h"], txt=_BLANCO),
        "presionado": dict(fg=C["cobalto_p"], borde=C["cobalto_p"], txt=_BLANCO),
        "off":        dict(fg=("#BCCBE6", "#2A3A5C"), borde=("#BCCBE6", "#2A3A5C"), txt=("#F5F8FF", "#7F8CB5")),
    }),
    "danger": dict(ancho_borde=1, estados={
        "normal":     dict(fg=C["surface"], borde=C["danger_borde"], txt=C["danger"]),
        "hover":      dict(fg=C["danger_soft"], borde=C["danger"], txt=C["danger"]),
        "presionado": dict(fg=C["danger_press"], borde=C["danger_press"], txt=_BLANCO),
        "off":        dict(fg=C["surface2"], borde=C["border"], txt=C["muted"]),
    }),
    "ghost": dict(ancho_borde=0, estados=_SIN_BORDE),
    "nav": dict(ancho_borde=0, estados=_NAV),
}
_ALIAS_BTN = {"sec": "accion", "outline": "accion"}


class Boton(ctk.CTkButton):
    """Botón con el sistema de tres estados (ver el bloque de comentarios de arriba).

    Además de lo habitual de CTkButton:
    * ``estilo``: accion | pri | danger | ghost | nav | seleccion (y los alias «sec», «outline»).
    * ``icono``: nombre de iconos.py. Se repinta solo en cada estado (oscuro -> azul -> blanco).
    * ``seleccionable``: cada clic alterna el estado «seleccionado» (cobalto fijo). Por defecto solo en «seleccion».
    * ``seleccionar(True/False)`` / ``seleccionado``: para botones de navegación o selección controlados desde fuera.
    * ``configure(state=...)``, ``configure(command=...)`` y ``configure(icono=...)`` funcionan como siempre.
    """

    def __init__(self, master, text="", command=None, estilo="accion", ancho=None, alto=40, tam=13,
                 icono=None, tam_icono=17, seleccionable=None, radio=None, **kw):
        estilo = _ALIAS_BTN.get(estilo, estilo)
        espec = _ESTILOS_BTN[estilo]
        self._bt_estados = espec["estados"]
        self._bt_cmd = command
        self._bt_sel = False
        self._bt_dentro = False
        self._bt_presionado = False
        self._bt_estado = kw.get("state", "normal")
        self._bt_seleccionable = (estilo == "seleccion") if seleccionable is None else bool(seleccionable)
        self._bt_tam_icono = tam_icono
        self._bt_imgs = self._bt_crear_imagenes(icono)
        normal, off = self._bt_estados["normal"], self._bt_estados["off"]
        extra = {}
        if ancho:
            extra["width"] = ancho
        if self._bt_imgs:
            extra.update(image=self._bt_imgs["normal"], compound="left")
        # hover=False: los colores de hover/pulsado los pinta _bt_pintar (la librería solo tiene hover/normal).
        super().__init__(master, text=text, command=self._bt_al_pulsar, height=alto,
                         corner_radius=R_CAMPO if radio is None else radio,
                         fg_color=normal["fg"], hover=False,
                         hover_color=self._bt_estados["hover"]["fg"] if estilo not in ("ghost", "nav") else C["hover"],
                         border_width=espec["ancho_borde"], border_color=normal["borde"],
                         text_color=normal["txt"], text_color_disabled=off["txt"], font=fuente(tam, "bold"),
                         **extra, **kw)
        self.bind("<Enter>", self._bt_entra, add="+")
        self.bind("<Leave>", self._bt_sale, add="+")
        self._bt_pintar()

    # ---- iconos: uno por estado, con el color del texto de ese estado
    def _bt_crear_imagenes(self, nombre):
        if not nombre:
            return {}
        imgs = {k: _icono(nombre, self._bt_tam_icono, e["txt"]) for k, e in self._bt_estados.items()}
        return imgs if all(v is not None for v in imgs.values()) else {}

    # ---- estado visual
    def _bt_puntero_dentro(self):
        try:
            x, y = self.winfo_pointerxy()
            return (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                    and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        except tk.TclError:
            return False

    def _bt_entra(self, _e=None):
        self._bt_dentro = True
        self._bt_pintar()

    def _bt_sale(self, _e=None):
        # Entre el lienzo del botón y su texto saltan <Leave>/<Enter> seguidos: solo se apaga si el puntero salió de verdad.
        self._bt_dentro = self._bt_puntero_dentro()
        self._bt_pintar()

    def _bt_nombre_estado(self):
        if self._bt_estado == "disabled":
            return "off"
        if self._bt_presionado or self._bt_sel:
            return "presionado"
        return "hover" if self._bt_dentro else "normal"

    def _bt_pintar(self):
        try:
            if not self.winfo_exists():
                return
            nombre = self._bt_nombre_estado()
            e = self._bt_estados[nombre]
            kw = dict(fg_color=e["fg"], border_color=e["borde"], text_color=e["txt"])
            if self._bt_imgs:
                kw["image"] = self._bt_imgs[nombre]
            ctk.CTkButton.configure(self, **kw)
        except tk.TclError:
            pass

    def _bt_al_pulsar(self):
        """Pulsación: destello cobalto (o alternar la selección) y después la acción del botón."""
        if self._bt_seleccionable:
            self._bt_sel = not self._bt_sel
        self._bt_presionado = True
        self._bt_pintar()
        try:
            self.update_idletasks()          # se ve el cobalto aunque la acción abra un cuadro modal
        except tk.TclError:
            pass
        self.after(_FLASH_MS, self._bt_soltar)
        if self._bt_cmd is not None:
            self._bt_cmd()

    def _bt_soltar(self):
        try:
            if not self.winfo_exists():      # la acción pudo cerrar la ventana del botón
                return
        except tk.TclError:
            return
        self._bt_presionado = False
        self._bt_dentro = self._bt_puntero_dentro()
        self._bt_pintar()

    # ---- API pública
    @property
    def seleccionado(self):
        return self._bt_sel

    def seleccionar(self, valor=True):
        """Marca/desmarca el botón como seleccionado (cobalto fijo)."""
        self._bt_sel = bool(valor)
        self._bt_pintar()

    def configure(self, require_redraw=False, **kw):
        repintar = False
        if "command" in kw:
            self._bt_cmd = kw.pop("command")
        if "icono" in kw:
            self._bt_imgs = self._bt_crear_imagenes(kw.pop("icono"))
            repintar = True
        if "state" in kw:
            self._bt_estado = kw["state"]
            repintar = True
        if kw or require_redraw:
            super().configure(require_redraw=require_redraw, **kw)
        if repintar:
            self._bt_pintar()


def icono_boton(padre, texto, comando=None, lado=36, icono=None, tam_icono=18, estilo="accion", **kw):
    """Botón cuadrado pequeño. Con ``icono`` (nombre de iconos.py) muestra el icono; si no, ``texto``."""
    if icono and _icono(icono, tam_icono, C["text"]) is not None:
        texto = ""
    else:
        icono = None
    return Boton(padre, texto, comando, estilo, ancho=lado, alto=lado, tam=14, icono=icono, tam_icono=tam_icono,
                 radio=10, **kw)


# ------------------------------------------------------------------ campos
def campo(padre, ancho=260, placeholder="", mostrar=None, **kw):
    """Campo de texto moderno."""
    return ctk.CTkEntry(padre, width=ancho, height=ALTO_CAMPO, corner_radius=R_CAMPO, border_width=1,
                        fg_color=C["surface2"], border_color=C["btn_borde"], text_color=C["text"],
                        placeholder_text=placeholder or None,
                        placeholder_text_color=C["muted"], show=mostrar or "", font=fuente(13), **kw)


def campo_solo_lectura(ent, texto):
    """Escribe un texto en un campo y lo deja de solo lectura."""
    ent.configure(state="normal")
    ent.delete(0, "end")
    ent.insert(0, texto)
    ent.configure(state="readonly")


class Buscador(ctk.CTkFrame):
    """Campo de búsqueda limpio: lupa a la izquierda, texto sin marco y «×» para borrar (solo con texto escrito).

    * ``comando(texto)`` se llama mientras se escribe, con una pausa corta (``retraso`` ms) para no recalcular
      en cada tecla; también al pegar, cortar, borrar con «×» o pulsar Esc.
    * El texto de ayuda (``placeholder``) es discreto y desaparece al escribir.
    * Al enfocarlo, el borde y la lupa se vuelven azul cobalto.
    * Métodos: get(), set(texto), limpiar(), focus_set().
    """

    def __init__(self, master, placeholder="", ancho=420, comando=None, retraso=120, **kw):
        super().__init__(master, width=ancho, height=ALTO_CAMPO, corner_radius=R_CAMPO + 4, border_width=1,
                         fg_color=C["surface"], border_color=C["border"], **kw)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._comando = comando
        self._retraso = retraso
        self._pendiente = None
        self._ultimo = ""
        self._lupas = (_icono("search", 18, C["muted"]), _icono("search", 18, C["cobalto_txt"]))
        self._lupa = ctk.CTkLabel(self, text="" if self._lupas[0] is not None else "⌕", image=self._lupas[0],
                                  width=24, fg_color="transparent", text_color=C["muted"], font=fuente(16))
        self._lupa.grid(row=0, column=0, padx=(14, 0))
        self.entrada = ctk.CTkEntry(self, width=40, height=ALTO_CAMPO - 8, border_width=0, corner_radius=0,
                                    fg_color=C["surface"], text_color=C["text"], font=fuente(13),
                                    placeholder_text=placeholder or None, placeholder_text_color=C["muted"])
        self.entrada.grid(row=0, column=1, sticky="ew", padx=(6, 4))
        x = _icono("x", 14, C["muted"])
        self._borrar = ctk.CTkButton(self, text="" if x is not None else "×", image=x, width=26, height=26,
                                     corner_radius=13, fg_color="transparent", hover_color=C["hover"],
                                     text_color=C["muted"], font=fuente(14, "bold"), command=self.limpiar)
        self._borrar.grid(row=0, column=2, padx=(0, 8))
        self._borrar.grid_remove()                    # solo se muestra cuando hay texto
        for secuencia, funcion in (("<KeyRelease>", self._cambio), ("<<Paste>>", self._cambio_diferido),
                                   ("<<Cut>>", self._cambio_diferido), ("<FocusIn>", self._con_foco),
                                   ("<FocusOut>", self._sin_foco), ("<Escape>", lambda _e: self.limpiar())):
            self.entrada.bind(secuencia, funcion, add="+")

    # ---- eventos
    def _con_foco(self, _e=None):
        self.configure(border_color=C["cobalto_txt"])
        if self._lupas[1] is not None:
            self._lupa.configure(image=self._lupas[1])

    def _sin_foco(self, _e=None):
        self.configure(border_color=C["border"])
        if self._lupas[0] is not None:
            self._lupa.configure(image=self._lupas[0])

    def _cambio_diferido(self, _e=None):
        self.after(30, self._cambio)                  # el texto pegado/cortado aún no está en el campo durante el evento

    def _cambio(self, _e=None):
        try:
            texto = self.entrada.get()
        except tk.TclError:
            return
        if texto:
            self._borrar.grid()
        else:
            self._borrar.grid_remove()
        if texto == self._ultimo:                     # flechas, Mayús, etc.: el texto no cambió
            return
        self._ultimo = texto
        if self._pendiente is not None:
            self.after_cancel(self._pendiente)
        self._pendiente = self.after(self._retraso, self._disparar)

    def _disparar(self):
        self._pendiente = None
        if self._comando is not None:
            self._comando(self.entrada.get())

    # ---- API
    def get(self):
        return self.entrada.get()

    def set(self, texto):
        self.entrada.delete(0, "end")
        if texto:
            self.entrada.insert(0, texto)
        self._cambio()

    def limpiar(self):
        """Borra el texto, devuelve el foco al campo y actualiza los resultados de inmediato."""
        self.entrada.delete(0, "end")
        self._borrar.grid_remove()
        self._ultimo = ""
        if self._pendiente is not None:
            self.after_cancel(self._pendiente)
            self._pendiente = None
        self.entrada.focus_set()
        self._disparar()

    def focus_set(self):
        self.entrada.focus_set()


class Combo(ctk.CTkOptionMenu):
    """Selector desplegable. Mantiene ``get``/``set``/``current`` como el Combobox clásico."""

    def __init__(self, master, values=(), ancho=260, command=None, **kw):
        self._valores = list(values)
        self._cb = command
        super().__init__(master, values=self._valores or [""], width=ancho, height=ALTO_CAMPO,
                         corner_radius=R_CAMPO, fg_color=C["surface2"], button_color=C["surface2"],
                         button_hover_color=C["hover"], text_color=C["text"],
                         dropdown_fg_color=C["surface"], dropdown_hover_color=C["primary_soft"],
                         dropdown_text_color=C["text"], font=fuente(13), dropdown_font=fuente(13),
                         dynamic_resizing=False, anchor="w", command=self._cambio, **kw)
        if self._valores:
            self.set(self._valores[0])

    def _cambio(self, valor):
        if self._cb:
            self._cb(valor)

    def al_cambiar(self, fn):
        """Registra la función que se llamará al elegir otra opción."""
        self._cb = fn

    def current(self, i=None):
        if i is None:
            try:
                return self._valores.index(self.get())
            except ValueError:
                return -1
        self.set(self._valores[i])

    def valores(self, nuevos):
        self._valores = list(nuevos)
        self.configure(values=self._valores or [""])


class Contador(ctk.CTkFrame):
    """Cantidad entera con botones − / +. Métodos: get(), set(v), focus_set()."""

    def __init__(self, master, minimo=0, maximo=999999, valor=1, ancho=150, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.minimo, self.maximo = minimo, maximo
        self._menos = Boton(self, "−", lambda: self._paso(-1), "accion", ancho=38, alto=ALTO_CAMPO, tam=16)
        self._menos.pack(side="left")
        self._ent = ctk.CTkEntry(self, width=max(50, ancho - 84), height=ALTO_CAMPO, corner_radius=R_CAMPO,
                                 border_width=1, fg_color=C["surface2"], border_color=C["btn_borde"],
                                 text_color=C["text"], justify="center", font=fuente(13, "bold"))
        self._ent.pack(side="left", padx=6)
        self._mas = Boton(self, "+", lambda: self._paso(1), "accion", ancho=38, alto=ALTO_CAMPO, tam=16)
        self._mas.pack(side="left")
        self.set(valor)

    def _paso(self, d):
        try:
            v = int(self._ent.get())
        except ValueError:
            v = self.minimo
        self.set(max(self.minimo, min(self.maximo, v + d)))

    def get(self):
        return self._ent.get()

    def set(self, v):
        self._ent.delete(0, "end")
        self._ent.insert(0, str(v))

    def focus_set(self):
        self._ent.focus_set()


def limitar_digitos(entrada, maximo):
    """El campo acepta solo números y hasta ``maximo`` dígitos (también al pegar texto)."""
    cmd = entrada.register(lambda p: p == "" or (p.isdigit() and len(p) <= maximo))
    entrada.configure(validate="key", validatecommand=(cmd, "%P"))


def limitar_decimal(entrada, decimales=2, maximo=12):
    """Solo números con un separador decimal (punto o coma) y hasta ``decimales`` decimales."""
    patron = re.compile(r"^\d*[.,]?\d{0,%d}$" % decimales)
    cmd = entrada.register(lambda p: len(p) <= maximo and bool(patron.match(p)))
    entrada.configure(validate="key", validatecommand=(cmd, "%P"))


def limitar_caracteres(entrada, permitidos, maximo):
    """Acepta solo los caracteres de ``permitidos`` (cadena) y hasta ``maximo`` caracteres."""
    cmd = entrada.register(lambda p: len(p) <= maximo and all(ch in permitidos for ch in p))
    entrada.configure(validate="key", validatecommand=(cmd, "%P"))


class CampoTelefono(ctk.CTkFrame):
    """[ 0412 ▼ ] [ 1234567 ]: prefijo móvil desplegable + siete dígitos.

    ``get()`` devuelve el número completo (04121234567) o "" si no hay número; ``set(texto)`` separa el
    prefijo y los siete dígitos de un teléfono guardado; ``error()`` explica por qué no se puede guardar.
    """

    def __init__(self, master, ancho=560, prefijos=tel.PREFIJOS_MOVIL, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._legado = None          # teléfono guardado con otro formato: se muestra tal cual, sin alterarlo
        self.combo = Combo(self, values=list(prefijos), ancho=112)
        self.combo.set(tel.PREFIJO_PREDETERMINADO)
        self.combo.pack(side="left")
        self.num = campo(self, max(120, ancho - 122), "1234567")
        self.num.pack(side="left", padx=(10, 0), fill="x", expand=True)
        limitar_digitos(self.num, tel.DIGITOS_NUMERO)
        self.num.bind("<KeyRelease>", lambda _e: setattr(self, "_legado", None), add="+")

    def set(self, telefono):
        """Muestra un teléfono guardado (recupera prefijo y número); vacío = prefijo predeterminado."""
        self.num.configure(validate="none", state="normal")
        self.num.delete(0, "end")
        self._legado = None
        self.combo.set(tel.PREFIJO_PREDETERMINADO)
        txt = "" if telefono is None else str(telefono).strip()
        partes = tel.dividir(txt)
        if partes:
            if partes[0] not in self.combo._valores:        # prefijo guardado que no está en la lista: se agrega
                self.combo.valores(sorted(self.combo._valores + [partes[0]]))
            self.combo.set(partes[0])
            self.num.insert(0, partes[1])
        elif txt:                                            # formato antiguo: se respeta
            self._legado = txt
            self.num.insert(0, txt)
        limitar_digitos(self.num, tel.DIGITOS_NUMERO)

    def get(self):
        if self._legado:
            return self._legado
        return tel.unir(self.combo.get(), self.num.get().strip())

    def error(self):
        """None si se puede guardar; si no, el mensaje para el usuario."""
        if self._legado:
            return None
        return tel.error_partes(self.combo.get(), self.num.get(), tuple(self.combo._valores))

    def estado(self, modo):
        """'normal' = editable; cualquier otro valor = solo lectura."""
        editable = modo == "normal"
        self.combo.configure(state="normal" if editable else "disabled")
        self.num.configure(state="normal" if editable else ("readonly" if self.get() else "disabled"))

    def focus_set(self):
        self.num.focus_set()


def fila_formulario(padre, fila, texto, widget, ayuda=None, col_widget=1, sticky="ew"):
    """Etiqueta arriba del campo, en una grilla de dos columnas (etiqueta | campo)."""
    etiqueta(padre, texto, 12, "bold", C["muted"]).grid(row=fila, column=0, sticky="w", pady=(10, 0), columnspan=2)
    widget.grid(row=fila + 1, column=0, columnspan=2, sticky=sticky, pady=(4, 0))
    if ayuda is not None:
        ayuda.grid(row=fila + 2, column=0, columnspan=2, sticky="w", pady=(3, 0))


# ------------------------------------------------------------------ tablas
def tabla(padre, columnas, encabezados, anchos, anclas=None, h_scroll=False, **kw):
    """Tarjeta con una tabla (ttk.Treeview) y barras de desplazamiento modernas.

    Devuelve (tarjeta, treeview). ``encabezados`` y ``anclas`` son dicts por columna.
    """
    marco = tarjeta(padre, **kw)
    marco.grid_rowconfigure(0, weight=1)
    marco.grid_columnconfigure(0, weight=1)
    tv = ttk.Treeview(marco, columns=columnas, show="headings", selectmode="browse")
    anclas = anclas or {}
    for c, w in zip(columnas, anchos):
        tv.heading(c, text=encabezados[c], anchor=anclas.get(c, "w"))
        tv.column(c, width=w, minwidth=60, anchor=anclas.get(c, "w"), stretch=True)
    sb = ctk.CTkScrollbar(marco, command=tv.yview, corner_radius=8)
    tv.configure(yscrollcommand=sb.set)
    tv.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
    sb.grid(row=0, column=1, sticky="ns", padx=(4, 6), pady=10)
    if h_scroll:
        sh = ctk.CTkScrollbar(marco, command=tv.xview, orientation="horizontal", corner_radius=8)
        tv.configure(xscrollcommand=sh.set)
        sh.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    colorear_filas(tv)
    return marco, tv


# ------------------------------------------------------------------ ventanas modales
class Dialogo(ctk.CTkToplevel):
    """Ventana secundaria con el estilo de la aplicación. ``modal=True`` bloquea la ventana padre."""

    def __init__(self, parent, titulo, ancho=520, alto=420, modal=True, redim=False):
        super().__init__(parent)
        self.withdraw()
        self.title(titulo)
        self.configure(fg_color=C["bg"])
        self.resizable(redim, redim)
        self._padre = parent
        self._modal = modal
        centrar(self, ancho, alto, parent)
        try:
            if parent.winfo_viewable():
                self.transient(parent.winfo_toplevel())
        except Exception:
            pass
        self.deiconify()
        if modal:
            self.after(150, self._tomar_foco)

    def _tomar_foco(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def cuerpo(self, pad=22, scroll=False):
        """Contenedor principal con relleno; opcionalmente desplazable."""
        if scroll:
            c = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
            c.pack(fill="both", expand=True, padx=pad - 8, pady=pad - 10)
        else:
            c = ctk.CTkFrame(self, fg_color="transparent")
            c.pack(fill="both", expand=True, padx=pad, pady=pad)
        return c


# ------------------------------------------------------------------ avisos (reemplazan a messagebox)
_ICONOS = {"info": ("✓", "ok"), "warning": ("!", "warn"), "error": ("✕", "danger"), "question": ("?", "primary")}
_ICONO_AVISO = {"info": "check", "warning": "triangle-alert", "error": "x", "question": "circle-help"}


def _sello_aviso(padre, tipo, lado, tam_icono, tam_glifo):
    """Círculo de color con el icono del tipo de aviso (o su glifo de texto si no se pudo dibujar el icono)."""
    glifo, tono = _ICONOS[tipo]
    img = _icono(_ICONO_AVISO[tipo], tam_icono, C[tono])
    if img is not None:
        return ctk.CTkLabel(padre, text="", image=img, width=lado, height=lado, corner_radius=lado // 2,
                            fg_color=C[tono + "_soft"])
    return ctk.CTkLabel(padre, text=glifo, width=lado, height=lado, corner_radius=lado // 2, fg_color=C[tono + "_soft"],
                        text_color=C[tono], font=fuente(tam_glifo, "bold"))


def _raiz(parent):
    if parent is not None:
        try:
            if parent.winfo_exists():
                return parent
        except Exception:
            pass
    return tk._default_root


def _dialogo_mensaje(titulo, texto, tipo, parent, botones):
    """Cuadro modal estilizado. ``botones``: lista de (texto, valor, estilo). Devuelve el valor elegido."""
    raiz = _raiz(parent)
    lineas = sum(max(1, math.ceil(len(t) / 50)) for t in str(texto).split("\n"))
    alto = int(min(620, 178 + lineas * 21))
    d = Dialogo(raiz, titulo, 480, alto)
    resultado = {"v": botones[-1][1] if botones else None}
    tono = _ICONOS[tipo][1]
    cuerpo = d.cuerpo(24)
    fila = transparente(cuerpo)
    fila.pack(fill="both", expand=True)
    _sello_aviso(fila, tipo, 46, 22, 20).pack(side="left", anchor="n", padx=(0, 16))
    col = transparente(fila)
    col.pack(side="left", fill="both", expand=True)
    etiqueta(col, titulo, 16, "bold").pack(anchor="w")
    etiqueta(col, str(texto), 13, color=C["muted"], justify="left", wraplength=340).pack(anchor="w", pady=(6, 0))
    barra = transparente(cuerpo)
    barra.pack(fill="x", pady=(14, 0))

    def elegir(v):
        resultado["v"] = v
        d.destroy()

    for texto_b, valor, estilo in botones:      # el primero (principal) queda más a la derecha
        Boton(barra, texto_b, lambda v=valor: elegir(v), estilo=estilo, ancho=110).pack(side="right", padx=(8, 0))
    cerrar = botones[-1][1]                      # cerrar la ventana = última opción (No / Entendido)
    d.protocol("WM_DELETE_WINDOW", lambda: elegir(cerrar))
    d.bind("<Escape>", lambda _e: elegir(cerrar))
    d.wait_window()
    return resultado["v"]


def toast(parent, texto, tipo="info", ms=3600):
    """Aviso no bloqueante, abajo a la derecha de la ventana principal."""
    raiz = _raiz(parent)
    if raiz is None:
        return
    try:
        raiz = raiz.winfo_toplevel()
        tono = _ICONOS[tipo][1]
        caja = ctk.CTkFrame(raiz, fg_color=C["surface"], corner_radius=14, border_width=1, border_color=C[tono])
        _sello_aviso(caja, tipo, 30, 16, 14).pack(side="left", padx=(12, 10), pady=12)
        ctk.CTkLabel(caja, text=str(texto), text_color=C["text"], font=fuente(12), justify="left",
                     wraplength=330).pack(side="left", padx=(0, 16), pady=12)
        caja.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        caja.lift()
        caja.after(ms, lambda: caja.winfo_exists() and caja.destroy())
        caja.bind("<Button-1>", lambda _e: caja.destroy())
    except tk.TclError:
        pass


class messagebox:   # noqa: N801  (mismo nombre que tkinter.messagebox para no tocar la lógica)
    @staticmethod
    def showinfo(titulo, mensaje, parent=None, **_):
        toast(parent, mensaje, "info")
        return "ok"

    @staticmethod
    def showwarning(titulo, mensaje, parent=None, **_):
        return _dialogo_mensaje(titulo, mensaje, "warning", parent, [("Entendido", "ok", "pri")])

    @staticmethod
    def showerror(titulo, mensaje, parent=None, **_):
        return _dialogo_mensaje(titulo, mensaje, "error", parent, [("Cerrar", "ok", "pri")])

    @staticmethod
    def askyesno(titulo, mensaje, parent=None, icon=None, **_):
        return _dialogo_mensaje(titulo, mensaje, "question" if icon != "warning" else "warning", parent,
                                [("Sí", True, "pri"), ("No", False, "accion")])
