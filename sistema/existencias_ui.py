"""Pantalla «Existencias» (diseño «panel de producción e inventario») con seguimiento por lotes.

Estructura, de arriba abajo:
  1. Barra de acciones: nueva orden, completar paso, lotes activos/finalizados, no conformes, materia prima e Historial
     (rechazos definitivos, permanente). El rol CONTROL consulta todo pero solo modifica la etapa que tiene asignada.
  2. Cuatro tarjetas con los totales de TODOS los lotes y del inventario (no dependen del lote elegido).
  3. «Resumen del lote» elegido: pistón, orden, cantidades, fecha de inicio y etapa actual.
  4. «Seguimiento de producción»: avance del lote y los 9 pasos (clic en un paso para ver su detalle).
  5. «Detalle del paso» (resultado de calidad) y «Historial de movimientos» (del lote o del inventario general).

Las existencias ya no se mueven a mano: entran por la liberación de un lote (paso 9) y salen por Ventas.
``ExistenciasMixin`` se mezcla con la ventana principal (``App``). Los datos salen de produccion_repo.py.
"""
import tkinter as tk
from datetime import date, datetime
from functools import partial
from types import SimpleNamespace

import customtkinter as ctk

import conexion as db
import panel_graficos as G
import produccion_repo as prod
from estilos import C, _c, fuente
from iconos import icono
from panel_ui import Lienzo
from ui import (Boton, Combo, Contador, Dialogo, campo, etiqueta, tenue, tarjeta, transparente, tabla, tags_fila,
                titulo_seccion, limitar_decimal, messagebox, icono_boton, toast)

VIOLETA = "#8B5CF6"
VERDE = "#22C55E"
ESTADO_TXT = prod.ESTADO_TXT
ESTADO_CHIP = {"PENDIENTE": "Pendiente", "EN_PROCESO": "En proceso", "COMPLETADO": "Completado",
               "COMPLETADO_OBS": "Con observaciones", "BLOQUEADO": "Bloqueado"}
TONO = {"COMPLETADO": ("ok_soft", "ok"), "COMPLETADO_OBS": ("warn_soft", "warn"), "EN_PROCESO": ("primary_soft", "cobalto_txt"),
        "BLOQUEADO": ("danger_soft", "danger"), "PENDIENTE": ("surface2", "muted")}
FMT_FH = "%d/%m/%Y %H:%M"
MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")

COLS_LOTE = (("fecha", "Fecha", 130, "w"), ("mov", "Movimiento", 230, "w"), ("cant", "Cantidad", 120, "center"),
             ("estado", "Estado", 100, "center"), ("usuario", "Usuario", 90, "w"), ("obs", "Observaciones", 240, "w"))
COLS_INV = (("fecha", "FECHA", 130, "w"), ("codigo", "CÓDIGO", 115, "w"), ("tipo", "TIPO", 100, "center"),
            ("cant", "CANT.", 60, "center"), ("ant", "ANT.", 55, "center"), ("nuevo", "NUEVO", 60, "center"),
            ("lote", "LOTE", 75, "w"), ("motivo", "MOTIVO", 230, "w"), ("factura", "FACTURA", 90, "w"))


# ----------------------------------------------------------------------------- utilidades puras
def _kg(v):
    v = float(v or 0)
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha_hora(v):
    return v.strftime(FMT_FH) if hasattr(v, "strftime") else str(v or "")


def _fecha(v):
    return v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else (str(v) if v else "—")


def _decimal(txt):
    return float(str(txt).strip().replace(",", ".") or 0)


def _entero(txt, rotulo="La cantidad"):
    try:
        v = int(str(txt).strip() or 0)
    except ValueError:
        raise ValueError(f"{rotulo} debe ser un número entero.")
    if v < 0:
        raise ValueError(f"{rotulo} no puede ser negativa.")
    return v


def parse_fecha_hora(txt):
    """«dd/mm/aaaa hh:mm» (o solo la fecha) -> datetime. Lanza ValueError con un mensaje claro."""
    txt = (txt or "").strip()
    for fmt in (FMT_FH, "%d/%m/%Y"):
        try:
            return datetime.strptime(txt, fmt)
        except ValueError:
            continue
    raise ValueError("Escriba la fecha y hora como dd/mm/aaaa hh:mm (ejemplo: 21/11/2026 14:30).")


def _etapas_vacias():
    return [{"paso": p, "estado": "PENDIENTE", "fecha": None, "aprobados": 0, "rechazados": 0, "pendientes": 0,
             "pend_aprobados": 0, "pend_rechazados": 0, "motivo": None, "defectos": None, "observaciones": None,
             "cant_recibida": None, "cant_procesada": None, "responsable": None, "fecha_hora": None, "bloqueo": None}
            for p in range(1, prod.ULTIMO_PASO + 1)]


def _modelo(o):
    if not o:
        return "—"
    return f"{o.get('codigo') or '—'} · {o.get('modelo') or ''}".strip(" ·")


class ExistenciasMixin:
    # ------------------------------------------------------------------ construcción
    def ui_existencias(self):
        esc = self._exi_esc = self._factor_esc()
        if not hasattr(self, "_lienzos"):
            self._lienzos = []
        self._exi = SimpleNamespace(res={}, orden=None, id_sel=None, activas=[], etapas=_etapas_vacias(), sel=1,
                                    modo="lote", cols={}, resumen=prod.resumen_lote(None, []))
        cont = ctk.CTkScrollableFrame(self.t_exi, fg_color="transparent", corner_radius=0)
        cont.pack(fill="both", expand=True)

        # ---- 1. acciones (ya no hay entradas, salidas ni ajustes manuales)
        barra = transparente(cont)
        barra.pack(fill="x", pady=(0, 12))
        if self.gestion_stock:
            Boton(barra, "Nueva orden", self.dialogo_orden, "pri", ancho=134, alto=36, tam=12, icono="plus").pack(side="left", padx=(0, 6))
        if self.gestion_stock or self.es_control:
            Boton(barra, "Completar paso", self.dialogo_completar_paso, "accion", ancho=148, alto=36, tam=12, icono="check").pack(side="left", padx=(0 if self.es_control else 3, 3))
            ctk.CTkFrame(barra, width=1, height=24, corner_radius=0, fg_color=C["border"]).pack(side="left", padx=8)
        self.btn_activos = Boton(barra, "Lotes activos", self.dialogo_lotes, "accion", ancho=140, alto=36, tam=12, icono="factory")
        self.btn_activos.pack(side="left", padx=3)
        Boton(barra, "Finalizados", lambda: self.dialogo_lotes(True), "accion", ancho=116, alto=36, tam=12, icono="list").pack(side="left", padx=3)
        Boton(barra, "No conformes", self.dialogo_no_conformes, "accion", ancho=130, alto=36, tam=12, icono="triangle-alert").pack(side="left", padx=3)
        if self.gestion_stock:
            Boton(barra, "Materia prima", self.dialogo_materia_prima, "accion", ancho=130, alto=36, tam=12, icono="boxes").pack(side="left", padx=3)
        # Historial (sustituye al antiguo «Precio USD», que ahora vive en Inventario): rechazos definitivos, visible para todos los roles.
        icono_boton(barra, "Historial", self.dialogo_historial, lado=36, icono="history").pack(side="left", padx=3)

        # Aviso del rol CONTROL: qué etapa puede modificar (el resto es solo consulta).
        self.lb_exi_control = None
        if self.es_control:
            aviso = ctk.CTkFrame(cont, corner_radius=10, fg_color=C["primary_soft"], border_width=1, border_color=C["primary"])
            aviso.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(aviso, text="", image=icono("clipboard-list", 22, C["cobalto_txt"])).pack(side="left", padx=(14, 8), pady=10)
            self.lb_exi_control = etiqueta(aviso, "", 13, "bold", C["cobalto_txt"], wraplength=1000, justify="left")
            self.lb_exi_control.pack(side="left", padx=(0, 14), pady=10)
            self._exi_texto_control()

        # ---- 2. tarjetas (totales generales)
        kp = transparente(cont)
        kp.pack(fill="x", pady=(0, 14))
        self._exi_kpis = []
        for i in range(4):
            kp.grid_columnconfigure(i, weight=1, uniform="exi_kpi")
            lz = Lienzo(kp, partial(self._dibujar_kpi_exi, i), int(118 * esc), fondo="bg")
            lz.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 7, 7 if i < 3 else 0))
            self._lienzos.append(lz)
            self._exi_kpis.append(lz)

        # ---- 3. resumen del lote seleccionado
        rsm = tarjeta(cont)
        rsm.pack(fill="x", pady=(0, 14))
        cab = transparente(rsm)
        cab.pack(fill="x", padx=22, pady=(14, 4))
        ctk.CTkLabel(cab, text="", image=icono("package", 26, C["primary"])).pack(side="left")
        self.lb_exi_lote = etiqueta(cab, "Sin lote seleccionado", 17, "bold")
        self.lb_exi_lote.pack(side="left", padx=(10, 10))
        self.chip_lote = ctk.CTkLabel(cab, text="", font=fuente(11, "bold"), corner_radius=20, height=24, width=110,
                                      fg_color=C["surface2"], text_color=C["muted"])
        self.chip_lote.pack(side="left")
        self.lb_exi_resp = tenue(cab, "", 12, anchor="e")
        self.lb_exi_resp.pack(side="right")
        grid = transparente(rsm)
        grid.pack(fill="x", padx=22, pady=(4, 16))
        self._exi_celdas = {}
        rotulos = (("pis", "Pistón (código y modelo)"), ("ord", "Orden de producción"), ("ini", "Cantidad inicial"),
                   ("fec", "Fecha de inicio"), ("apr", "Cantidad aprobada"), ("rec", "Cantidad rechazada"),
                   ("pen", "Cantidad pendiente"), ("eta", "Etapa actual"))
        for i, (clave, texto) in enumerate(rotulos):
            fila, col = divmod(i, 4)
            grid.grid_columnconfigure(col, weight=1, uniform="exi_rs")
            celda = transparente(grid)
            celda.grid(row=fila, column=col, sticky="w", padx=(0, 12), pady=(0, 8))
            tenue(celda, texto, 12).pack(anchor="w")
            v = etiqueta(celda, "—", 14, "bold", wraplength=250, justify="left")
            v.pack(anchor="w")
            self._exi_celdas[clave] = v

        # ---- 4. seguimiento de producción
        trk = tarjeta(cont)
        trk.pack(fill="x", pady=(0, 14))
        cab = transparente(trk)
        cab.pack(fill="x", padx=22, pady=(16, 0))
        ctk.CTkLabel(cab, text="", image=icono("factory", 28, C["primary"])).pack(side="left")
        self.lb_exi_titulo = etiqueta(cab, "Seguimiento de Producción", 18, "bold")
        self.lb_exi_titulo.pack(side="left", padx=(10, 0))
        self.lb_exi_pct = etiqueta(cab, "0%", 17, "bold", anchor="e")
        self.lb_exi_pct.pack(side="right")
        self.pb_exi = ctk.CTkProgressBar(cab, width=300, height=12, corner_radius=6, fg_color=C["surface2"],
                                         progress_color=C["primary"])
        self.pb_exi.set(0)
        self.pb_exi.pack(side="right", padx=14)

        self._cv_pasos = tk.Canvas(trk, height=int(60 * esc), highlightthickness=0, bd=0, bg=_c("surface"))
        self._cv_pasos.pack(fill="x", padx=14, pady=(12, 0))
        self._cv_pasos.bind("<Configure>", lambda _e: self._exi_dibujar_pasos())
        fp = transparente(trk)
        fp.pack(fill="x", padx=14, pady=(0, 16))
        for i in range(prod.ULTIMO_PASO):
            fp.grid_columnconfigure(i, weight=1, uniform="exi_paso")
            self._exi_columna(fp, i + 1)
        fp.bind("<Configure>", lambda e: self._exi_ajustar_texto(e.width))

        # ---- 5. detalle + historial
        f4 = transparente(cont)
        f4.pack(fill="both", expand=True)
        f4.grid_columnconfigure(0, weight=4, uniform="exi_f4")
        f4.grid_columnconfigure(1, weight=7, uniform="exi_f4")
        det = tarjeta(f4)
        det.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._exi_det_cab = transparente(det)
        self._exi_det_cab.pack(fill="x", padx=20, pady=(16, 6))
        ctk.CTkLabel(self._exi_det_cab, text="", image=icono("clipboard-list", 26, C["primary"])).pack(side="left")
        self.lb_exi_det = etiqueta(self._exi_det_cab, "Detalle del paso", 16, "bold", wraplength=300, justify="left")
        self.lb_exi_det.pack(side="left", padx=(10, 0))
        self._exi_det = transparente(det)
        self._exi_det.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        his = tarjeta(f4)
        his.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        cab = transparente(his)
        cab.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(cab, text="", image=icono("list", 26, C["primary"])).pack(side="left")
        self.lb_exi_his = etiqueta(cab, "Historial de Movimientos del Lote", 16, "bold")
        self.lb_exi_his.pack(side="left", padx=(10, 0))
        sel = transparente(cab)
        sel.pack(side="right")
        self.btn_hist = {}
        for clave, texto in (("lote", "Lote"), ("inventario", "Inventario")):
            b = Boton(sel, texto, partial(self._exi_cambiar_modo, clave), "accion", ancho=96, alto=30, tam=12)
            b.pack(side="left", padx=2)
            self.btn_hist[clave] = b
        self.btn_hist["lote"].seleccionar(True)
        cols = [c[0] for c in COLS_LOTE]
        marco, self.tv_mov = tabla(his, cols, {c[0]: c[1] for c in COLS_LOTE}, [c[2] for c in COLS_LOTE],
                                   {c[0]: c[3] for c in COLS_LOTE}, fg_color="transparent", border_width=0)
        marco.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.tv_mov.configure(height=9)

        self._lienzos.append(SimpleNamespace(redibujar=self._exi_repintar))
        self._exi_detalle()

    def _exi_columna(self, padre, paso):
        """Una columna del seguimiento: nombre, fecha, estado y (si hay piezas) el resumen de aprobados/errores."""
        col = transparente(padre)
        col.grid(row=0, column=paso - 1, sticky="n", padx=2)
        nombre = etiqueta(col, f"{paso}. {prod.PASOS[paso - 1]}", 13, "normal", justify="center", anchor="center", wraplength=110,
                          height=int(58 * self._exi_esc))
        nombre.pack(pady=(2, 4))
        fecha = tenue(col, " ", 12, anchor="center")
        fecha.pack(pady=(0, 6))
        chip = ctk.CTkLabel(col, text="Pendiente", font=fuente(11, "bold"), corner_radius=20, height=24, width=104,
                            fg_color=C["surface2"], text_color=C["muted"])
        chip.pack()
        mini = ctk.CTkFrame(col, corner_radius=8, border_width=1, fg_color=C["surface2"], border_color=C["border"])
        mini_ok = etiqueta(mini, "", 12, "bold", C["ok"], anchor="center")
        mini_ok.pack(padx=8, pady=(5, 0))
        mini_err = etiqueta(mini, "", 12, "bold", C["danger"], anchor="center")
        mini_err.pack(padx=8)
        mini_pen = etiqueta(mini, "", 12, "bold", C["warn"], anchor="center")
        mini_pen.pack(padx=8)
        etiqueta(mini, "Ver detalle ⌄", 11, "normal", C["cobalto_txt"], anchor="center").pack(padx=8, pady=(0, 5))
        self._exi.cols[paso] = SimpleNamespace(nombre=nombre, fecha=fecha, chip=chip, mini=mini, ok=mini_ok, err=mini_err, pen=mini_pen)
        self._exi_enlazar(col, paso)

    def _exi_enlazar(self, w, paso):
        w.bind("<Button-1>", lambda _e, p=paso: self._exi_elegir(p), add="+")
        for h in w.winfo_children():
            self._exi_enlazar(h, paso)

    def _exi_ajustar_texto(self, ancho):
        ancho_col = max(80, int(ancho / prod.ULTIMO_PASO) - 14)
        for c in self._exi.cols.values():
            c.nombre.configure(wraplength=ancho_col)

    # ------------------------------------------------------------------ tarjetas (totales de todos los lotes)
    def _dibujar_kpi_exi(self, i, w, h):
        r = self._exi.res
        n = lambda k: int(r.get(k, 0) or 0)
        esc, col = self._factor_esc(), self._colores()
        if i == 0:
            return G.tarjeta_existencia(w, h, esc, col, G.AZUL, "Materia Prima", f"{_kg(r.get('mp_kg', 0))} kg",
                                        "Aluminio disponible", "boxes")
        if i == 1:
            return G.tarjeta_existencia(w, h, esc, col, VERDE, "Pistones Aprobados", str(n("aprobados")),
                                        "Productos terminados", "piston")
        if i == 2:
            return G.tarjeta_existencia(w, h, esc, col, G.AMBAR, "En Revisión / Rechazo", "", "", "triangle-alert",
                                        dual=(("Por evaluar", n("pendientes"), G.AMBAR), ("Rechazados", n("rechazados"), G.ROJO)))
        return G.tarjeta_existencia(w, h, esc, col, VIOLETA, "Órdenes Activas", str(n("activas")), "En producción", "factory")

    # ------------------------------------------------------------------ carga de datos
    def cargar_movimientos(self):
        """Refresca toda la pantalla (al entrar y tras cada operación). Conserva el lote elegido."""
        if not hasattr(self, "_exi"):
            return
        x = self._exi
        self._refrescar_permisos()
        try:
            x.res = prod.resumen()
            x.activas = prod.ordenes_activas()
            if x.id_sel is not None:
                x.orden = prod.orden(x.id_sel)
            if x.orden is None:                      # primera vez, o el lote elegido ya no existe: primer lote activo
                x.orden = x.activas[0] if x.activas else None
                x.id_sel = x.orden["id_orden"] if x.orden else None
        except Exception as ex:
            return messagebox.showerror("Existencias", f"No se pudieron cargar los datos.\n\n{ex}", parent=self)
        self.btn_activos.configure(text=f"Lotes activos ({len(x.activas)})")
        self._exi_cargar_orden(reiniciar_paso=False)
        for lz in self._exi_kpis:
            lz.redibujar()

    def _exi_seleccionar_lote(self, id_orden):
        """Cambia TODA la pantalla al lote indicado (otras órdenes no se mezclan)."""
        self._exi.id_sel = id_orden
        self._exi.orden = prod.orden(id_orden)
        self._exi_cargar_orden(reiniciar_paso=True)

    def _exi_cargar_orden(self, reiniciar_paso=True):
        x = self._exi
        o = x.orden
        try:
            x.etapas = prod.etapas(o["id_orden"]) if o else []
        except Exception as ex:
            x.etapas = []
            messagebox.showerror("Existencias", f"No se pudo cargar la orden.\n\n{ex}", parent=self)
        if not x.etapas:
            x.etapas = _etapas_vacias()
        try:
            recuperadas = prod.recuperadas_lote(o["id_orden"]) if o else 0
        except Exception:
            recuperadas = 0
        x.resumen = prod.resumen_lote(o, x.etapas, recuperadas)
        if reiniciar_paso or not (1 <= x.sel <= prod.ULTIMO_PASO):
            x.sel = int(o["paso_actual"]) if o else 1
        self.pb_exi.set(x.resumen["pct"] / 100)
        self.lb_exi_pct.configure(text=f"{x.resumen['pct']}%")
        self.lb_exi_titulo.configure(text=(f"Seguimiento de Producción - Lote: {o['lote']}  |  Orden: {o['codigo_orden']}"
                                           if o else "Seguimiento de Producción"))
        self._exi_pintar_resumen()
        self._exi_pintar_columnas()
        self._exi_dibujar_pasos()
        self._exi_detalle()
        self._exi_llenar_hist()

    def _exi_pintar_resumen(self):
        x, o, r = self._exi, self._exi.orden, self._exi.resumen
        c = self._exi_celdas
        if not o:
            self.lb_exi_lote.configure(text="Sin lote seleccionado")
            self.chip_lote.configure(text="", fg_color=C["surface2"])
            self.lb_exi_resp.configure(text="Cree una orden con «Nueva orden» o elija un lote en «Lotes activos».")
            for v in c.values():
                v.configure(text="—", text_color=C["text"])
            return
        activa = o["estado"] == "EN_PRODUCCION"
        self.lb_exi_lote.configure(text=f"Lote {o['lote']}")
        self.chip_lote.configure(text="En producción" if activa else "Finalizado",
                                 fg_color=C["primary_soft"] if activa else C["ok_soft"],
                                 text_color=C["cobalto_txt"] if activa else C["ok"])
        resp = o.get("responsable")
        self.lb_exi_resp.configure(text=f"Responsable: {resp}" if resp else "")
        c["pis"].configure(text=_modelo(o))
        c["ord"].configure(text=o["codigo_orden"])
        c["ini"].configure(text=f"{int(o['cantidad_plan'])} pistones")
        c["fec"].configure(text=_fecha(o.get("fecha_inicio") or o.get("creada")))
        c["apr"].configure(text=str(r["aprobadas"]), text_color=C["ok"])
        c["rec"].configure(text=str(r["rechazadas"]), text_color=C["danger"] if r["rechazadas"] else C["text"])
        c["pen"].configure(text=str(r["pendientes"]), text_color=C["warn"] if r["pendientes"] else C["text"])
        if activa:
            paso = r["paso"]
            c["eta"].configure(text=f"Paso {paso} de {prod.ULTIMO_PASO}: {prod.PASOS[paso - 1]} ({ESTADO_TXT[r['estado_paso']]})")
        else:
            c["eta"].configure(text="Finalizado" + (f" · {o['motivo_cierre']}" if o.get("motivo_cierre") else ""))

    def _exi_pintar_columnas(self):
        for e in self._exi.etapas:
            c = self._exi.cols[e["paso"]]
            est = e["estado"]
            fondo, color = TONO[est]
            c.chip.configure(text=ESTADO_CHIP[est], fg_color=C[fondo], text_color=C[color])
            c.fecha.configure(text=e["fecha"].strftime("%d/%m") if e["fecha"] else " ")
            if est in prod.ESTADOS_COMPLETOS and e["paso"] >= prod.PRIMER_PASO_PIEZAS:
                rech, pen = int(e["rechazados"] or 0), prod.pendiente_vigente(e)
                c.ok.configure(text=f"{int(e['aprobados'] or 0)} Aprobados")
                c.err.configure(text=f"{rech} Errores" if rech else "")
                c.pen.configure(text=f"{pen} Pendientes" if pen else "")
                c.mini.configure(fg_color=C["danger_soft"] if rech else C["surface2"],
                                 border_color=C["danger_borde"] if rech else C["border"])
                c.mini.pack(pady=(8, 0))
            else:
                c.mini.pack_forget()

    # ------------------------------------------------------------------ pasos (círculos y línea)
    def _exi_dibujar_pasos(self):
        cv = self._cv_pasos
        cv.delete("all")
        cv.configure(bg=_c("surface"))
        W, H = cv.winfo_width(), cv.winfo_height()
        if W < 50 or len(self._exi.etapas) < prod.ULTIMO_PASO:
            return
        esc, x = self._exi_esc, self._exi
        n = prod.ULTIMO_PASO
        radio = 19 * esc
        cy = H / 2
        xs = [(i + 0.5) * W / n for i in range(n)]
        verde, azul, gris = _c("ok"), _c("primary"), _c("btn_borde")
        ambar, rojo = _c("warn"), _c("danger")
        for i in range(n - 1):
            hecho = x.etapas[i]["estado"] in prod.ESTADOS_COMPLETOS
            cv.create_line(xs[i] + radio, cy, xs[i + 1] - radio, cy, width=max(2, int(3 * esc)), fill=verde if hecho else gris)
        for i, e in enumerate(x.etapas):
            paso, cx, est = e["paso"], xs[i], e["estado"]
            tag = f"p{paso}"
            if x.sel == paso and est != "EN_PROCESO":
                cv.create_oval(cx - radio - 5 * esc, cy - radio - 5 * esc, cx + radio + 5 * esc, cy + radio + 5 * esc,
                               outline=_c("primary_h"), width=2, tags=tag)
            if est in prod.ESTADOS_COMPLETOS:
                relleno = verde if est == "COMPLETADO" else ambar
                cv.create_oval(cx - radio, cy - radio, cx + radio, cy + radio, fill=relleno, outline=relleno, tags=tag)
                k = radio
                cv.create_line(cx - 0.45 * k, cy + 0.02 * k, cx - 0.1 * k, cy + 0.38 * k, cx + 0.5 * k, cy - 0.34 * k,
                               fill="#FFFFFF", width=max(3, int(3.4 * esc)), capstyle="round", joinstyle="round", tags=tag)
            elif est == "BLOQUEADO":
                cv.create_oval(cx - radio - 5 * esc, cy - radio - 5 * esc, cx + radio + 5 * esc, cy + radio + 5 * esc,
                               outline=_c("danger_soft"), width=max(2, int(3 * esc)), tags=tag)
                cv.create_oval(cx - radio, cy - radio, cx + radio, cy + radio, fill=rojo, outline=rojo, tags=tag)
                cv.create_text(cx, cy, text="!", fill="#FFFFFF", font=fuente(16, "bold"), tags=tag)
            elif est == "EN_PROCESO":
                cv.create_oval(cx - radio - 5 * esc, cy - radio - 5 * esc, cx + radio + 5 * esc, cy + radio + 5 * esc,
                               outline=_c("primary_soft"), width=max(2, int(3 * esc)), tags=tag)
                cv.create_oval(cx - radio, cy - radio, cx + radio, cy + radio, fill=_c("surface"), outline=azul,
                               width=max(3, int(3 * esc)), tags=tag)
                cv.create_text(cx, cy, text=str(paso), fill=_c("text"), font=fuente(15, "bold"), tags=tag)
            else:
                cv.create_oval(cx - radio, cy - radio, cx + radio, cy + radio, fill=_c("surface"), outline=gris,
                               width=max(2, int(2 * esc)), tags=tag)
                cv.create_text(cx, cy, text=str(paso), fill=_c("muted"), font=fuente(14, "bold"), tags=tag)
            cv.tag_bind(tag, "<Button-1>", lambda _e, p=paso: self._exi_elegir(p))

    def _exi_elegir(self, paso):
        self._exi.sel = paso
        self._exi_dibujar_pasos()
        self._exi_detalle()

    def _exi_repintar(self):
        if hasattr(self, "_cv_pasos"):
            self._exi_dibujar_pasos()

    # ------------------------------------------------------------------ detalle del paso (resultado de calidad)
    def _exi_detalle(self):
        x = self._exi
        for w in self._exi_det.winfo_children():
            w.destroy()
        paso = x.sel
        e = next((t for t in x.etapas if t["paso"] == paso), None)
        self.lb_exi_det.configure(text=f"Detalle del Paso {paso}: {prod.PASOS[paso - 1]}")
        if e is None:
            return
        est = e["estado"]
        o = x.orden
        rech, aprob, pen = int(e["rechazados"] or 0), int(e["aprobados"] or 0), prod.pendiente_vigente(e)
        hecho = est in prod.ESTADOS_COMPLETOS
        if not o:
            texto, fondo, color, ico = "Aún no hay lotes. Cree uno con «Nueva orden».", "surface2", "muted", "circle-help"
        elif est == "BLOQUEADO":
            texto, fondo, color, ico = f"Paso bloqueado: {e['bloqueo'] or 'incidencia sin descripción'}", "danger_soft", "danger", "ban"
        elif rech > 0 and hecho:
            texto, fondo, color, ico = (f"Se presentaron {rech} pieza{'s' if rech != 1 else ''} con defectos",
                                        "danger_soft", "danger", "triangle-alert")
        elif est == "COMPLETADO_OBS":
            texto, fondo, color, ico = "Paso completado con observaciones", "warn_soft", "warn", "triangle-alert"
        elif est == "COMPLETADO":
            texto, fondo, color, ico = "Paso completado sin defectos", "ok_soft", "ok", "check"
        elif est == "EN_PROCESO":
            texto, fondo, color, ico = "Paso en proceso", "primary_soft", "cobalto_txt", "zap"
        else:
            texto, fondo, color, ico = "Paso pendiente", "surface2", "muted", "calendar"
        ban = ctk.CTkFrame(self._exi_det, corner_radius=8, fg_color=C[fondo], border_width=1,
                           border_color=C["danger_borde"] if fondo == "danger_soft" else C[fondo])
        ban.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(ban, text="", image=icono(ico, 22, C[color])).pack(side="left", padx=(12, 8), pady=10)
        etiqueta(ban, texto, 13, "bold", C[color], wraplength=300, justify="left").pack(side="left", pady=10, padx=(0, 10))

        contador = [0]

        def fila(rotulo, valor, color_valor=None):
            f = ctk.CTkFrame(self._exi_det, corner_radius=6, fg_color=C["surface2"] if contador[0] % 2 == 0 else "transparent")
            contador[0] += 1
            f.pack(fill="x", pady=1)
            etiqueta(f, rotulo, 13).pack(side="left", padx=(10, 6), pady=5)
            etiqueta(f, valor, 13, "bold" if color_valor else "normal", color_valor, anchor="e", wraplength=230,
                     justify="right").pack(side="right", padx=(6, 10), pady=5)

        dato = lambda v: "—" if v in (None, "") else str(v)
        if paso >= prod.PRIMER_PASO_PIEZAS:
            if e.get("cant_recibida") is not None:
                recibidas = e["cant_recibida"]
            elif o and not hecho and est in ("EN_PROCESO", "BLOQUEADO"):
                recibidas = prod.piezas_recibidas(x.etapas, o["cantidad_plan"], paso)
            else:
                recibidas = None
            fila("Recibidas de la etapa anterior:", dato(recibidas))
            fila("Procesadas:", dato(e.get("cant_procesada")))
            fila("Aprobadas:", str(aprob) if hecho else "—", C["ok"] if hecho else None)
            fila("Rechazadas:", str(rech) if hecho else "—", C["danger"] if rech else None)
            fila("Pendientes de evaluación:", str(pen) if hecho else "—", C["warn"] if pen else None)
            fila("Motivo del rechazo:", dato(e["motivo"]))
            fila("Defectos encontrados:", dato(e.get("defectos")))
        else:
            fila("Resultado:", ESTADO_TXT[est])
        fila("Observaciones:", dato(e["observaciones"]))
        fila("Responsable:", dato(e.get("responsable")))
        fila("Fecha y hora:", _fecha_hora(e.get("fecha_hora")) if e.get("fecha_hora") else _fecha(e["fecha"]))

        activa = bool(o) and o["estado"] == "EN_PRODUCCION"
        es_actual = activa and paso == int(o["paso_actual"])
        puede = self._puede_paso(paso)            # Administrador: cualquiera; CONTROL: solo su etapa
        if puede and es_actual and est == "EN_PROCESO":
            Boton(self._exi_det, "Completar este paso", self.dialogo_completar_paso, "pri", alto=38, icono="check").pack(fill="x", pady=(12, 0))
            Boton(self._exi_det, "Bloquear por incidencia", self.dialogo_bloquear, "accion", alto=36, icono="ban").pack(fill="x", pady=(8, 0))
        elif puede and es_actual and est == "BLOQUEADO":
            Boton(self._exi_det, "Desbloquear paso", self._desbloquear, "pri", alto=38, icono="check").pack(fill="x", pady=(12, 0))
        if self.es_control and not puede:
            tenue(self._exi_det, f"Solo consulta: este paso corresponde a otro responsable. Su etapa es el paso {self._etapa_control() or '—'}.",
                  12, wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))
        elif self.es_control and o and not es_actual and not hecho and activa:
            tenue(self._exi_det, "Aún no es su turno: el lote todavía no llegó a este paso.", 12, wraplength=300,
                  justify="left").pack(anchor="w", pady=(10, 0))
        if puede and o and pen > 0:
            Boton(self._exi_det, "Evaluar piezas pendientes", self.dialogo_pendientes, "accion", alto=36,
                  icono="clipboard-list").pack(fill="x", pady=(8, 0))
        Boton(self._exi_det, "Ver trazabilidad y control de calidad", self._trazabilidad, "accion", alto=38,
              icono="file-text").pack(fill="x", pady=(8, 0) if o else (12, 0))

    # ------------------------------------------------------------------ historial
    def _exi_cambiar_modo(self, modo):
        self._exi.modo = modo
        for clave, b in self.btn_hist.items():
            b.seleccionar(clave == modo)
        self.lb_exi_his.configure(text="Historial de Movimientos del Lote" if self._exi.modo == "lote"
                                  else "Historial de Movimientos de Inventario")
        cols = COLS_LOTE if self._exi.modo == "lote" else COLS_INV
        tv = self.tv_mov
        tv.delete(*tv.get_children())
        tv.configure(columns=[c[0] for c in cols])
        for clave, texto, ancho, ancla in cols:
            tv.heading(clave, text=texto, anchor=ancla)
            tv.column(clave, width=ancho, minwidth=60, anchor=ancla, stretch=True)
        self._exi_llenar_hist()

    def _exi_llenar_hist(self):
        tv, x = self.tv_mov, self._exi
        tv.delete(*tv.get_children())
        try:
            if x.modo == "lote":
                filas = prod.historial(x.orden["id_orden"]) if x.orden else []
                for i, h in enumerate(filas):
                    tv.insert("", "end", tags=tags_fila(i), values=(
                        _fecha_hora(h["fecha_hora"]), h["movimiento"], h["cantidad"] or "—", h["estado"] or "—",
                        h["usuario"] or "—", h["observaciones"] or ""))
            else:
                for i, m in enumerate(prod.movimientos_inventario()):
                    tv.insert("", "end", tags=tags_fila(i), values=(
                        _fecha_hora(m["fecha_hora"]), m["codigo"], m["tipo"], m["cantidad"], m["stock_anterior"],
                        m["stock_nuevo"], m.get("lote") or "—", m["motivo"], m.get("numero") or "—"))
        except Exception as ex:
            messagebox.showerror("Existencias", f"No se pudo cargar el historial.\n\n{ex}", parent=self)

    # ------------------------------------------------------------------ utilidades de diálogos
    def _exi_permiso(self, texto):
        if not self.gestion_stock:
            messagebox.showwarning("Permiso denegado", texto, parent=self)
            return False
        return True

    def _etapa_control(self):
        """Etapa (1-9) asignada al usuario CONTROL, o None."""
        e = self.user.get("etapa")
        return int(e) if e and 1 <= int(e) <= prod.ULTIMO_PASO else None

    def _puede_paso(self, paso):
        """¿Puede el usuario actual registrar o modificar ese paso? (misma regla que valida el servidor de datos)."""
        return prod.puede_modificar_paso(self.user["rol"], self.user.get("etapa"), paso)

    def _exi_permiso_paso(self, paso, texto="No tiene permiso para modificar la producción."):
        """Avisa y devuelve False si el usuario no puede modificar ese paso."""
        motivo = prod.motivo_sin_permiso(self.user["rol"], self.user.get("etapa"), paso)
        if motivo:
            messagebox.showwarning("Permiso denegado", motivo if self.es_control else texto, parent=self)
            return False
        return True

    def _exi_texto_control(self):
        if not self.lb_exi_control:
            return
        e = self._etapa_control()
        if e is None:
            self.lb_exi_control.configure(text="Usuario CONTROL sin etapa asignada: puede consultar toda la producción, "
                                               "pero no modificar ninguna etapa. Solicite la asignación al administrador.")
        else:
            self.lb_exi_control.configure(text=f"{prod.nombre_control(e)}  ·  Puede consultar los lotes y sus nueve etapas, "
                                               f"pero solo registrar, completar o modificar el paso {e}.")

    def _refrescar_permisos(self):
        """Relee la etapa asignada (el administrador pudo cambiarla durante la sesión)."""
        if not self.es_control:
            return
        try:
            fila = db.consulta(db.SQL_USUARIO + " WHERE u.id_usuario=%s", (self.user["id"],), uno=True)
            if fila:
                self.user["etapa"] = fila["etapa"]
        except Exception:
            pass
        self._exi_texto_control()

    def _exi_rotulo(self, card, texto, arriba=12):
        etiqueta(card, texto, 12, "bold", C["muted"]).pack(anchor="w", pady=(arriba, 0))

    def _exi_nombre_usuario(self):
        return str(self.user.get("nombre") or self.user.get("usuario") or "")

    def _exi_tras_cambio(self, id_sel=None):
        """Refresca la pantalla y el inventario después de una operación."""
        if id_sel is not None:
            self._exi.id_sel = id_sel
        self.cargar_movimientos()
        if hasattr(self, "cargar_inv"):
            self.cargar_inv()

    # ------------------------------------------------------------------ lotes activos / finalizados
    def dialogo_lotes(self, finalizados=False):
        """Lista de lotes en producción (o del historial de órdenes finalizadas). Al elegir uno, la pantalla cambia a ese lote."""
        try:
            filas = prod.ordenes_finalizadas() if finalizados else prod.ordenes_activas()
        except Exception as ex:
            return messagebox.showerror("Lotes", f"No se pudo cargar la lista.\n\n{ex}", parent=self)
        titulo = "Órdenes finalizadas" if finalizados else "Lotes activos"
        d = Dialogo(self, titulo, 980 if finalizados else 880, 520)
        card = d.cuerpo(22)
        titulo_seccion(card, titulo).pack(anchor="w")
        tenue(card, "Haga doble clic en un lote (o use «Ver lote») para mostrarlo en la pantalla principal." if not finalizados
              else "Historial conservado: cada lote mantiene sus etapas, resultados y movimientos. Doble clic para consultarlo.", 12).pack(anchor="w", pady=(2, 8))
        if finalizados:
            cols = ("lote", "modelo", "inicio", "fin", "incorp", "rech", "cierre")
            enc = {"lote": "LOTE", "modelo": "PISTÓN / MODELO", "inicio": "INICIO", "fin": "FINALIZACIÓN",
                   "incorp": "AL ALMACÉN", "rech": "RECHAZADAS", "cierre": "CIERRE"}
            anchos, anclas = (80, 220, 90, 120, 90, 90, 220), {"incorp": "center", "rech": "center"}
        else:
            cols = ("lote", "modelo", "paso", "estado", "inicio", "inicial")
            enc = {"lote": "LOTE", "modelo": "PISTÓN / MODELO", "paso": "AVANCE", "estado": "ESTADO",
                   "inicio": "INICIO", "inicial": "CANT. INICIAL"}
            anchos, anclas = (90, 260, 130, 130, 100, 100), {"inicial": "center"}
        marco, tv = tabla(card, cols, enc, anchos, anclas)
        marco.pack(fill="both", expand=True)
        nc_por_orden = {}
        if finalizados:
            try:
                for n in prod.no_conformes():
                    nc_por_orden[n["id_orden"]] = nc_por_orden.get(n["id_orden"], 0) + int(n["cantidad"]) - int(n["recuperadas"] or 0)
            except Exception:
                pass
        for i, o in enumerate(filas):
            if finalizados:
                vals = (o["lote"], _modelo(o), _fecha(o.get("fecha_inicio")), _fecha_hora(o.get("fecha_fin")) if o.get("fecha_fin") else "—",
                        int(o.get("aprobados_final") or 0), nc_por_orden.get(o["id_orden"], 0), o.get("motivo_cierre") or "Completado")
            else:
                est = ESTADO_TXT.get(o.get("estado_paso") or "EN_PROCESO", "En proceso")
                vals = (o["lote"], _modelo(o), f"Paso {o['paso_actual']} de {prod.ULTIMO_PASO}", est,
                        _fecha(o.get("fecha_inicio")), int(o["cantidad_plan"]))
            tv.insert("", "end", iid=str(o["id_orden"]), tags=tags_fila(i), values=vals)
        if not filas:
            tenue(card, "No hay órdenes finalizadas todavía." if finalizados else "No hay lotes en producción. Cree uno con «Nueva orden».", 12).pack(anchor="w", pady=(8, 0))
        elif self._exi.id_sel is not None and str(self._exi.id_sel) in tv.get_children():
            tv.selection_set(str(self._exi.id_sel))

        def ver(_e=None):
            sel = tv.selection()
            if not sel:
                return messagebox.showinfo(titulo, "Seleccione un lote de la lista.", parent=d)
            d.destroy()
            self._exi_seleccionar_lote(int(sel[0]))

        tv.bind("<Double-1>", ver)
        pie = transparente(card)
        pie.pack(fill="x", pady=(10, 0))
        Boton(pie, "Ver lote", ver, "pri", ancho=140, alto=38, icono="check").pack(side="right")
        Boton(pie, "Cerrar", d.destroy, "accion", ancho=110, alto=38).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------ nueva orden
    def dialogo_orden(self):
        if not self._exi_permiso("No tiene permiso para crear órdenes de producción."):
            return
        try:
            disponible = prod.saldo_materia_prima()
            filas = db.pistones()
            sugerido = prod.proximo_lote()
        except Exception as ex:
            return messagebox.showerror("Producción", f"No se pudo preparar la orden.\n\n{ex}", parent=self)
        if not filas:
            return messagebox.showinfo("Producción", "Primero registre al menos un pistón en el catálogo.", parent=self)
        d = Dialogo(self, "Nueva orden de producción", 600, 720)
        card = d.cuerpo(24, scroll=True)
        titulo_seccion(card, "Nueva orden de producción").pack(anchor="w")
        tenue(card, f"Materia prima disponible: {_kg(disponible)} kg. Se creará un seguimiento nuevo de 9 etapas, "
                    "independiente de los demás lotes.", 12, wraplength=500, justify="left").pack(anchor="w", pady=(2, 0))
        self._exi_rotulo(card, "Código del lote")
        lote = campo(card, 220)
        lote.insert(0, sugerido)
        lote.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Código o modelo del pistón")
        combo = Combo(card, [f"{r['codigo']} · {r['descripcion']}" for r in filas], ancho=500)
        combo.pack(anchor="w", fill="x", pady=(5, 0))
        tenue(card, "Al liberar el lote, las piezas aprobadas se suman a las existencias de este pistón.", 11).pack(anchor="w", pady=(3, 0))
        self._exi_rotulo(card, "Cantidad inicial a fabricar")
        cantidad = Contador(card, 1, 999999, 100)
        cantidad.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Materia prima requerida (kg de aluminio)")
        kg = campo(card, 200)
        limitar_decimal(kg, 3)
        kg.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Fecha de inicio (dd/mm/aaaa)")
        fecha = campo(card, 200)
        fecha.insert(0, date.today().strftime("%d/%m/%Y"))
        fecha.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Responsable")
        resp = campo(card, 500)
        resp.insert(0, self._exi_nombre_usuario())
        resp.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Observaciones")
        obs = campo(card, 500)
        obs.pack(fill="x", pady=(5, 0))

        def guardar():
            try:
                k, n = _decimal(kg.get()), int(cantidad.get())
                f_ini = datetime.strptime(fecha.get().strip(), "%d/%m/%Y").date()
            except ValueError:
                return messagebox.showwarning("Datos", "Revise los kilogramos, la cantidad y la fecha (dd/mm/aaaa).", parent=d)
            pid = filas[combo.current()]["id"]
            try:
                oid, codigo, cod_lote = prod.nueva_orden(lote.get(), pid, n, k, f_ini, resp.get(), obs.get(), self.user["id"])
            except ValueError as ex:
                return messagebox.showwarning("Orden no creada", str(ex), parent=d)
            except Exception as ex:
                return messagebox.showerror("Orden no creada", str(ex), parent=d)
            d.destroy()
            self._exi_tras_cambio(oid)
            self._exi_cargar_orden(reiniciar_paso=True)
            messagebox.showinfo("Producción", f"Orden {codigo} creada (lote {cod_lote}). Su seguimiento está vacío y el paso 1 quedó en proceso.", parent=self)
        Boton(card, "Crear orden", guardar, "pri").pack(fill="x", pady=(20, 0))

    def dialogo_materia_prima(self):
        if not self._exi_permiso("No tiene permiso para registrar materia prima."):
            return
        d = Dialogo(self, "Recepción de materia prima", 520, 420)
        card = d.cuerpo(26)
        titulo_seccion(card, "Recepción de materia prima").pack(anchor="w")
        self._exi_rotulo(card, "Aluminio recibido (kg)", 14)
        kg = campo(card, 200)
        limitar_decimal(kg, 3)
        kg.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Descripción")
        desc = campo(card, 420, "Ej.: Aluminio grado A, proveedor…")
        desc.pack(fill="x", pady=(5, 0))

        def guardar():
            try:
                prod.entrada_materia_prima(_decimal(kg.get()), desc.get(), self.user["id"])
            except ValueError as ex:
                return messagebox.showwarning("Materia prima", str(ex) or "Indique los kilogramos.", parent=d)
            except Exception as ex:
                return messagebox.showerror("Materia prima", str(ex), parent=d)
            d.destroy()
            self.cargar_movimientos()
            messagebox.showinfo("Producción", "Materia prima registrada.", parent=self)
        Boton(card, "Guardar recepción", guardar, "pri").pack(fill="x", pady=(20, 0))

    # ------------------------------------------------------------------ completar paso con resultado de calidad
    def dialogo_completar_paso(self):
        if not (self.gestion_stock or self.es_control):
            return messagebox.showwarning("Permiso denegado", "No tiene permiso para avanzar la producción.", parent=self)
        x = self._exi
        o = x.orden
        if not o:
            return messagebox.showinfo("Producción", "Primero cree o elija un lote en «Lotes activos».", parent=self)
        if o["estado"] != "EN_PRODUCCION":
            return messagebox.showinfo("Producción", "Este lote ya está finalizado.", parent=self)
        paso = int(o["paso_actual"])
        if not self._exi_permiso_paso(paso, "No tiene permiso para avanzar la producción."):
            return
        actual = next((e for e in x.etapas if e["paso"] == paso), None)
        if actual and actual["estado"] == "BLOQUEADO":
            return messagebox.showwarning("Paso bloqueado", f"El paso {paso} está bloqueado: {actual['bloqueo'] or 'incidencia'}.\n"
                                                           "Desbloquéelo antes de completarlo.", parent=self)
        con_piezas = paso >= prod.PRIMER_PASO_PIEZAS
        recibida = prod.piezas_recibidas(x.etapas, o["cantidad_plan"], paso)
        d = Dialogo(self, "Registro de resultados", 620, 760 if con_piezas else 520)
        card = d.cuerpo(24, scroll=True)
        titulo_seccion(card, f"Paso {paso}: {prod.PASOS[paso - 1]}").pack(anchor="w")
        tenue(card, f"Lote {o['lote']} · Orden {o['codigo_orden']} · {_modelo(o)}", 12).pack(anchor="w", pady=(2, 0))
        cont = SimpleNamespace(proc=None, apr=None, rec=None, pen=None, motivo=None, defectos=None)
        lb_suma = None
        if con_piezas:
            etiqueta(card, f"Cantidad recibida de la etapa anterior: {recibida}", 14, "bold").pack(anchor="w", pady=(12, 0))
            fila = transparente(card)
            fila.pack(fill="x", pady=(6, 0))
            for i in range(2):
                fila.grid_columnconfigure(i, weight=1, uniform="cc")
            def par(r, c, texto, valor):
                f = transparente(fila)
                f.grid(row=r, column=c, sticky="w", pady=(0, 6), padx=(0, 10))
                etiqueta(f, texto, 12, "bold", C["muted"]).pack(anchor="w")
                w = Contador(f, 0, 999999, valor, ancho=170)
                w.pack(anchor="w", pady=(3, 0))
                return w
            cont.proc = par(0, 0, "Cantidad procesada", recibida)
            cont.apr = par(0, 1, "Cantidad aprobada", recibida)
            cont.rec = par(1, 0, "Cantidad rechazada", 0)
            cont.pen = par(1, 1, "Pendiente de evaluación", 0)
            lb_suma = etiqueta(card, "", 12, "bold")
            lb_suma.pack(anchor="w", pady=(2, 0))
            self._exi_rotulo(card, "Motivo de los rechazos (obligatorio si hay rechazadas)")
            cont.motivo = campo(card, 540)
            cont.motivo.pack(fill="x", pady=(5, 0))
            self._exi_rotulo(card, "Descripción de los defectos encontrados")
            cont.defectos = campo(card, 540)
            cont.defectos.pack(fill="x", pady=(5, 0))
        else:
            tenue(card, "Este paso trabaja con materia prima (aún no se cuentan piezas). Se registra quién lo ejecutó, cuándo y sus observaciones.",
                  12, wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
        self._exi_rotulo(card, "Observaciones")
        obs = campo(card, 540)
        obs.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Responsable de la inspección")
        resp = campo(card, 540)
        resp.insert(0, self._exi_nombre_usuario())
        resp.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Fecha y hora (dd/mm/aaaa hh:mm)")
        fh = campo(card, 220)
        fh.insert(0, datetime.now().strftime(FMT_FH))
        fh.pack(anchor="w", pady=(5, 0))
        if paso == prod.PASO_LIBERACION:
            tenue(card, "Al guardar, las piezas aprobadas ingresan una sola vez al stock de productos terminados.", 11,
                  wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
        elif con_piezas:
            tenue(card, "Solo las piezas aprobadas continúan al siguiente paso. Las rechazadas quedan como productos no conformes "
                        "y las pendientes permanecen retenidas.", 11, wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
        boton = Boton(card, "Guardar resultado y completar paso", lambda: guardar(), "pri")
        boton.pack(fill="x", pady=(18, 0))

        auto = {"ultimo": recibida}

        def valores():
            return (_entero(cont.proc.get(), "La cantidad procesada"), _entero(cont.apr.get(), "La cantidad aprobada"),
                    _entero(cont.rec.get(), "La cantidad rechazada"), _entero(cont.pen.get(), "La cantidad pendiente"))

        def refrescar():
            """Mantiene la suma a la vista y recalcula «aprobada» mientras el usuario no la haya escrito a mano."""
            try:
                if not lb_suma or not d.winfo_exists():
                    return
                try:
                    proc, apr, rec, pen = valores()
                    if apr == auto["ultimo"]:
                        nuevo = max(0, proc - rec - pen)
                        if nuevo != apr:
                            cont.apr.set(nuevo)
                        auto["ultimo"] = apr = nuevo
                    total = apr + rec + pen
                    if total == proc and proc == recibida:
                        lb_suma.configure(text=f"✓ {apr} + {rec} + {pen} = {total} (coincide con las procesadas)", text_color=C["ok"])
                    else:
                        lb_suma.configure(text=f"✕ {apr} + {rec} + {pen} = {total}; deben sumar {proc} procesadas"
                                               + ("" if proc == recibida else f" y coincidir con las {recibida} recibidas"),
                                          text_color=C["danger"])
                except ValueError:
                    lb_suma.configure(text="Escriba números enteros.", text_color=C["danger"])
                d.after(250, refrescar)
            except tk.TclError:      # la ventana se cerró entre dos repintados
                return

        def guardar():
            try:
                momento = parse_fecha_hora(fh.get())
                r = {"responsable": resp.get(), "observaciones": obs.get(), "fecha_hora": momento}
                if con_piezas:
                    proc, apr, rec, pen = valores()
                    r.update(recibida=recibida, procesada=proc, aprobada=apr, rechazada=rec, pendiente=pen,
                             motivo=cont.motivo.get(), defectos=cont.defectos.get())
            except ValueError as ex:
                return messagebox.showwarning("Datos", str(ex), parent=d)
            try:
                res = prod.completar_paso(o["id_orden"], r, self.user["id"])
            except ValueError as ex:
                return messagebox.showwarning("Paso no completado", str(ex), parent=d)
            except Exception as ex:
                return messagebox.showerror("Paso no completado", str(ex), parent=d)
            d.destroy()
            self._exi_tras_cambio()
            self._exi_cargar_orden(reiniciar_paso=True)
            partes = [f"Paso {paso} completado ({ESTADO_TXT[res['estado']].lower()})."]
            if con_piezas:
                partes.append(f"Aprobadas: {res['aprobadas']} · rechazadas: {res['rechazadas']} · pendientes: {res['pendientes']}.")
                if res["rechazadas"]:
                    partes.append(f"{res['rechazadas']} pieza(s) quedaron registradas como productos no conformes.")
            if res["sin_piezas"]:
                partes.append("No quedaron piezas aprobadas: el lote se cerró sin producción.")
            elif res["liberadas"] and res["stock_nuevo"] is not None:
                partes.append(f"Entrada de producción: {res['liberadas']} pistones. Stock {res['stock_anterior']} → {res['stock_nuevo']}.")
            elif res["finalizada"]:
                partes.append("El lote quedó finalizado.")
            else:
                partes.append(f"El paso {paso + 1} quedó en proceso.")
            toast(self, "\n".join(partes), "info", ms=9000)

        if con_piezas:
            refrescar()

    # ------------------------------------------------------------------ bloqueo / pendientes
    def dialogo_bloquear(self):
        o = self._exi.orden
        if not o or o["estado"] != "EN_PRODUCCION":
            return
        paso = int(o["paso_actual"])
        if not self._exi_permiso_paso(paso, "No tiene permiso para bloquear pasos."):
            return
        d = Dialogo(self, "Bloquear paso", 540, 340)
        card = d.cuerpo(26)
        titulo_seccion(card, f"Bloquear paso {paso}: {prod.PASOS[paso - 1]}").pack(anchor="w")
        tenue(card, f"Lote {o['lote']}. Mientras esté bloqueado no se puede completar ni avanzar.", 12, wraplength=470, justify="left").pack(anchor="w", pady=(2, 0))
        self._exi_rotulo(card, "Incidencia que impide continuar", 14)
        motivo = campo(card, 480)
        motivo.pack(fill="x", pady=(5, 0))

        def guardar():
            try:
                prod.bloquear_paso(o["id_orden"], motivo.get(), self.user["id"])
            except ValueError as ex:
                return messagebox.showwarning("Bloqueo", str(ex), parent=d)
            except Exception as ex:
                return messagebox.showerror("Bloqueo", str(ex), parent=d)
            d.destroy()
            self._exi_tras_cambio()
        Boton(card, "Bloquear paso", guardar, "danger").pack(fill="x", pady=(20, 0))

    def _desbloquear(self):
        o = self._exi.orden
        if not o or not self._exi_permiso_paso(int(o["paso_actual"]), "No tiene permiso para desbloquear pasos."):
            return
        if not messagebox.askyesno("Desbloquear", "¿La incidencia ya fue resuelta? El paso volverá a «En proceso».", parent=self):
            return
        try:
            prod.desbloquear_paso(o["id_orden"], "Incidencia resuelta", self.user["id"])
        except Exception as ex:
            return messagebox.showwarning("Desbloqueo", str(ex), parent=self)
        self._exi_tras_cambio()

    def dialogo_pendientes(self):
        """Evalúa las piezas retenidas del paso mostrado (mismo proceso que la pestaña «Pistones en revisión»)."""
        x = self._exi
        if not self._exi_permiso_paso(x.sel, "No tiene permiso para evaluar piezas."):
            return
        o = x.orden
        fila = None
        if o:
            try:
                fila = next((f for f in prod.en_revision(o["id_orden"]) if f["paso"] == x.sel), None)
            except Exception as ex:
                return messagebox.showerror("Pendientes", str(ex), parent=self)
        if not fila:
            return messagebox.showinfo("Pendientes", "Este paso no tiene piezas pendientes de evaluación.", parent=self)
        self._dialogo_evaluar(fila, self, lambda: None)

    def _dialogo_evaluar(self, fila, padre, recargar):
        """Evaluación de piezas en revisión: las aprobadas (recuperadas) continúan; las rechazadas pasan a «Pistones rechazados»."""
        if not self._exi_permiso_paso(fila["paso"], "No tiene permiso para evaluar piezas."):
            return
        vigente = prod.pendiente_vigente(fila)
        if vigente <= 0:
            return messagebox.showinfo("Revisión", "Estas piezas ya fueron evaluadas.", parent=padre)
        puede = prod.puede_aprobar_revision(fila)
        paso = fila["paso"]
        d = Dialogo(self, "Evaluar piezas en revisión", 580, 660)
        card = d.cuerpo(24, scroll=True)
        titulo_seccion(card, f"En revisión · paso {paso}: {prod.PASOS[paso - 1]}").pack(anchor="w")
        tenue(card, f"Lote {fila['lote']} · {vigente} pieza(s) retenidas. Las aprobadas se suman a lo que recibe el paso siguiente; "
                    "las rechazadas pasan a «Pistones rechazados».", 12, wraplength=500, justify="left").pack(anchor="w", pady=(2, 0))
        if not puede:
            etiqueta(card, "El paso siguiente ya se completó o el lote está cerrado: estas piezas ya no pueden continuar el flujo; "
                           "solo pueden rechazarse.", 12, "bold", C["warn"], wraplength=500, justify="left").pack(anchor="w", pady=(6, 0))
        self._exi_rotulo(card, "Aprobadas (recuperadas)")
        apr = Contador(card, 0, vigente if puede else 0, 0)
        apr.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Rechazadas")
        rec = Contador(card, 0, vigente, 0)
        rec.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Motivo (obligatorio si hay rechazadas)")
        motivo = campo(card, 500)
        motivo.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Defectos encontrados")
        defectos = campo(card, 500)
        defectos.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Observaciones")
        obs = campo(card, 500)
        obs.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Responsable de la inspección")
        resp = campo(card, 500)
        resp.insert(0, self._exi_nombre_usuario())
        resp.pack(fill="x", pady=(5, 0))

        def guardar():
            try:
                a, r = _entero(apr.get(), "La cantidad aprobada"), _entero(rec.get(), "La cantidad rechazada")
                prod.resolver_pendientes(fila["id_orden"], paso, a, r, motivo.get(), defectos.get(), obs.get(), resp.get(), self.user["id"])
            except ValueError as ex:
                return messagebox.showwarning("Revisión", str(ex), parent=d)
            except Exception as ex:
                return messagebox.showerror("Revisión", str(ex), parent=d)
            d.destroy()
            recargar()
            self._exi_tras_cambio()
        Boton(card, "Guardar evaluación", guardar, "pri").pack(fill="x", pady=(18, 0))

    # ------------------------------------------------------------------ productos no conformes
    def dialogo_no_conformes(self):
        """Ventana con dos pestañas: «Pistones rechazados» (recuperar o descartar) y «Pistones en revisión» (aprobar o rechazar).

        Nada se borra: los registros ya resueltos siguen en el historial («Mostrar historial») con su defecto original.
        Una pieza recuperada deja de contarse como rechazada y como pendiente.
        """
        d = Dialogo(self, "Productos no conformes", 1180, 700, redim=True)
        card = d.cuerpo(22)
        titulo_seccion(card, "Productos no conformes").pack(anchor="w")
        tenue(card, "Los pistones rechazados y en revisión no forman parte del stock de venta. Una pieza recuperada o aprobada "
                    "sale de estas listas activas; su historial se conserva.", 12).pack(anchor="w", pady=(2, 8))
        barra = transparente(card)
        barra.pack(fill="x", pady=(0, 8))
        cuerpo = transparente(card)
        cuerpo.pack(fill="both", expand=True)
        paneles, botones, cargadores = {}, {}, {}

        def mostrar(clave):
            for k, pn in paneles.items():
                pn.pack_forget()
                botones[k].seleccionar(k == clave)
            paneles[clave].pack(fill="both", expand=True)

        def refrescar():
            for f in cargadores.values():
                f()

        for clave, texto in (("rechazados", "Pistones rechazados"), ("revision", "Pistones en revisión")):
            b = Boton(barra, texto, partial(mostrar, clave), "accion", ancho=250, alto=36, tam=13)
            b.pack(side="left", padx=(0, 6))
            botones[clave] = b
            paneles[clave] = transparente(cuerpo)
        cargadores["rechazados"] = self._nc_pestana_rechazados(paneles["rechazados"], d, botones["rechazados"], refrescar)
        cargadores["revision"] = self._nc_pestana_revision(paneles["revision"], d, botones["revision"], refrescar)
        pie = transparente(card)
        pie.pack(fill="x", pady=(10, 0))
        Boton(pie, "Cerrar", d.destroy, "accion", ancho=110, alto=38).pack(side="right")
        refrescar()
        mostrar("rechazados")

    def _nc_filtros(self, padre, cargar, extra_texto):
        """Dos filtros alternables: «Solo el lote elegido» y el de historial. Devuelve (estado_lote, estado_historial)."""
        filtros = transparente(padre)
        filtros.pack(fill="x", pady=(0, 8))
        est = {"lote": False, "hist": False}

        def alternar(clave, boton):
            est[clave] = not est[clave]
            boton.seleccionar(est[clave])
            cargar()
        b1 = Boton(filtros, "Solo el lote elegido", None, "accion", ancho=180, alto=32, tam=12)
        b1.configure(command=lambda: alternar("lote", b1))
        b1.pack(side="left")
        b2 = Boton(filtros, extra_texto, None, "accion", ancho=280, alto=32, tam=12)
        b2.configure(command=lambda: alternar("hist", b2))
        b2.pack(side="left", padx=8)
        return est

    def _nc_pestana_rechazados(self, panel, d, boton_tab, refrescar):
        """Pestaña 1: registros de no conformes. Por defecto solo los que aún tienen piezas por recuperar o descartar."""
        cols = ("fecha", "lote", "modelo", "etapa", "cant", "saldo", "rec", "des", "motivo", "estado", "resp")
        enc = {"fecha": "FECHA", "lote": "LOTE", "modelo": "MODELO", "etapa": "ETAPA DEL DEFECTO", "cant": "CANT.", "saldo": "SALDO",
               "rec": "RECUP.", "des": "DESCART.", "motivo": "MOTIVO", "estado": "ESTADO", "resp": "RESPONSABLE"}
        registros = {}
        recarga = {"f": lambda: None}
        est = self._nc_filtros(panel, lambda: recarga["f"](), "Mostrar historial (recuperados y descartados)")
        marco, tv = tabla(panel, cols, enc, (115, 65, 160, 190, 50, 55, 55, 65, 170, 105, 100),
                          {"cant": "center", "saldo": "center", "rec": "center", "des": "center"})
        marco.pack(fill="both", expand=True)
        det = etiqueta(panel, "", 12, wraplength=1060, justify="left")
        det.pack(anchor="w", pady=(8, 0))

        def cargar():
            sel_previa = tv.selection()
            tv.delete(*tv.get_children())
            registros.clear()
            try:
                filas = prod.no_conformes(self._exi.orden["id_orden"] if est["lote"] and self._exi.orden else None,
                                          solo_con_saldo=not est["hist"])
                pendientes_n = sum(prod.saldo_nc(n) for n in prod.no_conformes(solo_con_saldo=True))
            except Exception as ex:
                return messagebox.showerror("No conformes", str(ex), parent=d)
            boton_tab.configure(text=f"Pistones rechazados ({pendientes_n})")
            for i, n in enumerate(filas):
                registros[str(n["id_nc"])] = n
                tv.insert("", "end", iid=str(n["id_nc"]), tags=tags_fila(i), values=(
                    _fecha_hora(n["fecha_hora"]), n["lote"], _modelo(n), f"{n['paso']}. {prod.PASOS[n['paso'] - 1]}",
                    n["cantidad"], prod.saldo_nc(n), n["recuperadas"], n["descartadas"], n["motivo"], prod.estado_nc(n),
                    n["responsable"] or "—"))
            if sel_previa and tv.exists(sel_previa[0]):
                tv.selection_set(sel_previa[0])
            det.configure(text="" if filas else ("No hay pistones rechazados con estos filtros." if est["hist"] else
                                                 "No hay pistones rechazados pendientes de recuperar o descartar."))

        recarga["f"] = cargar

        def al_elegir(_e=None):
            sel = tv.selection()
            n = registros.get(sel[0]) if sel else None
            if not n:
                return
            texto = (f"Lote {n['lote']} · {n['codigo'] or '—'} · etapa {n['paso']}: {n['cantidad']} rechazada(s), "
                     f"{n['recuperadas']} recuperada(s), {n['descartadas']} descartada(s).  "
                     f"Defectos: {n['defectos'] or '—'}.  Observaciones: {n['observaciones'] or '—'}.")
            try:
                for r in prod.reprocesos(n["id_nc"]):
                    texto += (f"\n   Reproceso {_fecha_hora(r['fecha_hora'])}: {r['aprobadas']} recuperadas / {r['rechazadas']} descartadas "
                              f"({r['responsable'] or '—'}). {r['observaciones'] or ''}")
            except Exception:
                pass
            det.configure(text=texto)
        tv.bind("<<TreeviewSelect>>", al_elegir)

        def reprocesar(_e=None):
            sel = tv.selection()
            n = registros.get(sel[0]) if sel else None
            if not n:
                return messagebox.showinfo("Reproceso", "Seleccione un registro de la lista.", parent=d)
            if prod.saldo_nc(n) <= 0:
                return messagebox.showinfo("Reproceso", "Este registro ya no tiene piezas por recuperar o descartar.", parent=d)
            self._dialogo_reproceso(n, d, refrescar)
        pie = transparente(panel)
        pie.pack(fill="x", pady=(10, 0))
        if self.gestion_stock or self.es_control:
            Boton(pie, "Recuperar / rechazar", reprocesar, "pri", ancho=200, alto=38, icono="refresh-cw").pack(side="left")
        return cargar

    def _nc_pestana_revision(self, panel, d, boton_tab, refrescar):
        """Pestaña 2: piezas retenidas «en revisión» de todos los lotes. Mismo proceso: aprobar (recuperar) o rechazar."""
        cols = ("fecha", "lote", "modelo", "etapa", "cant", "apr", "rech", "vig", "motivo", "estado", "resp")
        enc = {"fecha": "FECHA", "lote": "LOTE", "modelo": "MODELO", "etapa": "ETAPA DE ORIGEN", "cant": "RETENIDAS",
               "apr": "APROB.", "rech": "RECH.", "vig": "EN REVISIÓN", "motivo": "OBSERVACIONES", "estado": "ESTADO", "resp": "RESPONSABLE"}
        registros = {}
        recarga = {"f": lambda: None}
        est = self._nc_filtros(panel, lambda: recarga["f"](), "Mostrar historial (ya evaluados)")
        marco, tv = tabla(panel, cols, enc, (115, 65, 160, 190, 75, 55, 55, 85, 170, 115, 100),
                          {"cant": "center", "apr": "center", "rech": "center", "vig": "center"})
        marco.pack(fill="both", expand=True)
        det = etiqueta(panel, "", 12, wraplength=1060, justify="left")
        det.pack(anchor="w", pady=(8, 0))

        def cargar():
            sel_previa = tv.selection()
            tv.delete(*tv.get_children())
            registros.clear()
            try:
                filas = prod.en_revision(self._exi.orden["id_orden"] if est["lote"] and self._exi.orden else None,
                                         solo_vigentes=not est["hist"])
                en_rev_n = sum(prod.pendiente_vigente(f) for f in prod.en_revision())
            except Exception as ex:
                return messagebox.showerror("En revisión", str(ex), parent=d)
            boton_tab.configure(text=f"Pistones en revisión ({en_rev_n})")
            for i, f in enumerate(filas):
                clave = f"{f['id_orden']}-{f['paso']}"
                registros[clave] = f
                tv.insert("", "end", iid=clave, tags=tags_fila(i), values=(
                    _fecha_hora(f["fecha_hora"]) if f.get("fecha_hora") else "—", f["lote"], _modelo(f),
                    f"{f['paso']}. {prod.PASOS[f['paso'] - 1]}", f["pendientes"], f["pend_aprobados"], f["pend_rechazados"],
                    prod.pendiente_vigente(f), f["observaciones"] or "", prod.estado_revision(f), f.get("responsable") or "—"))
            if sel_previa and tv.exists(sel_previa[0]):
                tv.selection_set(sel_previa[0])
            det.configure(text="" if filas else ("No hay pistones en revisión con estos filtros." if est["hist"] else
                                                 "No hay pistones en revisión."))

        recarga["f"] = cargar

        def al_elegir(_e=None):
            sel = tv.selection()
            f = registros.get(sel[0]) if sel else None
            if not f:
                return
            texto = (f"Lote {f['lote']} · {f['codigo'] or '—'} · etapa {f['paso']}: {f['pendientes']} retenida(s), "
                     f"{f['pend_aprobados']} aprobada(s), {f['pend_rechazados']} rechazada(s), {prod.pendiente_vigente(f)} en revisión.  "
                     f"Motivo/defectos de la etapa: {f.get('motivo') or '—'} / {f.get('defectos') or '—'}.")
            if prod.pendiente_vigente(f) > 0 and not prod.puede_aprobar_revision(f):
                texto += "\n   Estas piezas ya no pueden continuar el flujo (el paso siguiente se completó o el lote está cerrado): solo pueden rechazarse."
            det.configure(text=texto)
        tv.bind("<<TreeviewSelect>>", al_elegir)

        def evaluar(_e=None):
            sel = tv.selection()
            f = registros.get(sel[0]) if sel else None
            if not f:
                return messagebox.showinfo("Revisión", "Seleccione un registro de la lista.", parent=d)
            self._dialogo_evaluar(f, d, refrescar)
        pie = transparente(panel)
        pie.pack(fill="x", pady=(10, 0))
        if self.gestion_stock or self.es_control:
            Boton(pie, "Aprobar / rechazar", evaluar, "pri", ancho=200, alto=38, icono="check").pack(side="left")
        return cargar

    def _dialogo_reproceso(self, n, padre, recargar):
        if not self._exi_permiso_paso(n["paso"], "No tiene permiso para registrar reprocesos."):
            return
        saldo = prod.saldo_nc(n)
        d = Dialogo(self, "Reproceso de no conformes", 580, 600)
        card = d.cuerpo(24, scroll=True)
        titulo_seccion(card, f"Reproceso · lote {n['lote']}").pack(anchor="w")
        tenue(card, f"{n['cantidad']} rechazadas en el paso {n['paso']} ({n['motivo']}). Por reprocesar: {saldo}. "
                    "La nueva inspección decide cuántas se recuperan; solo esas ingresan al stock, una vez, y dejan de contarse como rechazadas.", 12,
              wraplength=500, justify="left").pack(anchor="w", pady=(2, 0))
        if not n.get("liberada"):
            etiqueta(card, "Este lote aún está en producción: solo podrá recuperar piezas cuando sea liberado.", 12, "bold",
                     C["warn"], wraplength=500, justify="left").pack(anchor="w", pady=(6, 0))
        self._exi_rotulo(card, "Piezas aprobadas en la nueva inspección (se recuperan)")
        apr = Contador(card, 0, saldo, 0)
        apr.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Piezas rechazadas otra vez (se descartan)")
        rec = Contador(card, 0, saldo, 0)
        rec.pack(anchor="w", pady=(5, 0))
        self._exi_rotulo(card, "Responsable de la nueva inspección")
        resp = campo(card, 500)
        resp.insert(0, self._exi_nombre_usuario())
        resp.pack(fill="x", pady=(5, 0))
        self._exi_rotulo(card, "Observaciones del reproceso")
        obs = campo(card, 500)
        obs.pack(fill="x", pady=(5, 0))

        def guardar():
            try:
                a, r = _entero(apr.get(), "La cantidad aprobada"), _entero(rec.get(), "La cantidad rechazada")
                res = prod.reprocesar(n["id_nc"], a, r, resp.get(), obs.get(), self.user["id"])
            except ValueError as ex:
                return messagebox.showwarning("Reproceso", str(ex), parent=d)
            except Exception as ex:
                return messagebox.showerror("Reproceso", str(ex), parent=d)
            d.destroy()
            recargar()
            self._exi_tras_cambio()
            extra = (f" Stock {res['stock_anterior']} → {res['stock_nuevo']}." if res["stock_nuevo"] is not None else "")
            messagebox.showinfo("Reproceso", f"Registrado: {res['recuperadas']} recuperadas y {res['descartadas']} descartadas.{extra}", parent=padre)
        Boton(card, "Registrar nueva inspección", guardar, "pri").pack(fill="x", pady=(18, 0))

    # ------------------------------------------------------------------ historial permanente de rechazos definitivos
    def dialogo_historial(self):
        """Pistones rechazados DEFINITIVAMENTE (descartados tras el reproceso). Solo lectura y permanente.

        El contador mensual cambia de periodo y vuelve a cero cada mes, pero los registros anteriores nunca se eliminan:
        se consultan con los filtros de fecha, mes, año, lote, modelo y etapa.
        """
        try:
            op = prod.opciones_rechazos()
        except Exception as ex:
            return messagebox.showerror("Historial", f"No se pudo cargar el historial.\n\n{ex}", parent=self)
        hoy = date.today()
        d = Dialogo(self, "Historial de pistones rechazados", 1240, 760, redim=True)
        card = d.cuerpo(20)
        titulo_seccion(card, "Historial de pistones rechazados").pack(anchor="w")
        tenue(card, "Solo piezas rechazadas definitivamente. Es un registro permanente: no se puede editar ni borrar, "
                    "aunque cambie el mes o el año.", 12).pack(anchor="w", pady=(2, 8))

        # ---- contadores: el del mes en curso (vuelve a cero al cambiar de mes) y el del filtro aplicado
        fila_c = transparente(card)
        fila_c.pack(fill="x", pady=(0, 8))
        for i in range(2):
            fila_c.grid_columnconfigure(i, weight=1, uniform="hist_c")
        c1, c2 = tarjeta(fila_c), tarjeta(fila_c)
        c1.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        c2.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        tenue(c1, f"Rechazados en {MESES[hoy.month - 1]} {hoy.year} (contador mensual)", 12).pack(anchor="w", padx=16, pady=(10, 0))
        lb_mes = etiqueta(c1, "0", 24, "bold", C["danger"])
        lb_mes.pack(anchor="w", padx=16, pady=(0, 10))
        tenue(c2, "Resultado de los filtros", 12).pack(anchor="w", padx=16, pady=(10, 0))
        lb_tot = etiqueta(c2, "0 pistones", 24, "bold")
        lb_tot.pack(anchor="w", padx=16, pady=(0, 2))
        lb_tot2 = tenue(c2, "", 12)
        lb_tot2.pack(anchor="w", padx=16, pady=(0, 10))

        # ---- filtros
        fl = tarjeta(card)
        fl.pack(fill="x", pady=(0, 8))
        grid = transparente(fl)
        grid.pack(fill="x", padx=14, pady=10)
        modelos = {f"{m['codigo_piston']} · {m['modelo'] or ''}".strip(" ·"): m["id_piston"] for m in op["modelos"]}
        anios = [str(a) for a in op["anios"]]
        if str(hoy.year) not in anios:
            anios.insert(0, str(hoy.year))
        etapas = {f"{i}. {prod.PASOS[i - 1]}": i for i in range(1, prod.ULTIMO_PASO + 1)}

        w = {}

        def celda(col, clave, texto, crear):
            f = transparente(grid)
            f.grid(row=0, column=col, sticky="w", padx=(0, 10))
            tenue(f, texto, 11).pack(anchor="w")
            w[clave] = crear(f)
            w[clave].pack(anchor="w", pady=(2, 0))

        def combo(valores, ancho):
            return lambda f: Combo(f, valores, ancho=ancho, command=lambda _v: aplicar())
        celda(0, "desde", "Desde (fecha)", lambda f: campo(f, 112, "dd/mm/aaaa"))
        celda(1, "hasta", "Hasta (fecha)", lambda f: campo(f, 112, "dd/mm/aaaa"))
        celda(2, "mes", "Mes", combo(["Todos"] + list(MESES), 128))
        celda(3, "anio", "Año", combo(["Todos"] + anios, 100))
        celda(4, "lote", "Lote", combo(["Todos"] + op["lotes"], 110))
        celda(5, "modelo", "Modelo", combo(["Todos"] + list(modelos), 210))
        celda(6, "etapa", "Etapa del defecto", combo(["Todas"] + list(etapas), 220))
        f_desde, f_hasta, cb = w["desde"], w["hasta"], w
        bt = transparente(grid)
        bt.grid(row=0, column=7, sticky="sw", padx=(4, 0))
        Boton(bt, "Buscar", lambda: aplicar(), "pri", ancho=90, alto=34, tam=12, icono="search").pack(side="left")
        Boton(bt, "Limpiar", lambda: limpiar(), "accion", ancho=90, alto=34, tam=12).pack(side="left", padx=(6, 0))

        # ---- tabla
        cols = ("fecha", "pis", "lote", "cant", "etapa", "motivo", "resp")
        enc = {"fecha": "FECHA DEL RECHAZO", "pis": "CÓDIGO Y MODELO", "lote": "LOTE", "cant": "CANT. RECHAZADA",
               "etapa": "ETAPA DEL DEFECTO", "motivo": "MOTIVO DEL RECHAZO", "resp": "RESPONSABLE DE LA DECISIÓN"}
        marco, tv = tabla(card, cols, enc, (130, 270, 80, 110, 200, 230, 170), {"cant": "center"})
        marco.pack(fill="both", expand=True)
        det = etiqueta(card, "", 12, wraplength=1150, justify="left")
        det.pack(anchor="w", pady=(8, 0))
        registros = {}

        def leer_fecha(campo_, rotulo):
            txt = campo_.get().strip()
            if not txt:
                return None
            try:
                return datetime.strptime(txt, "%d/%m/%Y").date()
            except ValueError:
                raise ValueError(f"La fecha «{rotulo}» debe escribirse como dd/mm/aaaa (ejemplo: 21/11/2026).")

        def aplicar(_e=None):
            try:
                desde, hasta = leer_fecha(f_desde, "Desde"), leer_fecha(f_hasta, "Hasta")
                if desde and hasta and desde > hasta:
                    raise ValueError("La fecha «Desde» no puede ser posterior a «Hasta».")
            except ValueError as ex:
                return messagebox.showwarning("Filtros", str(ex), parent=d)
            mes = MESES.index(cb["mes"].get()) + 1 if cb["mes"].get() in MESES else None
            anio = int(cb["anio"].get()) if cb["anio"].get().isdigit() else None
            lote = cb["lote"].get() if cb["lote"].get() != "Todos" else None
            try:
                filas = prod.rechazos_definitivos(desde, hasta, mes, anio, lote, modelos.get(cb["modelo"].get()),
                                                  etapas.get(cb["etapa"].get()))
                del_mes = prod.rechazados_del_mes(hoy.year, hoy.month)
            except Exception as ex:
                return messagebox.showerror("Historial", f"No se pudo consultar el historial.\n\n{ex}", parent=d)
            tv.delete(*tv.get_children())
            registros.clear()
            for i, f in enumerate(filas):
                clave = str(f["id_rechazo"])
                registros[clave] = f
                modelo = f"{f['codigo_piston'] or '—'} · {f['modelo'] or ''}".strip(" ·")
                tv.insert("", "end", iid=clave, tags=tags_fila(i), values=(
                    _fecha_hora(f["fecha_rechazo"]), modelo, f["lote"], f["cantidad"],
                    f"{f['paso']}. {prod.PASOS[int(f['paso']) - 1]}", f["motivo"], f["responsable"] or f.get("usuario") or "—"))
            tot = prod.resumen_rechazos(filas)
            lb_mes.configure(text=f"{del_mes} pistón{'es' if del_mes != 1 else ''}")
            lb_tot.configure(text=f"{tot['piezas']} pistón{'es' if tot['piezas'] != 1 else ''}")
            lb_tot2.configure(text=f"{tot['registros']} registro{'s' if tot['registros'] != 1 else ''} · "
                                   f"{tot['lotes']} lote{'s' if tot['lotes'] != 1 else ''}")
            det.configure(text="" if filas else "No hay pistones rechazados definitivamente con estos filtros.")

        def limpiar():
            for campo_ in (f_desde, f_hasta):
                campo_.delete(0, "end")
            for clave, combo in cb.items():
                combo.set("Todas" if clave == "etapa" else "Todos")
            aplicar()

        def al_elegir(_e=None):
            sel = tv.selection()
            f = registros.get(sel[0]) if sel else None
            if f:
                det.configure(text=(f"Lote {f['lote']} · {f['cantidad']} pieza(s) rechazada(s) definitivamente. "
                                    f"Defectos: {f['defectos'] or '—'}.  Observaciones de la decisión: {f['observaciones'] or '—'}.  "
                                    f"Registrado por el usuario: {f['usuario'] or '—'}."))
        tv.bind("<<TreeviewSelect>>", al_elegir)
        f_desde.bind("<Return>", aplicar)
        f_hasta.bind("<Return>", aplicar)
        pie = transparente(card)
        pie.pack(fill="x", pady=(10, 0))
        Boton(pie, "Cerrar", d.destroy, "accion", ancho=110, alto=38).pack(side="right")
        aplicar()

    # ------------------------------------------------------------------ trazabilidad y control de calidad del lote
    def _trazabilidad(self):
        x = self._exi
        if not x.orden:
            return messagebox.showinfo("Trazabilidad", "No hay un lote seleccionado.", parent=self)
        try:
            t = prod.trazabilidad(x.orden["id_orden"])
        except Exception as ex:
            return messagebox.showerror("Trazabilidad", str(ex), parent=self)
        o, r = t["orden"], t["resumen"]
        d = Dialogo(self, "Trazabilidad del lote", 1060, 720, redim=True)
        card = d.cuerpo(18, scroll=True)
        titulo_seccion(card, f"Trazabilidad · Lote {o['lote']} · Orden {o['codigo_orden']}").pack(anchor="w")
        fin = _fecha_hora(o["fecha_fin"]) if o.get("fecha_fin") else "En producción"
        tenue(card, f"{_modelo(o)} · Responsable: {o.get('responsable') or '—'} · Inicio: {_fecha(o.get('fecha_inicio') or o.get('creada'))} · "
                    f"Finalización: {fin}", 12).pack(anchor="w", pady=(2, 0))
        tenue(card, f"Cantidad inicial: {o['cantidad_plan']} · Aprobadas: {r['aprobadas']} · Rechazadas: {r['rechazadas']} · "
                    f"Pendientes: {r['pendientes']} · Incorporadas al almacén: {int(o.get('aprobados_final') or 0) if o.get('liberada') else 0}"
                    + (f" · Cierre: {o['motivo_cierre']}" if o.get("motivo_cierre") else ""), 12).pack(anchor="w", pady=(2, 8))

        def seccion(texto, cols, enc, anchos, anclas, filas, alto):
            etiqueta(card, texto, 14, "bold").pack(anchor="w", pady=(10, 4))
            if not filas:
                return tenue(card, "Sin registros.", 12).pack(anchor="w")
            marco, tv = tabla(card, cols, enc, anchos, anclas, h_scroll=True)
            marco.pack(fill="x")
            tv.configure(height=min(max(len(filas), 1), alto))
            for i, f in enumerate(filas):
                tv.insert("", "end", tags=tags_fila(i), values=f)

        cols = ("paso", "estado", "rec", "proc", "apr", "rech", "pen", "motivo", "def", "obs", "resp", "fecha")
        enc = {"paso": "ETAPA", "estado": "ESTADO", "rec": "RECIB.", "proc": "PROC.", "apr": "APROB.", "rech": "RECH.", "pen": "PEND.",
               "motivo": "MOTIVO", "def": "DEFECTOS", "obs": "OBSERVACIONES", "resp": "RESPONSABLE", "fecha": "FECHA Y HORA"}
        anclas = {k: "center" for k in ("rec", "proc", "apr", "rech", "pen")}
        filas = []
        for e in t["etapas"]:
            if e["estado"] == "PENDIENTE" and not e.get("fecha_hora"):
                filas.append((f"{e['paso']}. {prod.PASOS[e['paso'] - 1]}", "Pendiente", "—", "—", "—", "—", "—", "", "", "", "", ""))
                continue
            piezas = e["paso"] >= prod.PRIMER_PASO_PIEZAS
            hecho = e["estado"] in prod.ESTADOS_COMPLETOS
            filas.append((f"{e['paso']}. {prod.PASOS[e['paso'] - 1]}", ESTADO_TXT[e["estado"]],
                          e["cant_recibida"] if piezas and e.get("cant_recibida") is not None else "—",
                          e["cant_procesada"] if piezas and e.get("cant_procesada") is not None else "—",
                          e["aprobados"] if piezas and hecho else "—", e["rechazados"] if piezas and hecho else "—",
                          prod.pendiente_vigente(e) if piezas and hecho else "—", e["motivo"] or e["bloqueo"] or "",
                          e.get("defectos") or "", e["observaciones"] or "", e.get("responsable") or "",
                          _fecha_hora(e["fecha_hora"]) if e.get("fecha_hora") else _fecha(e["fecha"]) if e["fecha"] else ""))
        seccion("Etapas y resultados de control de calidad", cols, enc, (190, 150, 55, 55, 60, 55, 55, 150, 160, 160, 110, 120), anclas, filas, 9)
        seccion("Productos no conformes del lote",
                ("fecha", "paso", "cant", "rec", "des", "motivo", "obs", "resp", "est"),
                {"fecha": "FECHA", "paso": "ETAPA", "cant": "CANT.", "rec": "RECUP.", "des": "DESCART.", "motivo": "MOTIVO",
                 "obs": "OBSERVACIONES", "resp": "RESPONSABLE", "est": "ESTADO"},
                (120, 190, 55, 60, 70, 170, 180, 110, 110), {"cant": "center", "rec": "center", "des": "center"},
                [(_fecha_hora(n["fecha_hora"]), f"{n['paso']}. {prod.PASOS[n['paso'] - 1]}", n["cantidad"], n["recuperadas"],
                  n["descartadas"], n["motivo"], n["observaciones"] or "", n["responsable"] or "—", prod.estado_nc(n))
                 for n in t["no_conformes"]], 6)
        seccion("Piezas en revisión del lote (retenidas y evaluadas)",
                ("paso", "ret", "apr", "rech", "vig", "est", "obs", "resp"),
                {"paso": "ETAPA", "ret": "RETENIDAS", "apr": "APROB.", "rech": "RECH.", "vig": "EN REVISIÓN", "est": "ESTADO",
                 "obs": "OBSERVACIONES", "resp": "RESPONSABLE"},
                (220, 80, 60, 60, 90, 120, 240, 110), {"ret": "center", "apr": "center", "rech": "center", "vig": "center"},
                [(f"{e['paso']}. {prod.PASOS[e['paso'] - 1]}", e["pendientes"], e["pend_aprobados"], e["pend_rechazados"],
                  prod.pendiente_vigente(e), prod.estado_revision(e), e["observaciones"] or "", e.get("responsable") or "—")
                 for e in t["revisiones"]], 4)
        seccion("Movimientos de materia prima",
                ("fecha", "tipo", "kg", "desc", "usr"), {"fecha": "FECHA", "tipo": "TIPO", "kg": "KG", "desc": "DESCRIPCIÓN", "usr": "USUARIO"},
                (130, 100, 80, 420, 110), {"kg": "center"},
                [(_fecha_hora(m["fecha_hora"]), m["tipo"], _kg(m["kg"]), m["descripcion"], m.get("usuario") or "—") for m in t["materia_prima"]], 4)
        seccion("Ingreso al almacén de productos terminados",
                ("fecha", "tipo", "cant", "ant", "nuevo", "motivo"),
                {"fecha": "FECHA", "tipo": "TIPO", "cant": "CANT.", "ant": "STOCK ANT.", "nuevo": "STOCK NUEVO", "motivo": "MOTIVO"},
                (130, 100, 60, 90, 90, 400), {"cant": "center", "ant": "center", "nuevo": "center"},
                [(_fecha_hora(m["fecha_hora"]), m["tipo"], m["cantidad"], m["stock_anterior"], m["stock_nuevo"], m["motivo"])
                 for m in t["stock"]], 4)
        seccion("Historial completo del lote",
                ("fecha", "mov", "cant", "est", "usr", "obs"),
                {"fecha": "FECHA", "mov": "MOVIMIENTO", "cant": "CANTIDAD", "est": "ESTADO", "usr": "USUARIO", "obs": "OBSERVACIONES"},
                (130, 260, 150, 100, 90, 300), {"cant": "center", "est": "center"},
                [(_fecha_hora(h["fecha_hora"]), h["movimiento"], h["cantidad"] or "—", h["estado"] or "—", h.get("usuario") or "—",
                  h["observaciones"] or "") for h in t["historial"]], 10)
        Boton(card, "Cerrar", d.destroy, "accion", alto=38).pack(fill="x", pady=(14, 0))
