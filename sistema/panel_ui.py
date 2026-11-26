"""Estructura visual del sistema (diseño «panel industrial»): barra lateral, cabecera con fecha y tasa BCV, y la
pantalla «Resumen general» con indicadores, ventas recientes, pistón más vendido, accesos rápidos y estado del inventario.

``PanelMixin`` se mezcla con la ventana principal (``App``) y aporta estos métodos. Los gráficos se dibujan con Pillow
(ver panel_graficos.py) y se vuelven a dibujar solos al cambiar el tamaño de la ventana o el modo claro/oscuro.
"""
import datetime
import os
import tkinter as tk
from functools import partial

import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw

import conexion as db
import marca
import panel_graficos as G
from estilos import C, _c, fuente, modo_actual, guardar_modo, estilizar_tablas, colorear_filas
from iconos import icono
from login_visual import RUTA_FONDO
from ui import Boton, Combo, tarjeta, transparente, etiqueta, tenue, icono_boton

ANCHO_LATERAL = 268
SQL_RESUMEN = (
    "SELECT COUNT(*) AS referencias, COALESCE(SUM(e.stock),0) AS unidades, "
    "COALESCE(SUM(CASE WHEN p.activo=0 THEN 1 ELSE 0 END),0) AS desactivados, "
    "COALESCE(SUM(CASE WHEN p.activo=1 AND COALESCE(e.stock,0)<=p.stock_minimo THEN 1 ELSE 0 END),0) AS bajos, "
    "COALESCE(SUM(CASE WHEN p.activo=1 AND COALESCE(e.stock,0)=0 THEN 1 ELSE 0 END),0) AS agotados, "
    "COALESCE(SUM(CASE WHEN p.activo=1 THEN 1 ELSE 0 END),0) AS activos, "
    "COALESCE(SUM(CASE WHEN p.activo=1 AND COALESCE(e.stock,0)>0 AND COALESCE(e.stock,0)<=p.stock_minimo THEN 1 ELSE 0 END),0) AS poco "
    "FROM pistones p LEFT JOIN existencias e ON e.id_piston=p.id_piston")
_NO_ANULADA = "UPPER(f.estado) NOT IN ('ANULADA','CANCELADA')"
RANGOS = {"Últimos 7 días": 7, "Últimos 14 días": 14, "Últimos 30 días": 30}


class Lienzo(tk.Canvas):
    """Canvas que muestra una imagen dibujada con Pillow a su tamaño real y la rehace al redimensionarse."""

    def __init__(self, master, render, alto, ancho=None, fondo="surface", **kw):
        super().__init__(master, height=alto, width=ancho or 10, highlightthickness=0, bd=0, bg=_c(fondo), **kw)
        self._render, self._fondo, self._tarea, self._foto = render, fondo, None, None
        self._img = self.create_image(0, 0, anchor="nw")
        self.bind("<Configure>", self._al_cambiar)

    def _al_cambiar(self, _e=None):
        if self._tarea:
            self.after_cancel(self._tarea)
        self._tarea = self.after(30, self.redibujar)

    def redibujar(self):
        self._tarea = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        try:
            self.configure(bg=_c(self._fondo))
            self._foto = ImageTk.PhotoImage(self._render(w, h))
            self.itemconfigure(self._img, image=self._foto)
        except Exception:
            pass


def _cargar_img(ruta, tam):
    try:
        im = Image.open(ruta)
        im.load()
        im.thumbnail(tam)
        return ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
    except Exception:
        return None


def _decoracion_lateral(ancho, alto):
    """Pistones difuminados para el pie de la barra lateral (solo modo oscuro). None si falta la imagen."""
    try:
        src = Image.open(RUTA_FONDO).convert("RGB")
        a = src.crop((0, 540, 560, 941))
        esc = max(ancho * 2 / a.width, alto * 2 / a.height)
        a = a.resize((round(a.width * esc), round(a.height * esc)), Image.LANCZOS)
        a = a.crop((0, a.height - alto * 2, ancho * 2, a.height))
        lado = Image.new("RGB", a.size, G.rgb("#060E1A"))
        mascara = Image.linear_gradient("L").resize(a.size)                # transparente arriba, visible abajo
        mascara = mascara.point(lambda v: int(((v / 255) ** 1.4) * 215))
        return Image.composite(a, lado, mascara).resize((ancho, alto), Image.LANCZOS)
    except Exception:
        return None


class PanelMixin:
    # ------------------------------------------------------------ utilidades
    def _factor_esc(self):
        try:
            return max(1.0, float(self.winfo_fpixels("1i")) / 96.0)
        except Exception:
            return 1.0

    def _colores(self):
        return dict(bg=_c("bg"), surface=_c("surface"), surface2=_c("surface2"), borde=_c("border"), text=_c("text"),
                    muted=_c("muted"), dark=modo_actual() == "dark")

    def _poner_titulo(self, titulo):
        """Título en dos tonos: todo en blanco salvo la última palabra, en azul (como en el diseño)."""
        partes = titulo.rsplit(" ", 1)
        if len(partes) == 2:
            self.lb_titulo.configure(text=partes[0] + " ")
            self.lb_titulo2.configure(text=partes[1])
        else:
            self.lb_titulo.configure(text="")
            self.lb_titulo2.configure(text=titulo)
        self.lb_fecha.configure(text=datetime.date.today().strftime("%d/%m/%Y"))

    def repintar_panel(self):
        """Tras cambiar de modo claro/oscuro: rehace los gráficos y el color de los tableros."""
        for lz in getattr(self, "_lienzos", []):
            try:
                lz.redibujar()
            except Exception:
                pass

    # ------------------------------------------------------------ barra lateral
    def _construir_sidebar(self):
        sb = ctk.CTkFrame(self, width=ANCHO_LATERAL, corner_radius=0, fg_color=C["side"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.pack_propagate(False)
        self.sidebar = sb
        alto_deco = 250
        deco = _decoracion_lateral(ANCHO_LATERAL, alto_deco)
        if deco is not None:                       # se crea primero: queda detrás de todo lo demás
            blanco = Image.new("RGB", deco.size, (255, 255, 255))
            self._deco = ctk.CTkImage(light_image=blanco, dark_image=deco, size=(ANCHO_LATERAL, alto_deco))
            ctk.CTkLabel(sb, text="", image=self._deco, fg_color="transparent").place(relx=0, rely=1.0, anchor="sw")
        cab = transparente(sb)
        cab.pack(fill="x", padx=22, pady=(30, 26))
        self._logo_lateral = lg = marca.logo_ctk(212)
        if lg is not None:
            ctk.CTkLabel(cab, text="", image=lg).pack()
        else:
            etiqueta(cab, "Manufacturas de Aluminio I, C.A.", 14, "bold", wraplength=210, justify="center").pack()
        etiqueta(sb, "MENÚ", 11, "bold", C["muted"]).pack(anchor="w", padx=30, pady=(0, 8))
        # Todos los roles ven el menú completo: los módulos que no les corresponden responden «Acceso denegado» (ver mostrar_pagina).
        items = [("inicio", "layout-dashboard", "Resumen general"), ("registro", "piston", "Registrar pistón"),
                 ("inventario", "boxes", "Inventario"), ("existencias", "arrow-left-right", "Existencias"),
                 ("ventas", "shopping-cart", "Ventas"), ("facturas", "receipt-text", "Facturación"),
                 ("usuarios", "users", "Usuarios")]
        for clave, ico, texto in items:
            b = Boton(sb, f"  {texto}", lambda k=clave: self.mostrar_pagina(k), "nav", alto=48, tam=14,
                      icono=ico, tam_icono=22, radio=12, anchor="w")
            b.pack(fill="x", padx=14, pady=2)
            self.nav_buttons[clave] = b

        # Pie: tarjeta de sesión y, encima, el interruptor de modo oscuro (se empaquetan de abajo hacia arriba).
        ses = tarjeta(sb, fg_color=C["surface"], border_color=C["border"], corner_radius=16)
        ses.pack(side="bottom", fill="x", padx=14, pady=(0, 18))
        fila = transparente(ses)
        fila.pack(fill="x", padx=14, pady=(14, 10))
        ctk.CTkLabel(fila, text=self.user["nombre"][:1].upper(), width=46, height=46, corner_radius=23,
                     fg_color=C["nav_sel"], text_color="#FFFFFF", font=fuente(18, "bold")).pack(side="left")
        dt = transparente(fila)
        dt.pack(side="left", padx=(12, 0))
        etiqueta(dt, self.user["nombre"], 16, "bold").pack(anchor="w")
        tenue(dt, self.user["rol"], 12).pack(anchor="w")
        if self.es_control:
            tenue(dt, f"Control {int(self.user.get('etapa') or 0)}" if self.user.get("etapa") else "Sin etapa asignada", 12).pack(anchor="w")
        Boton(ses, "Cerrar sesión", self.volver_inicio, "danger", alto=38, tam=13, icono="log-out",
              tam_icono=18).pack(fill="x", padx=14, pady=(0, 14))
        self.sw_modo = ctk.CTkSwitch(sb, text="Modo oscuro", font=fuente(13), text_color=C["btn_texto"],
                                     progress_color=C["nav_sel"], command=self.cambiar_modo)
        self.sw_modo.pack(side="bottom", anchor="w", padx=26, pady=(0, 14))
        if modo_actual() == "dark":
            self.sw_modo.select()

    # ------------------------------------------------------------ cabecera
    def _construir_topbar(self):
        top = transparente(self.content)
        top.grid(row=0, column=0, sticky="ew", padx=32, pady=(26, 10))
        top.grid_columnconfigure(0, weight=1)
        izq = transparente(top)
        izq.grid(row=0, column=0, sticky="w")
        fila_t = transparente(izq)
        fila_t.pack(anchor="w")
        self.lb_titulo = etiqueta(fila_t, "", 32, "bold")
        self.lb_titulo.pack(side="left")
        self.lb_titulo2 = etiqueta(fila_t, "", 32, "bold", C["cobalto_txt"])
        self.lb_titulo2.pack(side="left")
        self.lb_sub = tenue(izq, "", 14, justify="left", wraplength=420)
        self.lb_sub.pack(anchor="w", pady=(2, 0))
        ctk.CTkFrame(izq, width=140, height=3, corner_radius=2, fg_color=C["nav_sel"]).pack(anchor="w", pady=(10, 0))

        chip = tarjeta(top, corner_radius=16)
        chip.grid(row=0, column=1, sticky="e", padx=(16, 0))
        # El subtítulo ocupa todo el ancho libre de la cabecera (descontando la tarjeta de fecha y tasa).
        top.bind("<Configure>", lambda e: self.lb_sub.configure(wraplength=max(240, e.width - chip.winfo_reqwidth() - 48)))

        def sello(padre, nombre):
            return ctk.CTkLabel(padre, text="", image=icono(nombre, 24, C["cobalto_txt"]), width=46, height=46,
                                corner_radius=14, fg_color=C["primary_soft"])

        sello(chip, "calendar").pack(side="left", padx=(14, 10), pady=12)
        bloque = transparente(chip)
        bloque.pack(side="left", pady=10)
        tenue(bloque, "Fecha actual", 12).pack(anchor="w")
        self.lb_fecha = etiqueta(bloque, datetime.date.today().strftime("%d/%m/%Y"), 15, "bold")
        self.lb_fecha.pack(anchor="w")
        ctk.CTkFrame(chip, width=1, height=44, corner_radius=0, fg_color=C["border"]).pack(side="left", padx=16)
        sello(chip, "circle-dollar-sign").pack(side="left", padx=(0, 10), pady=12)
        tx = transparente(chip)
        tx.pack(side="left", pady=10)
        fila_b = transparente(tx)
        fila_b.pack(anchor="w")
        self.dot_tasa = ctk.CTkLabel(fila_b, text="●", font=fuente(12), text_color=C["muted"], width=14)
        self.dot_tasa.pack(side="left")
        self.lb_tasa = etiqueta(fila_b, "BCV  consultando…", 14, "bold", C["muted"])
        self.lb_tasa.pack(side="left", padx=(2, 0))
        self.lb_tasa2 = tenue(tx, "", 12)
        self.lb_tasa2.pack(anchor="w")
        icono_boton(chip, "↻", lambda: self.refrescar_tasa(), icono="refresh-cw").pack(side="left", padx=(14, 6), pady=12)
        Boton(chip, "Manual", self.dialogo_tasa_manual, "accion", ancho=76, alto=36, tam=12).pack(side="left", padx=(0, 14), pady=12)

    # ------------------------------------------------------------ RESUMEN GENERAL
    @staticmethod
    def _sello_icono(padre, nombre, lado, tam_icono, tono="primary"):
        """Cuadrado redondeado de color suave con un icono del mismo tono."""
        img = icono(nombre, tam_icono, C[tono])
        return ctk.CTkLabel(padre, text="", image=img, width=lado, height=lado, corner_radius=lado // 3 + 1,
                            fg_color=C[tono + "_soft"])

    def ui_inicio(self):
        esc = self._factor_esc()
        self._lienzos = []
        self._res, self._ventas, self._top = {}, ([], []), None
        cont = ctk.CTkScrollableFrame(self.t_home, fg_color="transparent", corner_radius=0)
        cont.pack(fill="both", expand=True)

        # ---- indicadores
        kp = transparente(cont)
        kp.pack(fill="x", pady=(0, 16))
        for i, clave in enumerate(("referencias", "unidades", "bajos", "desactivados")):
            kp.grid_columnconfigure(i, weight=1, uniform="kpi")
            lz = Lienzo(kp, partial(self._dibujar_kpi, clave, i), int(155 * esc), fondo="bg")
            lz.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 8 if i < 3 else 0))
            self._lienzos.append(lz)

        # ---- ventas recientes + pistón más vendido
        f2 = transparente(cont)
        f2.pack(fill="x", pady=(0, 16))
        f2.grid_columnconfigure(0, weight=7, uniform="f2")
        f2.grid_columnconfigure(1, weight=4, uniform="f2")
        ven = tarjeta(f2)
        ven.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cab = transparente(ven)
        cab.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(cab, text="", image=icono("chart-column", 26, C["primary"])).pack(side="left")
        etiqueta(cab, "Ventas recientes", 18, "bold").pack(side="left", padx=(10, 0))
        self.cmb_rango = Combo(cab, list(RANGOS), ancho=170, command=lambda *_a: self._cargar_ventas())
        self.cmb_rango.set("Últimos 7 días")
        self.cmb_rango.pack(side="right")
        lz = Lienzo(ven, self._dibujar_ventas, int(250 * esc))
        lz.pack(fill="both", expand=True, padx=18, pady=(4, 16))
        self._lienzos.append(lz)

        top = tarjeta(f2)
        top.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        cab = transparente(top)
        cab.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(cab, text="", image=icono("trophy", 26, C["warn"])).pack(side="left")
        etiqueta(cab, "Pistón más vendido", 18, "bold").pack(side="left", padx=(10, 0))
        cuerpo = transparente(top)
        cuerpo.pack(fill="both", expand=True, padx=20, pady=(6, 18))
        self.lb_top_img = ctk.CTkLabel(cuerpo, text="", width=124, height=124)
        self.lb_top_img.pack(side="left", padx=(0, 12))
        der = transparente(cuerpo)
        der.pack(side="left", fill="both", expand=True)
        self.lb_top_nombre = etiqueta(der, "Sin ventas todavía", 18, "bold", wraplength=150, justify="left")
        self.lb_top_nombre.pack(anchor="w", pady=(10, 0))
        self.lb_top_uni = etiqueta(der, "", 20, "bold")
        self.lb_top_uni.pack(anchor="w", pady=(2, 10))
        self.btn_top = Boton(der, "Ver detalles  →", self._ver_top, "pri", alto=42, tam=13)
        self.btn_top.pack(anchor="w", fill="x", pady=(6, 0))

        # ---- accesos rápidos + estado del inventario
        f3 = transparente(cont)
        f3.pack(fill="x")
        f3.grid_columnconfigure(0, weight=6, uniform="f3")
        f3.grid_columnconfigure(1, weight=5, uniform="f3")
        acc = tarjeta(f3)
        acc.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cab = transparente(acc)
        cab.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(cab, text="", image=icono("zap", 26, C["warn"])).pack(side="left")
        etiqueta(cab, "Accesos rápidos", 18, "bold").pack(side="left", padx=(10, 0))
        fila = transparente(acc)
        fila.pack(fill="both", expand=True, padx=16, pady=(4, 18))
        if self.es_control:
            accesos = [("existencias", "arrow-left-right", "Existencias")]
        elif self.admin:
            accesos = [("registro", "circle-plus", "Registrar pistón"), ("inventario", "boxes", "Inventario"),
                       ("facturas", "receipt-text", "Facturación"), ("usuarios", "users", "Usuarios")]
        else:        # Cajero
            accesos = [("inventario", "boxes", "Inventario"), ("ventas", "shopping-cart", "Nueva venta"),
                       ("facturas", "receipt-text", "Facturación")]
        for i, (clave, ico, texto) in enumerate(accesos):
            fila.grid_columnconfigure(i, weight=1, uniform="acc")
            self._tile_acceso(fila, ico, texto, clave).grid(row=0, column=i, sticky="nsew", padx=4)

        inv = tarjeta(f3)
        inv.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        cab = transparente(inv)
        cab.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(cab, text="", image=icono("chart-column", 26, C["warn"])).pack(side="left")
        etiqueta(cab, "Estado del inventario", 18, "bold").pack(side="left", padx=(10, 0))
        cuerpo = transparente(inv)
        cuerpo.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        lado = int(150 * esc)
        lz = Lienzo(cuerpo, self._dibujar_dona, lado, ancho=lado)
        lz.pack(side="left", padx=(0, 22))
        self._lienzos.append(lz)
        leyenda = transparente(cuerpo)
        leyenda.pack(side="left", fill="both", expand=True)
        self.lb_pct = {}
        for clave, texto, color in (("disp", "Disponible", G.AZUL), ("bajo", "Stock bajo", G.AMBAR), ("agot", "Agotado", G.ROJO)):
            fl = transparente(leyenda)
            fl.pack(fill="x", pady=6)
            ctk.CTkLabel(fl, text="●", font=fuente(16), text_color=color, width=22).pack(side="left")
            etiqueta(fl, texto, 14).pack(side="left", padx=(4, 0))
            self.lb_pct[clave] = etiqueta(fl, "0%", 14, "bold", anchor="e")
            self.lb_pct[clave].pack(side="right")

    def _tile_acceso(self, padre, glifo, texto, clave):
        t = ctk.CTkFrame(padre, fg_color=C["surface2"], corner_radius=16, border_width=1, border_color=C["btn_borde"])
        ico = ctk.CTkLabel(t, text="", image=icono(glifo, 32, C["primary"]))
        ico.pack(pady=(20, 8))
        etiqueta(t, texto, 13, "bold", anchor="center").pack(padx=8, pady=(0, 20))

        def entra(_e=None):
            t.configure(border_color=C["primary"], fg_color=C["hover"])

        def sale(_e=None):
            x, y = t.winfo_pointerxy()
            if not (t.winfo_rootx() <= x < t.winfo_rootx() + t.winfo_width()
                    and t.winfo_rooty() <= y < t.winfo_rooty() + t.winfo_height()):
                t.configure(border_color=C["btn_borde"], fg_color=C["surface2"])

        for w in (t, *t.winfo_children()):
            w.bind("<Enter>", entra)
            w.bind("<Leave>", sale)
            w.bind("<Button-1>", lambda _e, k=clave: self.mostrar_pagina(k))
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        return t

    # ------------------------------------------------------------ dibujo de los gráficos
    def _dibujar_kpi(self, clave, i, w, h):
        r, esc = self._res, self._factor_esc()
        n = lambda k: int(r.get(k, 0) or 0)
        nueva = n("nuevas")
        defs = {
            "referencias": ("Referencias", n("referencias"), "piston", G.AZUL, G.TURQUESA,
                            (f"↑ +{nueva} esta semana" if nueva else "Sin altas esta semana"), "#22C55E" if nueva else None),
            "unidades": ("Unidades en stock", n("unidades"), "package", G.AZUL, G.AZUL,
                         f"{n('vendidas')} vendidas en 7 días", "#22C55E"),
            "bajos": ("Con stock bajo", n("bajos"), "triangle-alert", G.AMBAR, G.AMBAR,
                      "Requieren reposición" if n("bajos") else "Todo en orden", G.AMBAR),
            "desactivados": ("Desactivados", n("desactivados"), "circle-x", G.ROJO, G.GRIS, "Referencias inactivas", None),
        }
        titulo, valor, ico, acento, onda, nota, nc = defs[clave]
        col = self._colores()
        return G.tarjeta_kpi(w, h, esc, col, acento, onda, titulo, valor, nota, nc or col["muted"], ico, fase=i * 1.1)

    def _dibujar_ventas(self, w, h):
        dias, valores = self._ventas
        cada = 1 if len(valores) <= 8 else (2 if len(valores) <= 16 else 5)
        return G.grafico_lineas(w, h, self._factor_esc(), self._colores(), valores, dias, cada)

    def _dibujar_dona(self, w, h):
        r = self._res
        disp = max(0, int(r.get("activos", 0) or 0) - int(r.get("poco", 0) or 0) - int(r.get("agotados", 0) or 0))
        return G.dona(min(w, h), self._factor_esc(), self._colores(),
                      [(disp, G.AZUL), (int(r.get("poco", 0) or 0), G.AMBAR), (int(r.get("agotados", 0) or 0), G.ROJO)])

    # ------------------------------------------------------------ datos
    def actualizar_kpis(self):
        """Indicadores del resumen e inventario (siempre sobre el inventario completo)."""
        try:
            s = db.consulta(SQL_RESUMEN, uno=True) or {}
        except Exception:
            return
        for k, lbl in getattr(self, "kpi_inv", {}).items():
            lbl.configure(text=str(s.get(k, 0)))
        if not hasattr(self, "_res"):
            return
        try:
            s["nuevas"] = (db.consulta("SELECT COUNT(*) AS n FROM pistones WHERE fecha_creacion >= NOW() - INTERVAL 7 DAY",
                                       uno=True) or {}).get("n", 0)
            s["vendidas"] = (db.consulta(
                "SELECT COALESCE(SUM(d.cantidad),0) AS n FROM detalle_factura d JOIN facturas f ON f.id_factura=d.id_factura "
                f"WHERE {_NO_ANULADA} AND f.fecha_hora >= CURDATE() - INTERVAL 6 DAY", uno=True) or {}).get("n", 0)
        except Exception:
            pass
        self._res = s
        activos = int(s.get("activos", 0) or 0)
        poco, agot = int(s.get("poco", 0) or 0), int(s.get("agotados", 0) or 0)
        disp = max(0, activos - poco - agot)
        for clave, v in (("disp", disp), ("bajo", poco), ("agot", agot)):
            self.lb_pct[clave].configure(text=f"{round(100 * v / activos) if activos else 0}%")
        self._cargar_ventas()
        self._cargar_top()
        self.repintar_panel()

    def _cargar_ventas(self):
        n = RANGOS.get(self.cmb_rango.get(), 7)
        hoy = datetime.date.today()
        dias = [hoy - datetime.timedelta(days=n - 1 - i) for i in range(n)]
        try:
            filas = db.consulta(
                "SELECT DATE(f.fecha_hora) AS d, COALESCE(SUM(f.total),0) AS t FROM facturas f "
                f"WHERE {_NO_ANULADA} AND f.fecha_hora >= CURDATE() - INTERVAL %s DAY GROUP BY DATE(f.fecha_hora)", (n - 1,))
        except Exception:
            filas = []
        por_dia = {(f["d"] if isinstance(f["d"], datetime.date) else datetime.date.fromisoformat(str(f["d"])[:10])): float(f["t"] or 0)
                   for f in filas}
        self._ventas = ([d.strftime("%d/%m") for d in dias], [por_dia.get(d, 0.0) for d in dias])
        self.repintar_panel()

    def _cargar_top(self):
        try:
            fila = db.consulta(
                "SELECT p.id_piston AS id, p.codigo_piston AS codigo, p.descripcion, COALESCE(p.imagen,'') AS imagen, "
                "SUM(d.cantidad) AS u FROM detalle_factura d JOIN facturas f ON f.id_factura=d.id_factura "
                f"JOIN pistones p ON p.id_piston=d.id_piston WHERE {_NO_ANULADA} "
                "GROUP BY p.id_piston, p.codigo_piston, p.descripcion, p.imagen ORDER BY u DESC LIMIT 1", uno=True)
        except Exception:
            fila = None
        self._top = fila
        if not fila:
            self.lb_top_nombre.configure(text="Sin ventas todavía")
            self.lb_top_uni.configure(text="")
            self.lb_top_img.configure(image=None, text="")
            self.btn_top.configure(state="disabled")
            return
        u = int(fila["u"] or 0)
        self.lb_top_nombre.configure(text=fila["descripcion"] or fila["codigo"])
        self.lb_top_uni.configure(text=f"{u} {'unidad' if u == 1 else 'unidades'}")
        img = _cargar_img(fila["imagen"], (124, 124)) if fila["imagen"] else None
        self._img_top = img
        self.lb_top_img.configure(image=img, text="" if img else "(sin imagen)")
        self.btn_top.configure(state="normal")

    def _ver_top(self):
        if self._top:
            self.abrir_ficha_por_id(self._top["id"])
