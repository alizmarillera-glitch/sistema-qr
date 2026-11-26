import os, re, shutil, datetime, queue, threading, tkinter as tk
from decimal import Decimal
from tkinter import filedialog
from PIL import Image
import customtkinter as ctk
import conexion as db
from generador_etiqueta import crear_etiqueta
from escaneo_camara import escanear
from generador_qr import leer_codigo, leer_datos, datos_qr
from estilos import (C, MARCA_1, MARCA_2, MARCA_3, fuente, configurar_estilo, estilizar_tablas,
                     colorear_filas, modo_actual, guardar_modo)
from ui import (messagebox, Dialogo, Boton, Buscador, CampoTelefono, Combo, Contador, centrar, pantalla_completa, tarjeta, transparente, etiqueta, tenue,
                titulo_seccion, separador, insignia, campo, campo_solo_lectura, icono_boton, tabla, tags_fila,
                limitar_digitos, limitar_decimal, limitar_caracteres)
from tasa_bcv import obtener_tasa
from iconos import icono, foto_tk
from panel_ui import PanelMixin
from existencias_ui import ExistenciasMixin
import moneda as mon
import produccion_repo as prod
import marca
import busqueda
import tasas_repo
import ventas_repo
import empresa
import comprobante_pdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE, "imagenes_pistones")
FAC_DIR = os.path.join(BASE, "facturas")
IVA = Decimal("0.16")
TOL = Decimal("0.01")   # tolerancia de redondeo al cuadrar pagos (1 centavo)

# Datos del pistón que pide el formulario: los de la etiqueta física del producto.
# Cada sección es una lista de filas; una fila con un solo campo ocupa todo el ancho.
# El «Tipo de cabeza» (imagen del pistón) se elige en la tarjeta de la derecha del registro.
SECCIONES_PISTON = (
    ("1 · INFORMACIÓN GENERAL", (("codigo", "numero_piezas"), ("offset_mm", "fecha_fabricacion"))),
    ("2 · INFORMACIÓN DEL MOTOR", (("descripcion",), ("caracteristicas_adicionales",))),
    ("4 · MEDIDAS", (("diametro_mm", "diametro_cilindro_mm"),)),
    ("5 · TRAZABILIDAD", (("trazabilidad",),)),
)
# Datos que no van en la etiqueta: solo se muestran en la ficha para no perder lo que ya tenían los pistones antiguos.
SECCION_OTRAS_MEDIDAS = ("OTRAS MEDIDAS (OPCIONAL)", (("sobremedida_mm", "altura_compresion_mm"),
                                                      ("diametro_pasador_mm", "especificacion_camara")))
# (clave, título) en el orden en que se muestran en las fichas.
CAMPOS = [
    ("codigo", "Código del pistón"), ("descripcion", "Aplicación"),
    ("caracteristicas_adicionales", "Características adicionales"),
    ("numero_piezas", "Número de piezas"), ("offset_mm", "Offset"),
    ("fecha_fabricacion", "Fecha (automática)"), ("trazabilidad", "Trazabilidad"),
    ("diametro_mm", "Diámetro del pistón (mm)"), ("diametro_cilindro_mm", "Diámetro del cilindro (mm)"),
    ("sobremedida_mm", "Sobremedida (mm)"), ("altura_compresion_mm", "Altura de compresión (mm)"),
    ("diametro_pasador_mm", "Diámetro del pasador (mm)"), ("especificacion_camara", "Especificación de cámara"),
]
TITULOS = dict(CAMPOS)
# Campos numéricos: clave -> decimales. El cilindro admite 3 decimales (columna DECIMAL(10,3)).
CAMPOS_NUM = {"diametro_mm": 3, "diametro_cilindro_mm": 3, "sobremedida_mm": 2,
              "altura_compresion_mm": 2, "diametro_pasador_mm": 2}
# Longitud máxima de los textos (coincide con las columnas de MySQL).
LARGO_TEXTO = {"descripcion": 180, "caracteristicas_adicionales": 120, "offset_mm": 20, "trazabilidad": 80,
               "especificacion_camara": 180}
AYUDA_CAMPO = {
    "numero_piezas": "Piezas del pistón. Ej.: 4", "offset_mm": "Ej.: STD o 0.25",
    "fecha_fabricacion": "Se toma de la fecha del equipo",
    "descripcion": "Ej.: Chrysler 318 - V8 - 5.2 Lts", "caracteristicas_adicionales": "Ej.: A/C - C/R",
    "trazabilidad": "Ej.: 14Q", "diametro_mm": "Ej.: 100,789", "diametro_cilindro_mm": "Ej.: 100,822",
}
# Obligatorios al REGISTRAR un pistón nuevo (marcados con *).
OBLIGATORIOS_NUEVO = ("codigo", "descripcion", "numero_piezas", "diametro_mm")
# Métodos de pago que exigen número de referencia.
REQUIERE_REF = ("Zelle", "Pago móvil", "Transferencia")
# Moneda con la que normalmente se recibe cada método (se puede cambiar en el cuadro de pago).
MONEDA_POR_METODO = {"Zelle": "USD", "Divisa": "USD", "Pago móvil": "VES", "Bolívares": "VES"}

# Título y descripción que se muestran en la barra superior de cada pantalla.
PAGINAS = {
    "inicio": ("Resumen general", "Una vista rápida de tu operación y accesos directos."),
    "registro": ("Registrar pistón", "Comprueba el código y completa la ficha técnica."),
    "inventario": ("Inventario", "Administra referencias, disponibilidad y estado de los pistones."),
    "existencias": ("Existencias", "Seguimiento de producción por lotes, control de calidad e inventario"),
    "ventas": ("Nueva venta", "Agrega productos por código o con el escáner QR."),
    "facturas": ("Facturación", "Historial de facturas. Doble clic para ver el detalle."),
    "usuarios": ("Usuarios", "Administra accesos y roles del sistema."),
}


# Módulos a los que puede entrar cada rol; el resto responde «Acceso denegado». El menú lateral es el mismo para todos.
# Administrador: todos. Cajero: Resumen, Inventario (solo consulta), Ventas y Facturación. CONTROL: Resumen y Existencias.
MODULOS_ROL = {
    "Administrador": ("inicio", "registro", "inventario", "existencias", "ventas", "facturas", "usuarios"),
    "Cajero": ("inicio", "inventario", "ventas", "facturas"),
    prod.ROL_CONTROL: ("inicio", "existencias"),
}
MSG_SIN_PERMISO = "No tiene permisos para acceder a este módulo."
# Verde/rojo del estado activo/desactivado (los mismos de las etiquetas usr_activo / usr_inactivo de estilos.py): (claro, oscuro).
COLOR_ACTIVO = ("#0F8F5F", "#22C55E")
COLOR_INACTIVO = ("#D23F4E", "#F0505F")
ROLES = ("Administrador", "Cajero", prod.ROL_CONTROL)


def _txt(v):
    return "" if v is None else str(v)


def a_bs_o_none(usd, tasa):
    return mon.a_bs(usd, tasa) if tasa else None


def cargar_img(ruta, size):
    """Imagen escalada (manteniendo proporción) lista para un CTkLabel, o None si no existe."""
    try:
        im = Image.open(ruta)
        im.load()
        im.thumbnail(size)
        return ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
    except Exception:
        return None


def regenerar_etiqueta(p):
    """Genera QR + etiqueta y deja el QR vigente registrado en CODIGOS_QR."""
    qr, etq = crear_etiqueta(p)
    db.registrar_qr(p["id"], datos_qr(p), qr)
    return qr, etq


def _fecha_valida(txt):
    """DD/MM/AAAA (también DD-MM-AAAA o DD.MM.AA) o MM/AAAA -> texto normalizado."""
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})", txt)
    try:
        if m:
            d, mes, a = int(m[1]), int(m[2]), int(m[3])
            a += 2000 if a < 100 else 0
            datetime.date(a, mes, d)
            return f"{d:02d}/{mes:02d}/{a}"
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{4})", txt)
        if m and 1 <= int(m[1]) <= 12:
            return f"{int(m[1]):02d}/{m[2]}"
    except ValueError:
        pass
    raise ValueError("«Fecha» no es válida. Use el formato DD/MM/AAAA (ejemplo: 15/03/2025).")


def validar(v, nuevo=False, descripcion_actual=""):
    """Valida y normaliza los datos del pistón (los mismos de la etiqueta).

    ``nuevo=True`` (registro): exige código, aplicación, número de piezas y diámetro del pistón.
    ``nuevo=False`` (ficha): no exige datos que los pistones antiguos nunca tuvieron; si la aplicación queda
    vacía se conserva la descripción existente. En el registro la fecha es siempre la del equipo.
    """
    v = dict(v)
    for k in ("codigo", "descripcion", "caracteristicas_adicionales", "offset_mm", "trazabilidad",
              "especificacion_camara", "fecha_fabricacion"):
        v[k] = " ".join(str(v.get(k, "") or "").split())
        if k in LARGO_TEXTO and len(v[k]) > LARGO_TEXTO[k]:
            raise ValueError(f"«{TITULOS[k]}» admite como máximo {LARGO_TEXTO[k]} caracteres.")
    if nuevo:
        v["fecha_fabricacion"] = datetime.date.today().strftime("%d/%m/%Y")   # automática: la del equipo
    for k in (OBLIGATORIOS_NUEVO if nuevo else ("codigo",)):
        if not str(v.get(k, "") or "").strip():
            raise ValueError(f"«{TITULOS[k]}» es obligatorio.")

    bruto = str(v.get("numero_piezas", "") or "").strip()
    if not bruto:
        v["numero_piezas"] = None
    else:
        if not bruto.isdigit():
            raise ValueError("«Número de piezas» debe ser un número entero.")
        n = int(bruto)
        if n > 999999 or (nuevo and n < 1):
            raise ValueError("«Número de piezas» debe estar entre 1 y 999999.")
        v["numero_piezas"] = n

    for k, dec in CAMPOS_NUM.items():
        bruto = str(v.get(k, "") or "").strip().replace(",", ".")
        if bruto == "":
            v[k] = None
            continue
        try:
            n = round(float(bruto), dec)
        except ValueError:
            raise ValueError(f"«{TITULOS[k]}» debe ser un número (ejemplo: 100,789).")
        if n < 0 or n >= 10000 or (k == "diametro_mm" and nuevo and n == 0):
            raise ValueError(f"«{TITULOS[k]}» tiene un valor fuera de rango.")
        v[k] = n

    v["fecha_fabricacion"] = _fecha_valida(v["fecha_fabricacion"]) if v["fecha_fabricacion"] else None
    for k in ("offset_mm", "trazabilidad", "caracteristicas_adicionales", "especificacion_camara"):
        v[k] = v[k] or None
    if not v["descripcion"]:
        v["descripcion"] = " ".join(str(descripcion_actual or "").split())
    if not v["descripcion"]:
        raise ValueError("Indique la «Aplicación» (ejemplo: Chrysler 318 - V8 - 5.2 Lts).")
    return v


def construir_campos_piston(padre, valores=None, editable=True, obligatorios=(), extra=()):
    """Dibuja las secciones de datos del pistón (las de la etiqueta) dentro de ``padre``.

    Lo usan el registro de pistones y la ficha de edición. Devuelve un dict clave -> campo.
    ``extra`` agrega secciones al final (la ficha muestra ahí las medidas que no van en la etiqueta).
    La fecha nunca se escribe a mano: es la del equipo al registrar y se conserva al editar.
    """
    valores = valores or {}
    entradas = {}
    padre.grid_columnconfigure(0, weight=1, uniform="cp")
    padre.grid_columnconfigure(1, weight=1, uniform="cp")
    fila = 0
    for n, (titulo, filas) in enumerate(SECCIONES_PISTON + tuple(extra)):
        etiqueta(padre, titulo, 10, "bold", C["cobalto_txt"]).grid(
            row=fila, column=0, columnspan=2, sticky="w", pady=(0 if n == 0 else 18, 4))
        separador(padre).grid(row=fila + 1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        fila += 2
        for claves in filas:
            for j, k in enumerate(claves):
                solo = len(claves) == 1
                celda = transparente(padre)
                celda.grid(row=fila, column=j, columnspan=2 if solo else 1, sticky="ew",
                           padx=(0, 10) if (not solo and j == 0) else 0, pady=6)
                etiqueta(celda, TITULOS[k] + (" *" if k in obligatorios else ""), 12, "bold", C["muted"]).pack(anchor="w")
                ent = campo(celda, 200, AYUDA_CAMPO.get(k, ""))
                ent.pack(fill="x", pady=(4, 0))
                if valores.get(k) not in (None, ""):
                    ent.insert(0, str(valores[k]))
                # Los filtros se activan DESPUÉS de cargar el valor guardado: un dato antiguo nunca se descarta.
                if k == "numero_piezas":
                    limitar_digitos(ent, 6)
                elif k in CAMPOS_NUM:
                    limitar_decimal(ent, CAMPOS_NUM[k])
                if k in ("codigo", "fecha_fabricacion"):
                    ent.configure(state="readonly")
                elif not editable:
                    ent.configure(state="readonly", text_color=C["muted"])
                entradas[k] = ent
            fila += 1
    return entradas


def _mezcla(c1, c2, t):
    """Color intermedio entre dos '#RRGGBB'."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ============================================================================ LOGIN
# La pantalla de acceso vive en login_visual.py (diseño de recursos/login_fondo.png).
from login_visual import Login


# ============================================================================ APLICACIÓN
class App(PanelMixin, ExistenciasMixin, ctk.CTk):
    def __init__(self, usuario):
        super().__init__()
        self.user = usuario
        self.tasa = None            # tasa vigente en pantalla (dict) o None
        self._tasa_en_curso = False
        self.cerrar_sesion = False
        self.title(f"Manufacturas de Aluminio I, C.A. - {usuario['nombre']} ({usuario['rol']})")
        self.configure(fg_color=C["bg"])
        self.minsize(1280, 720)
        centrar(self, 1380, 840)
        pantalla_completa(self)
        estilizar_tablas(self)
        self.admin = usuario["rol"] == "Administrador"
        self.gestion_stock = self.admin     # gestión de producción y precios: solo el administrador
        self.es_control = usuario["rol"] == prod.ROL_CONTROL      # responsable de UNA etapa de producción
        self.modulos_permitidos = MODULOS_ROL.get(usuario["rol"], ("inicio",))
        self.nav_buttons = {}
        self.page_frames = {}
        self._construir_shell()
        self.mostrar_pagina("inicio")
        self.iniciar_tasa()

    # ------------------------------------------------------------ estructura
    def _construir_shell(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self._construir_sidebar()
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=C["border"]).grid(row=0, column=1, sticky="ns")
        self.content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.content.grid(row=0, column=2, sticky="nsew")
        self.content.grid_rowconfigure(1, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self._construir_topbar()
        self.page_host = transparente(self.content)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=32, pady=(4, 26))

        def pagina(clave, constructor):
            f = ctk.CTkFrame(self.page_host, fg_color="transparent", corner_radius=0)
            self.page_frames[clave] = f
            setattr(self, {"inicio": "t_home", "registro": "t_reg", "inventario": "t_inv", "existencias": "t_exi",
                           "ventas": "t_ven", "facturas": "t_fac", "usuarios": "t_usr"}[clave], f)
            constructor()

        pagina("inicio", self.ui_inicio)
        if self.admin:
            pagina("registro", self.ui_registro)
        pagina("inventario", self.ui_inventario)
        pagina("existencias", self.ui_existencias)
        pagina("ventas", self.ui_ventas)
        pagina("facturas", self.ui_facturas)
        if self.admin:
            pagina("usuarios", self.ui_usuarios)

    def mostrar_pagina(self, clave):
        """Muestra la pantalla elegida y refresca sus datos sin reiniciar el sistema."""
        if clave not in self.modulos_permitidos or clave not in self.page_frames:
            messagebox.showwarning("Acceso denegado", MSG_SIN_PERMISO, parent=self)
            return
        frame = self.page_frames[clave]
        for f in self.page_frames.values():
            f.pack_forget()
        frame.pack(fill="both", expand=True)
        titulo, sub = PAGINAS[clave]
        self._poner_titulo(titulo)
        self.lb_sub.configure(text=sub)
        for k, btn in self.nav_buttons.items():
            btn.seleccionar(k == clave)
        if clave == "inicio":
            self.actualizar_kpis()
        elif clave == "inventario":
            self.cargar_inv()
        elif clave == "existencias":
            self.cargar_movimientos()
        elif clave == "facturas":
            self.cargar_fac()
        elif clave == "usuarios":
            self.cargar_usuarios()

    def cambiar_modo(self):
        m = "dark" if self.sw_modo.get() else "light"
        ctk.set_appearance_mode(m)
        guardar_modo(m)
        estilizar_tablas(self)
        for nombre in ("tv", "tv_mov", "tv_v", "tv_f", "tv_u"):
            tv = getattr(self, nombre, None)
            if tv is not None:
                colorear_filas(tv)
        self._pintar_tasa()
        self.repintar_panel()

    def volver_inicio(self):
        if not messagebox.askyesno("Cerrar sesión", "¿Desea volver a la pantalla de inicio de sesión?", parent=self):
            return
        self.cerrar_sesion = True
        self.destroy()

    # ------------------------------------------------------------ RESUMEN
    # (ui_inicio, indicadores y gráficos: ver panel_ui.py)
    def abrir_ficha_por_id(self, id_piston):
        if "inventario" not in self.modulos_permitidos:        # la ficha pertenece al módulo Inventario
            return messagebox.showwarning("Acceso denegado", MSG_SIN_PERMISO, parent=self)
        Ficha(self, db.piston("p.id_piston=%s", (id_piston,)))

    # ------------------------------------------------------------ REGISTRO
    def ui_registro(self):
        cont = ctk.CTkScrollableFrame(self.t_reg, fg_color="transparent", corner_radius=0)
        cont.pack(fill="both", expand=True)
        self.codigo_busqueda = tk.StringVar()
        self.reg_codigo_card = tarjeta(cont)
        self.reg_codigo_card.pack(fill="x", pady=(0, 16))
        titulo_seccion(self.reg_codigo_card, "Código del pistón").pack(anchor="w", padx=22, pady=(20, 2))
        tenue(self.reg_codigo_card, "Introduce primero el código para comprobar que no esté registrado.", 12).pack(anchor="w", padx=22)
        fila = transparente(self.reg_codigo_card)
        fila.pack(fill="x", padx=22, pady=(12, 0))
        self.reg_codigo_entry = campo(fila, 340, textvariable=self.codigo_busqueda)
        self.reg_codigo_entry.pack(side="left")
        self._codigo_formateando = False
        self.reg_codigo_entry.bind("<KeyRelease>", self.formatear_codigo_piston)
        self.reg_codigo_entry.bind("<Return>", lambda _e: self.comprobar_codigo_piston())
        Boton(fila, "Comprobar código", self.comprobar_codigo_piston, "accion", ancho=170).pack(side="left", padx=(12, 0))
        self.reg_codigo_estado = tenue(self.reg_codigo_card, "Aún no se ha comprobado el código.", 12)
        self.reg_codigo_estado.pack(anchor="w", padx=22, pady=(10, 18))

        self.reg_form = transparente(cont)
        self.e = {}
        self.img_ruta = None
        self.reg_form_visible = False
        self.reg_codigo_entry.focus_set()

    def formatear_codigo_piston(self, event=None):
        """Prefijo EPV fijo; formato EPV-XXXXX-XXX-X con letras/números editables."""
        if self._codigo_formateando or (event and event.keysym in ("Left", "Right", "Home", "End", "Tab", "Shift_L", "Shift_R")):
            return
        raw = self.codigo_busqueda.get().upper().replace("EPV-", "", 1) if self.codigo_busqueda.get().upper().startswith("EPV-") else self.codigo_busqueda.get().upper()
        chars = "".join(ch for ch in raw if ch.isalnum())[:9]
        parts = [chars[:5]]
        if len(chars) > 5: parts.append(chars[5:8])
        if len(chars) > 8: parts.append(chars[8:9])
        formatted = "EPV-" + "-".join(parts)
        self._codigo_formateando = True
        self.codigo_busqueda.set(formatted)
        self.reg_codigo_entry.icursor("end")
        self._codigo_formateando = False

    def comprobar_codigo_piston(self):
        codigo = self.codigo_busqueda.get().strip().upper()
        if not codigo:
            return messagebox.showwarning("Código requerido", "Escriba el código del pistón.", parent=self)
        try:
            existente = db.consulta("SELECT id_piston AS id, codigo_piston AS codigo FROM pistones WHERE codigo_piston=%s", (codigo,), uno=True)
        except Exception as ex:
            return messagebox.showerror("Base de datos", f"No se pudo comprobar el código.\n\n{ex}", parent=self)
        if existente:
            self.reg_codigo_estado.configure(text=f"✕  El código «{codigo}» ya está registrado.", text_color=C["danger"])
            if self.reg_form_visible:
                self.reg_form.pack_forget()
                self.reg_form_visible = False
            messagebox.showwarning("Código duplicado", f"El pistón «{codigo}» ya está registrado.\nUse otro código.", parent=self)
            return
        self.reg_codigo_estado.configure(text=f"✓  El código «{codigo}» está disponible. Complete los datos de la etiqueta.",
                                         text_color=C["ok"])
        if not self.reg_form_visible:
            self._construir_formulario_piston()
            self.reg_form.pack(fill="both", expand=True, pady=(0, 10))
            self.reg_form_visible = True
        # Mantener sincronizado el código comprobado con el dato que se guardará.
        campo_solo_lectura(self.e["codigo"], codigo)

    def _construir_formulario_piston(self):
        for child in self.reg_form.winfo_children():
            child.destroy()
        self.reg_form.grid_columnconfigure(0, weight=1)
        card = tarjeta(self.reg_form)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        titulo_seccion(card, "Datos de la etiqueta").pack(anchor="w", padx=22, pady=(20, 0))
        tenue(card, "Estos son los datos que llevará la etiqueta del pistón. * Obligatorio.", 12).pack(anchor="w", padx=22)
        f = transparente(card)
        f.pack(fill="x", padx=22, pady=(10, 20))
        hoy = datetime.date.today().strftime("%d/%m/%Y")
        self.e = construir_campos_piston(f, {"fecha_fabricacion": hoy}, True, OBLIGATORIOS_NUEVO)
        campo_solo_lectura(self.e["codigo"], self.codigo_busqueda.get().strip())
        self.img_ruta = None

        der = tarjeta(self.reg_form)
        der.grid(row=0, column=1, sticky="nsew")
        titulo_seccion(der, "3 · TIPO DE CABEZA").pack(anchor="w", padx=22, pady=(20, 10))
        self.lb_img = ctk.CTkLabel(der, text="Imagen del pistón", width=300, height=200, corner_radius=14,
                                   fg_color=C["surface2"], text_color=C["muted"], font=fuente(12))
        self.lb_img.pack(padx=22)
        Boton(der, "Seleccionar imagen…", self.elegir_img, "accion").pack(fill="x", padx=22, pady=(12, 0))
        self.lbl_img_nombre = tenue(der, "Ninguna seleccionada", 11, wraplength=290)
        self.lbl_img_nombre.pack(anchor="w", padx=22, pady=(6, 0))
        separador(der).pack(fill="x", padx=22, pady=16)
        tenue(der, "La etiqueta, con el código QR del pistón, se genera al guardar.", 11, wraplength=290).pack(anchor="w", padx=22, pady=(0, 20))

        acciones = transparente(self.reg_form)
        acciones.grid(row=1, column=0, columnspan=2, sticky="e", pady=(16, 0))
        Boton(acciones, "Cancelar", self.limpiar, "accion", ancho=120).pack(side="left", padx=(0, 10))
        Boton(acciones, "Guardar y generar etiqueta", self.guardar_nuevo, "pri", ancho=240).pack(side="left")

    def elegir_img(self):
        r = filedialog.askopenfilename(filetypes=[("Imágenes", "*.jpg *.jpeg *.png")])
        if r:
            self.img_ruta = r
            self.ph = cargar_img(r, (300, 200))
            if self.ph:
                self.lb_img.configure(image=self.ph, text="")
            self.lbl_img_nombre.configure(text=os.path.basename(r))

    def limpiar(self):
        self.codigo_busqueda.set("")
        self.reg_codigo_estado.configure(text="Aún no se ha comprobado el código.", text_color=C["muted"])
        if self.reg_form_visible:
            self.reg_form.pack_forget()
            self.reg_form_visible = False
        self.img_ruta = None
        self.reg_codigo_entry.focus_set()

    def guardar_nuevo(self):
        codigo = self.codigo_busqueda.get().strip().upper()
        try:
            existente = db.consulta("SELECT id_piston AS id FROM pistones WHERE codigo_piston=%s", (codigo,), uno=True)
            if existente:
                self.reg_codigo_estado.configure(text=f"✕  El código «{codigo}» ya está registrado.", text_color=C["danger"])
                return messagebox.showwarning("Duplicado", "Ya existe un pistón con ese código.", parent=self)
            valores = {k: en.get().strip() for k, en in self.e.items()}
            valores["codigo"] = codigo
            v = validar(valores, nuevo=True)
        except ValueError as ex:
            return messagebox.showwarning("Datos", str(ex), parent=self)
        except Exception as ex:
            return messagebox.showerror("Base de datos", f"No se pudo validar el código.\n\n{ex}", parent=self)
        if not self.img_ruta:
            return messagebox.showwarning("Datos", "Debe seleccionar la imagen del pistón.", parent=self)
        os.makedirs(IMG_DIR, exist_ok=True)
        dest = os.path.join(IMG_DIR, v["codigo"] + os.path.splitext(self.img_ruta)[1].lower())
        shutil.copy(self.img_ruta, dest)
        v["imagen"] = dest
        try:
            v["id"] = db.crear_piston(v, self.user["id"])
            db.log(self.user["id"], "PISTON_CREADO", f"Pistón {v['codigo']}")
        except Exception as ex:
            return messagebox.showerror("No se pudo guardar", f"No se registró el pistón.\n\n{ex}", parent=self)
        etq = ""
        try:
            qr, etq = regenerar_etiqueta(v)
        except Exception as ex:
            messagebox.showwarning("Etiqueta", f"El pistón se guardó, pero no se pudo generar la etiqueta QR.\n\n{ex}\n\nSe reintentará al abrir el sistema.", parent=self)
        self.limpiar()
        messagebox.showinfo("Guardado", f"Pistón {v['codigo']} registrado correctamente.", parent=self)
        if etq:
            self.mostrar_etiqueta(v["codigo"], etq)

    def mostrar_etiqueta(self, codigo, ruta):
        """Vista de la etiqueta QR recién generada."""
        d = Dialogo(self, f"Etiqueta · {codigo}", 780, 640, modal=False, redim=True)
        c = d.cuerpo(22)
        titulo_seccion(c, f"Etiqueta generada · {codigo}").pack(anchor="w")
        tenue(c, "Se guardó en la carpeta etiquetas_generadas y está lista para imprimir.", 12).pack(anchor="w", pady=(2, 12))
        marco = tarjeta(c)
        marco.pack(fill="both", expand=True)
        ph = cargar_img(ruta, (700, 460))
        lbl = ctk.CTkLabel(marco, text="" if ph else "(no se pudo mostrar la etiqueta)", image=ph, text_color=C["muted"])
        lbl.pack(expand=True, padx=14, pady=14)
        Boton(c, "Cerrar", d.destroy, "pri", ancho=120).pack(anchor="e", pady=(14, 0))

    # ------------------------------------------------------------ INVENTARIO
    def ui_inventario(self):
        resumen = transparente(self.t_inv)
        resumen.pack(fill="x", pady=(0, 14))
        self.kpi_inv = {}
        for i, (clave, titulo, glifo, tono) in enumerate((
                ("referencias", "Referencias", "tag", "primary"), ("unidades", "Unidades en stock", "package", "ok"),
                ("bajos", "Con stock bajo", "triangle-alert", "warn"), ("desactivados", "Desactivados", "ban", "danger"))):
            resumen.grid_columnconfigure(i, weight=1, uniform="kpi_inv")
            self.kpi_inv[clave] = self._kpi_compacto(resumen, titulo, glifo, tono, i)

        top = tarjeta(self.t_inv)
        top.pack(fill="x", pady=(0, 14))
        # Solo la lupa identifica al buscador; la ayuda es breve y desaparece al escribir. Los resultados se
        # actualizan mientras se escribe, filtrando una copia en memoria (no se consulta la base en cada tecla).
        self.q = Buscador(top, "Código, marca, modelo, motor…", ancho=420, comando=lambda _t: self._pintar_inv())
        self.q.pack(side="left", padx=16, pady=14)
        self.lb_inv_info = tenue(top, "", 12)
        self.lb_inv_info.pack(side="left", padx=4)
        if self.admin:
            Boton(top, "Eliminar", self.eliminar_piston, "danger", ancho=110).pack(side="right", padx=(8, 16))
            # Interruptor del pistón elegido: verde = activo, rojo = desactivado (mismos tonos que el estado en Usuarios).
            self.sw_piston = ctk.CTkSwitch(top, text="", width=52, switch_width=46, switch_height=24,
                                           font=fuente(13, "bold"), fg_color=COLOR_INACTIVO, progress_color=COLOR_ACTIVO,
                                           button_color="#FFFFFF", button_hover_color="#F1F5F9",
                                           text_color=C["muted"], text_color_disabled=C["muted"],
                                           command=self.cambiar_estado_piston, state="disabled")
            self.sw_piston.pack(side="right", padx=(0, 8))

        cols = ("codigo", "descripcion", "diametro_mm", "sobremedida_mm", "stock", "precio_usd", "precio_bs", "estado")
        encabezados = {"codigo": "CÓDIGO", "descripcion": "DESCRIPCIÓN", "diametro_mm": "DIÁMETRO (MM)",
                       "sobremedida_mm": "SOBREMEDIDA (MM)", "stock": "STOCK",
                       "precio_usd": "PRECIO USD", "precio_bs": "PRECIO BS.", "estado": "ESTADO"}
        anchos = (135, 240, 105, 125, 70, 110, 140, 135)
        anclas = {c: ("w" if c in ("codigo", "descripcion") else "center") for c in cols}
        marco, self.tv = tabla(self.t_inv, cols, encabezados, anchos, anclas)
        marco.pack(fill="both", expand=True)
        self.tv.bind("<Double-1>", self.abrir_ficha)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._sincronizar_toggle())

    def _kpi_compacto(self, padre, titulo, glifo, tono, col):
        t = tarjeta(padre)
        t.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 7, 7 if col < 3 else 0))
        self._sello_icono(t, glifo, 44, 22, tono).pack(side="left", padx=(16, 12), pady=16)
        tx = transparente(t)
        tx.pack(side="left", pady=12)
        tenue(tx, titulo, 12).pack(anchor="w")
        lbl = etiqueta(tx, "—", 24, "bold")
        lbl.pack(anchor="w")
        return lbl

    def cargar_inv(self):
        """Relee el catálogo de la base de datos y lo muestra aplicando la búsqueda que haya escrita."""
        if not hasattr(self, "tv"): return
        self._cat_inv = db.consulta(db.SQL_PISTON + " ORDER BY p.codigo_piston")   # copia en memoria; la BD no se altera
        self._pintar_inv()
        # Las tarjetas resumen siempre usan el inventario completo, no solo la búsqueda.
        self.actualizar_kpis()

    def _pintar_inv(self):
        """Muestra el catálogo en memoria filtrado y ordenado según el buscador (sin consultar la base de datos)."""
        if not hasattr(self, "tv"): return
        catalogo = getattr(self, "_cat_inv", None)
        if catalogo is None:
            return self.cargar_inv()
        consulta = self.q.get().strip()
        filas, modo = busqueda.buscar(catalogo, consulta)      # lista nueva: el catálogo original no se reordena
        seleccionado = self.tv.focus()
        self.tv.delete(*self.tv.get_children())
        tasa = self.tasa_valor()
        for i, r in enumerate(filas):
            activo = bool(r.get("activo", 1))
            stock = int(r.get("stock", 0) or 0)
            bajo = activo and stock <= int(r.get("stock_minimo", 3) or 0)
            precio = mon.D(r.get("precio"))
            if precio > 0:
                p_usd, p_bs = mon.fmt_usd(precio), mon.fmt_bs(mon.a_bs(precio, tasa))
            else:
                p_usd, p_bs = "Sin precio", "—"
            self.tv.insert("", "end", iid=r["id"], values=(
                r["codigo"], r["descripcion"], _txt(r["diametro_mm"]) or "—", _txt(r["sobremedida_mm"]) or "—",
                stock, p_usd, p_bs, "● Activo" if activo else "● Desactivado"),
                tags=(tags_fila(i, "stock_bajo" if bajo else "")[0], "usr_activo" if activo else "usr_inactivo"))
        if seleccionado and self.tv.exists(seleccionado):         # conserva la fila elegida si sigue en los resultados
            self.tv.selection_set(seleccionado)
            self.tv.focus(seleccionado)
        total = len(catalogo)
        orden = "orden por código" if modo == busqueda.MODO_CODIGO else "orden alfabético"
        if not consulta:
            texto = f"{total} {'pistón' if total == 1 else 'pistones'}"
        elif filas:
            texto = f"{len(filas)} de {total}  ·  {orden}"
        else:
            texto = f"Sin resultados para «{consulta}»"
        self.lb_inv_info.configure(text=texto, text_color=C["muted"] if filas or not consulta else C["warn"])
        self._sincronizar_toggle()

    def _sincronizar_toggle(self):
        """Refleja en el interruptor el estado del pistón elegido: verde = activo, rojo = desactivado."""
        sw = getattr(self, "sw_piston", None)
        if sw is None:
            return
        sel = self.tv.focus()
        fila = next((r for r in getattr(self, "_cat_inv", None) or [] if str(r["id"]) == str(sel)), None) if sel else None
        sw.configure(state="normal")                     # select()/deselect() no actúan con el interruptor deshabilitado
        if fila is None:
            sw.deselect()
            sw.configure(state="disabled", fg_color=C["btn_borde"])
            return
        if fila.get("activo", 1):
            sw.select()
            pass
        else:
            sw.deselect()
            pass
        sw.configure(fg_color=COLOR_INACTIVO)

    def cambiar_estado_piston(self):
        """Acción del interruptor. Solo cambia ``pistones.activo``: no borra el pistón ni toca sus existencias;
        un pistón desactivado simplemente deja de poder venderse (Ventas y Facturación lo rechazan)."""
        if not self.admin:
            self._sincronizar_toggle()
            return messagebox.showwarning("Permiso denegado", "Solo el administrador puede cambiar el estado de un pistón.", parent=self)
        s = self.tv.focus()
        if not s:
            self._sincronizar_toggle()
            return messagebox.showwarning("Inventario", "Seleccione primero un pistón.", parent=self)
        p = db.piston("p.id_piston=%s", (s,))
        if not p:
            self.cargar_inv()
            return messagebox.showwarning("Inventario", "El pistón seleccionado ya no existe.", parent=self)
        nuevo = 1 if self.sw_piston.get() else 0         # lo que el usuario pidió al mover el interruptor
        if int(p.get("activo", 1) or 0) == nuevo:        # otro usuario ya lo había cambiado
            return self.cargar_inv()
        aviso = ("Podrá volver a venderse." if nuevo else
                 "No se eliminará ni cambiarán sus existencias; solo dejará de estar disponible para nuevas ventas.")
        if not messagebox.askyesno("Confirmar", f"¿Desea {'activar' if nuevo else 'desactivar'} el pistón {p['codigo']}?\n\n{aviso}", parent=self):
            return self._sincronizar_toggle()            # canceló: el interruptor vuelve a su posición
        db.consulta("UPDATE pistones SET activo=%s WHERE id_piston=%s", (nuevo, p["id"]), commit=True)
        db.log(self.user["id"], "PISTON_ESTADO", f"Pistón {p['codigo']} {'activado' if nuevo else 'desactivado'}")
        self.cargar_inv()
        messagebox.showinfo("Inventario", f"El pistón {p['codigo']} ahora está {'activo' if nuevo else 'desactivado'}.", parent=self)

    def eliminar_piston(self):
        # Solo administradores pueden eliminar registros. Se conserva el historial de ventas:
        # si el pistón aparece en una factura, no se permite borrarlo físicamente.
        if not self.admin:
            return messagebox.showwarning("Permiso denegado", "Solo el administrador puede eliminar pistones.", parent=self)
        s = self.tv.focus()
        if not s:
            return messagebox.showwarning("Inventario", "Seleccione primero el pistón que desea eliminar.", parent=self)
        p = db.piston("p.id_piston=%s", (s,))
        if not p:
            self.cargar_inv()
            return messagebox.showwarning("Inventario", "El pistón seleccionado ya no existe.", parent=self)
        vendido = db.consulta("SELECT id_detalle FROM detalle_factura WHERE id_piston=%s LIMIT 1", (p["id"],), uno=True)
        if vendido:
            return messagebox.showwarning(
                "No se puede eliminar",
                f"El pistón {p['codigo']} aparece en una o más facturas.\n\n"
                "Para proteger el historial de ventas, no se puede borrar este registro.",
                parent=self)
        confirmar = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Seguro que desea eliminar el pistón {p['codigo']}?\n\n"
            "Esta acción no se puede deshacer.",
            icon="warning", parent=self)
        if not confirmar:
            return
        try:
            db.eliminar_piston(p["id"])
            db.log(self.user["id"], "PISTON_ELIMINADO", f"Pistón {p['codigo']}")
        except Exception as e:
            return messagebox.showerror(
                "No se pudo eliminar",
                "No se pudo eliminar el pistón. Es posible que exista información relacionada.\n\n" + str(e),
                parent=self)
        self.cargar_inv()
        messagebox.showinfo("Inventario", f"El pistón {p['codigo']} fue eliminado.", parent=self)

    def abrir_ficha(self, _=None):
        sel = self.tv.focus()
        if sel: Ficha(self, db.piston("p.id_piston=%s", (sel,)))

    # ------------------------------------------------------------ EXISTENCIAS
    # La pantalla (ui_existencias, cargar_movimientos, órdenes de producción) está en existencias_ui.py.
    # Las existencias ya no se mueven a mano (sin entradas, salidas ni ajustes): suben al liberar un lote
    # (produccion_repo.completar_paso, paso 9) y bajan con las ventas (ventas_repo).
    # El precio de venta se modifica en Inventario (botón «Modificar precio» y ficha de cada pistón).
    def dialogo_precio(self, id_piston=None, al_guardar=None, padre=None):
        """Modifica el precio de venta (USD) del pistón elegido en Inventario (o el indicado por ``id_piston``).

        Usa db.establecer_precio: cierra el precio vigente y abre uno nuevo, de modo que Ventas y Facturación toman el
        precio nuevo y las facturas anteriores conservan el suyo.
        """
        padre = padre or self
        if not self.gestion_stock:
            return messagebox.showwarning("Permiso denegado", "No tiene permiso para cambiar precios.", parent=padre)
        pid = id_piston if id_piston is not None else (self.tv.focus() if hasattr(self, "tv") else "")
        if not pid:
            return messagebox.showwarning("Precio", "Seleccione primero un pistón de la lista.", parent=padre)
        p = db.piston("p.id_piston=%s", (pid,))
        if not p:
            self.cargar_inv()
            return messagebox.showwarning("Precio", "El pistón seleccionado ya no existe.", parent=padre)
        d = Dialogo(self, "Modificar precio de venta", 560, 560)
        card = d.cuerpo(26)
        titulo_seccion(card, "Modificar precio de venta").pack(anchor="w", pady=(0, 6))
        etiqueta(card, "Pistón", 12, "bold", C["muted"]).pack(anchor="w", pady=(8, 0))
        etiqueta(card, f"{p['codigo']} · {p['descripcion']}", 14, "bold", wraplength=480, justify="left").pack(anchor="w", pady=(3, 0))
        actual = mon.D(p.get("precio"))
        tenue(card, f"Precio actual: {mon.fmt_usd(actual)}" if actual > 0 else "Precio actual: sin precio asignado", 12).pack(anchor="w", pady=(2, 0))
        etiqueta(card, "Nuevo precio de venta (USD)", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        precio = campo(card, 200)
        if actual > 0:
            precio.insert(0, f"{actual:.2f}")
        precio.pack(anchor="w", pady=(5, 4))
        lb_bs = tenue(card, "", 12)
        lb_bs.pack(anchor="w", pady=(0, 6))

        def ayuda(_=None):
            tasa = self.tasa_valor()
            try: v = mon.parse_monto(precio.get())
            except ValueError: return lb_bs.configure(text="")
            lb_bs.configure(text=(f"Equivalente: {mon.fmt_bs(mon.a_bs(v, tasa))}  (tasa {mon.fmt_tasa(tasa)})" if tasa else "Equivalente en Bs.: no hay tasa disponible"))
        precio.bind("<KeyRelease>", ayuda); ayuda()

        try:    # últimos precios: el historial no se borra, solo se cierra la vigencia del anterior
            hist = db.consulta("SELECT precio_base, vigente_desde, vigente_hasta FROM precios_pistones WHERE id_piston=%s "
                               "ORDER BY vigente_desde DESC, id_precio DESC LIMIT 4", (p["id"],))
        except Exception:
            hist = []
        if hist:
            etiqueta(card, "Historial de precios", 12, "bold", C["muted"]).pack(anchor="w", pady=(8, 2))
            for h in hist:
                f = lambda v: v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else "—"
                tenue(card, f"{mon.fmt_usd(mon.D(h['precio_base']))}   ·   {f(h['vigente_desde'])} → "
                            f"{f(h['vigente_hasta']) if h.get('vigente_hasta') else 'vigente'}", 12).pack(anchor="w")

        def guardar():
            try: n = mon.q2(mon.parse_monto(precio.get()))
            except ValueError: return messagebox.showwarning("Precio", "Introduzca un precio numérico.", parent=d)
            if n <= 0: return messagebox.showwarning("Precio", "El precio debe ser mayor que cero.", parent=d)
            tasa = self.tasa_valor()
            try: db.establecer_precio(p["id"], n); db.log(self.user["id"], "PRECIO_ACTUALIZADO", f"{p['codigo']}: {p['precio']} -> {n} USD")
            except Exception as ex: return messagebox.showerror("Precio", str(ex), parent=d)
            d.destroy(); self.cargar_inv()
            if getattr(self, "carrito", None):      # una orden de venta abierta pasa a mostrar el precio vigente
                try: self._recargar_precios_carrito()
                except Exception: pass
            if al_guardar:
                try: al_guardar()
                except Exception: pass
            messagebox.showinfo("Precio actualizado", f"Precio de {p['codigo']} actualizado a {mon.fmt_usd(n)}" + (f" ({mon.fmt_bs(mon.a_bs(n, tasa))})" if tasa else "") + ". Las facturas anteriores no cambian.", parent=padre)
        Boton(card, "Guardar precio", guardar, "pri").pack(fill="x", pady=(14, 0))

    # ------------------------------------------------------------ VENTAS
    def ui_ventas(self):
        self.carrito = {}
        self.t_ven.grid_rowconfigure(1, weight=1)
        self.t_ven.grid_columnconfigure(0, weight=1)

        search = tarjeta(self.t_ven)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        etiqueta(search, "Código", 12, "bold", C["muted"]).pack(side="left", padx=(18, 8), pady=16)
        self.v_cod = campo(search, 240, "EPV-00000-000-0")
        self.v_cod.pack(side="left", pady=16)
        Boton(search, "Escanear QR", self.v_escanear, "accion", ancho=160, icono="scan-qr-code").pack(side="left", padx=10, pady=16)
        Boton(search, "Agregar a la orden", self.v_agregar, "accion", ancho=170).pack(side="right", padx=(10, 18), pady=16)
        self.v_cant = Contador(search, 1, 9999, 1, ancho=150)
        self.v_cant.pack(side="right", pady=16)
        etiqueta(search, "Cantidad", 12, "bold", C["muted"]).pack(side="right", padx=(0, 8), pady=16)
        self.v_cod.bind("<Return>", lambda e: self.v_agregar())

        columnas_venta = ("codigo", "descripcion", "cantidad", "precio_usd", "precio_bs", "importe_usd", "importe_bs")
        enc = {"codigo": "CÓDIGO", "descripcion": "DESCRIPCIÓN", "cantidad": "CANT.", "precio_usd": "PRECIO USD",
               "precio_bs": "PRECIO BS.", "importe_usd": "IMPORTE USD", "importe_bs": "IMPORTE BS."}
        anclas = {"codigo": "w", "descripcion": "w", "cantidad": "center", "precio_usd": "e", "precio_bs": "e",
                  "importe_usd": "e", "importe_bs": "e"}
        marco, self.tv_v = tabla(self.t_ven, columnas_venta, enc, (165, 200, 75, 110, 140, 125, 150), anclas)
        marco.grid(row=1, column=0, sticky="nsew")

        footer = tarjeta(self.t_ven)
        footer.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        footer.grid_columnconfigure(1, weight=1)
        izq = transparente(footer)
        izq.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="w")
        Boton(izq, "Quitar seleccionado", self.v_quitar, "accion", ancho=170, alto=38).pack(pady=(0, 8))
        Boton(izq, "Cancelar orden", self.cancelar_orden, "danger", ancho=170, alto=38).pack()
        medio = transparente(footer)
        medio.grid(row=0, column=1, sticky="ew", padx=10, pady=14)
        self.tot = {}
        for i, (clave, titulo, grande) in enumerate((("sub", "Subtotal", False), ("iva", f"IVA ({IVA:.0%})", False), ("tot", "TOTAL", True))):
            medio.grid_columnconfigure(i, weight=1, uniform="tot")
            col = transparente(medio)
            col.grid(row=0, column=i, sticky="w", padx=8)
            tenue(col, titulo, 12).pack(anchor="w")
            usd = etiqueta(col, "$0.00", 26 if grande else 18, "bold", C["primary"] if grande else C["text"])
            usd.pack(anchor="w")
            bs = tenue(col, "Bs. —", 12)
            bs.pack(anchor="w")
            self.tot[clave] = (usd, bs)
        self.lb_tasa_pie = tenue(medio, "", 11)
        self.lb_tasa_pie.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        Boton(footer, "CONTINUAR · FACTURAR", self.v_continuar, "pri", ancho=250, alto=58, tam=14).grid(
            row=0, column=2, padx=(8, 18), pady=16, sticky="e")
        self.v_refrescar()

    # ------------------------------------------------------------ TASA BCV
    def tasa_valor(self):
        """Tasa vigente (Decimal) o None si todavía no hay ninguna."""
        return self.tasa["valor"] if self.tasa else None

    def _pintar_tasa(self, consultando=False):
        if not hasattr(self, "lb_tasa"): return
        t = self.tasa
        if t is None:
            titulo, sub, color = "BCV  sin tasa", "Usa ↻ o «Manual»", C["danger"]
        else:
            f = t["fecha"].strftime("%d/%m/%Y") if hasattr(t["fecha"], "strftime") else str(t["fecha"])
            nota = {"en línea": "", "manual": "  ·  manual", "guardada": "  ·  sin verificar hoy"}.get(t["origen"], "")
            titulo = f"BCV  Bs. {mon.fmt_tasa(t['valor'])}"
            sub = f"USD{nota}"
            color = C["ok"] if t["origen"] == "en línea" else C["warn"]
        if consultando:
            sub = (sub + "  ·  " if sub else "") + "consultando…"
        self.lb_tasa.configure(text=titulo, text_color=C["text"])
        self.lb_tasa2.configure(text=sub)
        self.dot_tasa.configure(text_color=color)

    def iniciar_tasa(self):
        """Muestra de inmediato la última tasa guardada y consulta la oficial en segundo plano."""
        try:
            t = tasas_repo.ultima_tasa()
        except Exception:
            t = None
        if t:
            manual = "manual" in str(t["fuente"]).lower()
            self.tasa = {"valor": mon.D(t["tasa"]), "fecha": t["fecha_efectiva"], "fuente": t["fuente"],
                         "origen": "manual" if manual else "guardada", "consulta": t.get("fecha_consulta")}
        self._tasa_actualizada()
        self._ciclo_tasa()

    def _ciclo_tasa(self):
        self.refrescar_tasa(silencioso=True)
        self.after(30 * 60 * 1000, self._ciclo_tasa)

    def refrescar_tasa(self, silencioso=False):
        """Consulta la tasa BCV sin congelar la ventana y actualiza TODAS las pantallas al recibirla."""
        if self._tasa_en_curso:
            return
        self._tasa_en_curso = True
        self._pintar_tasa(consultando=True)
        cola = queue.Queue()

        def trabajo():
            try:
                cola.put(("ok", obtener_tasa()))
            except Exception as ex:
                cola.put(("error", ex))

        def sondear():
            try:
                estado, dato = cola.get_nowait()
            except queue.Empty:
                self.after(250, sondear)
                return
            self._tasa_en_curso = False
            if estado == "ok":
                valor, fecha, fuente = dato
                try:
                    tasas_repo.guardar_tasa(valor, fecha, fuente)
                except Exception:
                    pass
                self.tasa = {"valor": mon.D(valor), "fecha": fecha, "fuente": fuente, "origen": "en línea",
                             "consulta": datetime.datetime.now()}
                self._tasa_actualizada()
            else:
                self._pintar_tasa()
                if not silencioso:
                    messagebox.showwarning("Tasa BCV", f"{dato}\n\nPuede ingresar la tasa publicada en bcv.org.ve con el botón «Manual».", parent=self)

        threading.Thread(target=trabajo, daemon=True).start()
        self.after(250, sondear)

    def _tasa_actualizada(self):
        """Redibuja todo lo que muestra importes en Bs. cuando cambia la tasa."""
        self._pintar_tasa()
        try:
            self.cargar_inv()
        except Exception:
            pass
        if hasattr(self, "tv_v"):
            self.v_refrescar()

    def dialogo_tasa_manual(self):
        d = Dialogo(self, "Tasa BCV manual", 520, 340)
        card = d.cuerpo(26)
        titulo_seccion(card, "Ingresar la tasa manualmente").pack(anchor="w")
        tenue(card, "Escriba los Bs. por 1 USD publicados hoy en bcv.org.ve.\nQuedará guardada en el historial y se usará en todo el sistema.",
              12, justify="left").pack(anchor="w", pady=(4, 14))
        e = campo(card, 240)
        e.pack(anchor="w")
        if self.tasa: e.insert(0, f"{self.tasa['valor']:.4f}")
        e.focus_set()

        def guardar():
            try:
                v = mon.parse_monto(e.get())
            except ValueError as ex:
                return messagebox.showwarning("Tasa", str(ex), parent=d)
            if v <= 0:
                return messagebox.showwarning("Tasa", "La tasa debe ser mayor que cero.", parent=d)
            prev = self.tasa_valor()
            if prev and abs(v / prev - 1) > Decimal("0.5") and not messagebox.askyesno(
                    "Confirmar tasa", f"La tasa ingresada ({mon.fmt_tasa(v)}) difiere mucho de la actual ({mon.fmt_tasa(prev)}).\n¿Es correcta?", parent=d):
                return
            hoy = datetime.date.today()
            fuente = f"Manual (ingresada por {self.user['nombre']})"
            try:
                tasas_repo.guardar_tasa(v, hoy, fuente)
            except Exception as ex:
                return messagebox.showerror("Tasa", f"No se pudo guardar la tasa.\n\n{ex}", parent=d)
            self.tasa = {"valor": v, "fecha": hoy, "fuente": fuente, "origen": "manual", "consulta": datetime.datetime.now()}
            db.log(self.user["id"], "TASA_MANUAL", f"Tasa manual {mon.fmt_tasa(v)} Bs/USD")
            d.destroy(); self._tasa_actualizada()
        Boton(card, "Guardar tasa", guardar, "pri").pack(fill="x", pady=(18, 0))
        e.bind("<Return>", lambda _e: guardar())

    def _tasa_lista_para_facturar(self):
        """True si hay una tasa aceptable para facturar; si no, orienta al usuario."""
        t = self.tasa
        if t is None:
            if messagebox.askyesno("Tasa BCV", "No hay tasa BCV disponible y no se puede emitir la factura sin ella.\n\n¿Desea ingresarla manualmente ahora?", parent=self):
                self.dialogo_tasa_manual()
            else:
                self.refrescar_tasa()
            return False
        consulta = t.get("consulta")
        hoy = datetime.date.today()
        vigente = t["origen"] == "en línea" or (t["origen"] == "manual" and consulta and consulta.date() == hoy)
        if vigente:
            return True
        f = t["fecha"].strftime("%d/%m/%Y") if hasattr(t["fecha"], "strftime") else str(t["fecha"])
        if messagebox.askyesno("Tasa BCV sin verificar", f"No se pudo verificar la tasa de hoy en línea.\nLa última guardada es Bs. {mon.fmt_tasa(t['valor'])} (fecha {f}).\n\n¿Desea facturar con esa tasa?\n(Elija «No» para volver a intentar la consulta o ingresarla con el botón «Manual».)", parent=self):
            return True
        self.refrescar_tasa()
        return False

    # ------------------------------------------------------------ VENTAS: acciones
    def v_escanear(self):
        t = escanear()
        if not t:
            return messagebox.showinfo("Escaneo", "No se leyó ningún QR (o no hay cámara).", parent=self)
        datos = leer_datos(t); codigo = datos.get("codigo") or leer_codigo(t)
        if not codigo:
            return messagebox.showwarning("QR", "El código QR no contiene un código de pistón válido.", parent=self)
        p = db.piston("p.codigo_piston=%s", (codigo,))
        if not p:
            return messagebox.showwarning("QR", f"El pistón {codigo} no existe en el inventario.", parent=self)
        if not p.get("activo", 1):
            return messagebox.showwarning("Pistón desactivado", f"El pistón {codigo} está desactivado y no se puede vender.", parent=self)
        self.mostrar_detalle_piston(p, datos)
        self.v_cod.delete(0, "end"); self.v_cod.insert(0, codigo); self.v_agregar()

    def mostrar_detalle_piston(self, p, datos=None):
        """Ficha del pistón leída desde el QR.

        Estructura: cabecera fija + cuerpo desplazable + pie fijo con «Continuar». Así el botón y el título
        siempre se ven y los datos nunca quedan cortados, sea cual sea el alto de la ventana o la cantidad de datos.
        """
        w = Dialogo(self, f"Ficha del pistón {p['codigo']}", 900, 660, redim=True)
        w.minsize(640, 420)
        c = w.cuerpo(24)

        # --- cabecera fija
        etiqueta(c, f"PISTÓN · {p['codigo']}", 24, "bold").pack(anchor="w")
        tenue(c, "Información recuperada del código QR", 12).pack(anchor="w", pady=(2, 12))

        # --- pie fijo (se empaqueta antes del cuerpo para que siempre conserve su espacio)
        pie = transparente(c)
        pie.pack(side="bottom", fill="x", pady=(14, 0))
        Boton(pie, "Continuar", w.destroy, "pri", ancho=140).pack(side="right")

        # --- cuerpo con desplazamiento vertical
        body = ctk.CTkScrollableFrame(c, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        left = tarjeta(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 4))
        right = tarjeta(body)
        right.grid(row=0, column=1, sticky="nsew", pady=(0, 4))

        valores = []          # etiquetas de texto largo: su ajuste de línea sigue el ancho de la tarjeta
        for k, titulo in CAMPOS:
            etiqueta(left, titulo.upper(), 10, "bold", C["muted"]).pack(anchor="w", padx=20, pady=(10, 0))
            lb = etiqueta(left, _txt(p.get(k)) or "—", 14, wraplength=380, justify="left")
            lb.pack(anchor="w", padx=20)
            valores.append(lb)
        pr = mon.D(p.get("precio")); tasa = self.tasa_valor()
        etiqueta(left, "PRECIO DE VENTA", 10, "bold", C["muted"]).pack(anchor="w", padx=20, pady=(12, 0))
        lb_precio = etiqueta(left, (mon.fmt_usd(pr) + "   ·   " + mon.fmt_bs(a_bs_o_none(pr, tasa)) if pr > 0 else "Sin precio asignado"),
                             16, "bold", C["primary"], wraplength=380, justify="left")
        lb_precio.pack(anchor="w", padx=20, pady=(0, 16))
        valores.append(lb_precio)

        ultimo = {"ancho": 0}

        def ajustar_texto(e=None):
            ancho = left.winfo_width() - 44
            if ancho < 120 or abs(ancho - ultimo["ancho"]) < 4:
                return
            ultimo["ancho"] = ancho
            for lb in valores:
                lb.configure(wraplength=ancho)

        left.bind("<Configure>", ajustar_texto)

        ph = cargar_img(p.get("imagen", ""), (300, 280))
        if ph:
            ctk.CTkLabel(right, text="", image=ph).pack(padx=18, pady=18, anchor="n")
        else:
            tenue(right, "(sin imagen)", 12).pack(padx=70, pady=100)

    def v_agregar(self):
        cod = self.v_cod.get().strip(); p = db.piston("p.codigo_piston=%s", (cod,))
        if not p: return messagebox.showwarning("Venta", "Código no encontrado.", parent=self)
        if not p.get("activo", 1): return messagebox.showwarning("Venta", "Este pistón está desactivado y no se puede agregar a una venta.", parent=self)
        if mon.D(p.get("precio")) <= 0:
            return messagebox.showwarning("Venta", f"El pistón {p['codigo']} no tiene precio de venta.\nAsígnelo en Inventario → «Modificar precio».", parent=self)
        try: n = int(self.v_cant.get()); assert n > 0
        except Exception: return messagebox.showwarning("Venta", "Cantidad inválida.", parent=self)
        ya = self.carrito.get(p["id"], {}).get("cant", 0)
        if ya + n > p["stock"]: return messagebox.showwarning("Stock", f"Stock insuficiente (disponible: {p['stock']}).", parent=self)
        self.carrito[p["id"]] = {"p": p, "cant": ya + n}; self.v_cod.delete(0, "end"); self.v_cant.set(1); self.v_refrescar()

    def v_quitar(self):
        s = self.tv_v.focus()
        if s: self.carrito.pop(int(s), None); self.v_refrescar()

    def cancelar_orden(self):
        """Vacía la orden actual y deja la pantalla de ventas lista para una nueva venta."""
        if not self.carrito:
            return
        if messagebox.askyesno("Cancelar orden", "¿Desea cancelar la orden actual?", parent=self):
            self.carrito.clear()
            self.v_refrescar()
            self.v_cod.focus_set()

    def v_refrescar(self):
        self.tv_v.delete(*self.tv_v.get_children())
        tasa = self.tasa_valor()
        sub = Decimal("0")
        for n, (i, it) in enumerate(self.carrito.items()):
            precio = mon.q2(it["p"]["precio"])
            cantidad = int(it["cant"])
            importe = mon.q2(precio * cantidad)
            sub += importe
            self.tv_v.insert("", "end", iid=i, values=(
                it["p"]["codigo"], it["p"].get("descripcion", ""), cantidad,
                mon.fmt_usd(precio), mon.fmt_bs(mon.a_bs(precio, tasa)),
                mon.fmt_usd(importe), mon.fmt_bs(mon.a_bs(importe, tasa))), tags=tags_fila(n))
        iva = mon.q2(sub * IVA)
        total = sub + iva
        s_bs, i_bs, t_bs = mon.desglose_bs(sub, iva, tasa)
        for clave, usd, bs in (("sub", sub, s_bs), ("iva", iva, i_bs), ("tot", total, t_bs)):
            self.tot[clave][0].configure(text=mon.fmt_usd(usd))
            self.tot[clave][1].configure(text=mon.fmt_bs(bs, sin_tasa="Bs. —"))
        if tasa:
            f = self.tasa["fecha"].strftime("%d/%m/%Y") if hasattr(self.tasa["fecha"], "strftime") else str(self.tasa["fecha"])
            pie = f"Tasa BCV: {mon.fmt_tasa(tasa)} Bs./USD · Fecha: {f}"
        else:
            pie = "Sin tasa BCV: use «↻» o «Manual» (arriba) antes de facturar."
        self.lb_tasa_pie.configure(text=pie)

    # ------------------------------------------------------------ VENTAS: cliente y cobro
    def v_continuar(self):
        if not self.carrito:
            return messagebox.showwarning("Venta", "La orden está vacía.", parent=self)
        if not self._tasa_lista_para_facturar():
            return

        d = Dialogo(self, "Identificar cliente", 660, 780)
        card = d.cuerpo(26, scroll=True)
        cab = transparente(card)
        cab.pack(anchor="w")
        self._sello_icono(cab, "id-card", 40, 22, "primary").pack(side="left", padx=(0, 12))
        etiqueta(cab, "Datos del cliente", 24, "bold").pack(side="left")
        tenue(card, "Seleccione el tipo de documento y consulte si el cliente ya está registrado.", 12,
              wraplength=560, justify="left").pack(anchor="w", pady=(2, 10))

        etiqueta(card, "Tipo de documento", 12, "bold", C["muted"]).pack(anchor="w", pady=(8, 0))
        tipo = Combo(card, values=("V — Cédula venezolana", "E — Cédula de extranjero",
                                   "J — RIF jurídico", "P — Pasaporte"), ancho=560)
        tipo.pack(fill="x", pady=(5, 0))
        etiqueta(card, "Número de documento", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        doc_entry = campo(card, 560)
        doc_entry.pack(fill="x", pady=(5, 0))
        buscar_btn = Boton(card, "Buscar cliente", None, "accion")
        buscar_btn.pack(fill="x", pady=(12, 0))

        estado = tenue(card, "Introduzca el documento y pulse Buscar cliente.", 12, wraplength=560, justify="left")
        estado.pack(anchor="w", pady=(10, 4))
        separador(card).pack(fill="x", pady=(6, 4))

        campos_cliente = {}
        labels = (("codigo", "Código del cliente"), ("nombre", "Nombre / razón social"),
                  ("direccion_fiscal", "Dirección fiscal"), ("telefono", "Teléfono"),
                  ("correo", "Correo (opcional)"))
        for clave, titulo in labels:
            etiqueta(card, titulo, 12, "bold", C["muted"]).pack(anchor="w", pady=(10, 0))
            if clave == "telefono":
                # [ 0412 ▼ ] [ 1234567 ]: prefijo desplegable + siete dígitos; se guarda el número completo.
                ent = CampoTelefono(card, ancho=560)
                ent.pack(fill="x", pady=(5, 0))
                ent.estado("disabled")
            else:
                ent = campo(card, 560)
                ent.pack(fill="x", pady=(5, 0))
                ent.configure(state="disabled")
            campos_cliente[clave] = ent

        estado_factura = tenue(card, "", 12)
        estado_factura.pack(anchor="w", pady=(12, 0))
        btn_facturar = Boton(card, "Buscar cliente primero", None, "pri", alto=48)
        btn_facturar.pack(fill="x", pady=(6, 0))
        btn_facturar.configure(state="disabled")

        contexto = {"consultado": False, "cliente": None, "tipo": None, "documento": None}

        def tipo_codigo():
            seleccion = tipo.get().strip()
            return seleccion.split(" ", 1)[0] if seleccion else ""

        def poner_campos(datos=None, editable=False):
            datos = datos or {}
            for clave, ent in campos_cliente.items():
                if clave == "telefono":      # recupera el prefijo y los siete dígitos de un teléfono guardado
                    ent.set(datos.get("telefono"))
                    ent.estado("normal" if editable else "disabled")
                    continue
                ent.configure(state="normal")
                ent.delete(0, "end")
                if datos.get(clave) is not None:
                    ent.insert(0, str(datos.get(clave, "")))
                if not editable or clave == "codigo":
                    ent.configure(state="readonly" if datos.get(clave) else "disabled")
            if editable:
                campo_solo_lectura(campos_cliente["codigo"], "Se asignará al guardar")

        def buscar_cliente():
            tipo_doc = tipo_codigo()
            documento = doc_entry.get().strip()
            if not documento:
                return messagebox.showwarning("Documento requerido", "Escriba el número de documento.", parent=d)
            try:
                # En el modelo relacional el documento es único por sí solo (CLIENTES.documento).
                cliente = db.consulta(
                    "SELECT id_cliente, CONCAT('CLI-', LPAD(id_cliente, 6, '0')) AS codigo, tipo_documento, documento, "
                    "nombre_razon_social AS nombre, direccion AS direccion_fiscal, telefono, correo "
                    "FROM clientes WHERE documento=%s",
                    (documento,), uno=True)
            except Exception as ex:
                return messagebox.showerror("Base de datos",
                    f"No se pudo consultar el cliente.\nCompruebe que la actualización de la base de datos se haya aplicado.\n\n{ex}", parent=d)

            if cliente:
                tipo_doc = cliente["tipo_documento"]
            contexto.update({"consultado": True, "cliente": cliente, "tipo": tipo_doc, "documento": documento})
            if cliente:
                poner_campos(cliente, editable=False)
                estado.configure(text="✓  Cliente encontrado. Sus datos se han recuperado de la base de datos.", text_color=C["ok"])
                btn_facturar.configure(text="Generar factura", state="normal")
            else:
                poner_campos({"codigo": "", "nombre": "", "direccion_fiscal": "", "telefono": "", "correo": ""}, editable=True)
                estado.configure(text="Cliente no registrado. Complete los datos para guardarlo y continuar.", text_color=C["warn"])
                btn_facturar.configure(text="Registrar cliente y generar factura", state="normal")

        def iniciar_factura():
            if not contexto["consultado"]:
                return messagebox.showwarning("Consulta requerida", "Primero busque el cliente.", parent=d)
            tipo_doc = contexto["tipo"]
            documento = contexto["documento"]
            cliente_existente = contexto["cliente"]
            nombre = campos_cliente["nombre"].get().strip()
            direccion = campos_cliente["direccion_fiscal"].get().strip()
            telefono = campos_cliente["telefono"].get().strip()
            correo = campos_cliente["correo"].get().strip() or None
            if not nombre:
                return messagebox.showwarning("Datos incompletos", "El nombre o razón social es obligatorio.", parent=d)
            if not direccion:
                return messagebox.showwarning("Datos incompletos", "La dirección fiscal es obligatoria.", parent=d)
            if not telefono:
                return messagebox.showwarning("Datos incompletos", "El teléfono es obligatorio.", parent=d)
            if not cliente_existente:        # cliente nuevo: el número debe estar completo (prefijo + 7 dígitos)
                err_tel = campos_cliente["telefono"].error()
                if err_tel:
                    return messagebox.showwarning("Teléfono incompleto", err_tel, parent=d)

            btn_facturar.configure(state="disabled")
            estado_factura.configure(text="Guardando datos y preparando factura…")
            try:
                if not cliente_existente:
                    cliente_id = ventas_repo.guardar_cliente(tipo_doc, documento, nombre, direccion, telefono, correo)
                    codigo_cliente = f"CLI-{cliente_id:06d}"
                    contexto["cliente"] = {"id_cliente": cliente_id, "codigo": codigo_cliente}
                else:
                    cliente_id = cliente_existente["id_cliente"]
                    codigo_cliente = cliente_existente.get("codigo", "")
                estado_factura.configure(text=f"Cliente {codigo_cliente or ''} validado. Registre el pago…")
            except Exception as ex:
                btn_facturar.configure(state="normal")
                estado_factura.configure(text="")
                return messagebox.showerror("No se pudo guardar el cliente",
                    f"Verifique si el documento ya fue registrado.\n\n{ex}", parent=d)

            self.dialogo_pago(cliente_id, d, btn_facturar, estado_factura)

        buscar_btn.configure(command=buscar_cliente)
        btn_facturar.configure(command=iniciar_factura)

        def reiniciar(texto):
            contexto.update({"consultado": False, "cliente": None, "tipo": None, "documento": None})
            poner_campos()
            estado.configure(text=texto, text_color=C["muted"])
            btn_facturar.configure(state="disabled", text="Buscar cliente primero")
            estado_factura.configure(text="")

        def cambio_tipo(_valor=None):
            reiniciar("Tipo de documento cambiado. Vuelva a buscar el cliente.")

        def cambio_documento(_event=None):
            if contexto["consultado"]:
                reiniciar("El documento cambió. Vuelva a buscar el cliente.")

        tipo.al_cambiar(cambio_tipo)
        doc_entry.bind("<KeyRelease>", cambio_documento)
        doc_entry.bind("<Return>", lambda _e: buscar_cliente())
        doc_entry.focus_set()

    def dialogo_pago(self, cliente_id, dialogo_padre, boton, estado):
        """Registra cómo se paga la factura. Admite pagos mixtos, cada uno en USD o en Bs."""
        tasa = self.tasa_valor()
        sub = sum((mon.q2(it["p"]["precio"]) * it["cant"] for it in self.carrito.values()), Decimal("0"))
        iva = mon.q2(sub * IVA); total = sub + iva
        _sbs, _ibs, total_bs = mon.desglose_bs(sub, iva, tasa)

        def abortar(msg=None):
            boton.configure(state="normal"); estado.configure(text="")
            if msg:
                messagebox.showerror("Pago", msg, parent=dialogo_padre)

        if not tasa:
            return abortar("No hay tasa BCV disponible. Use «↻» o «Manual» e inténtelo de nuevo.")
        try:
            metodos = db.consulta("SELECT id_metodo_pago AS id, nombre_metodo AS nombre FROM metodo_pago "
                                  "WHERE estado=1 ORDER BY id_metodo_pago")
        except Exception as ex:
            return abortar(f"No se pudieron cargar los métodos de pago.\n\n{ex}")
        if not metodos:
            return abortar("No hay métodos de pago activos en la base de datos.")

        d = Dialogo(self, "Registrar pago", 800, 840)
        card = d.cuerpo(26, scroll=True)
        etiqueta(card, "Registrar pago", 24, "bold").pack(anchor="w")
        banner = ctk.CTkFrame(card, fg_color=C["primary_soft"], corner_radius=16)
        banner.pack(fill="x", pady=(10, 14))
        tenue(banner, "TOTAL A COBRAR", 11).pack(anchor="w", padx=20, pady=(14, 0))
        etiqueta(banner, f"{mon.fmt_usd(total)} USD   ·   {mon.fmt_bs(total_bs)}", 22, "bold", C["primary"]).pack(anchor="w", padx=20)
        tenue(banner, f"Tasa BCV aplicada: Bs. {mon.fmt_tasa(tasa)} por USD", 12).pack(anchor="w", padx=20, pady=(0, 14))

        form = tarjeta(card)
        form.pack(fill="x", pady=(0, 12))
        g = transparente(form)
        g.pack(fill="x", padx=20, pady=18)
        g.grid_columnconfigure(0, weight=1, uniform="pago")
        g.grid_columnconfigure(1, weight=1, uniform="pago")
        OPC_USD, OPC_VES = "USD  ($)", "Bs.  (bolívares)"
        etiqueta(g, "Método de pago", 12, "bold", C["muted"]).grid(row=0, column=0, sticky="w")
        metodo = Combo(g, values=[m["nombre"] for m in metodos], ancho=300)
        metodo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(5, 10))
        etiqueta(g, "Moneda recibida", 12, "bold", C["muted"]).grid(row=0, column=1, sticky="w")
        moneda = Combo(g, values=[OPC_USD, OPC_VES], ancho=300)
        moneda.grid(row=1, column=1, sticky="ew", pady=(5, 10))
        etiqueta(g, "Monto recibido", 12, "bold", C["muted"]).grid(row=2, column=0, sticky="w")
        monto = campo(g, 300)
        monto.grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=(5, 0))
        lb_eq = tenue(g, "", 12)
        lb_eq.grid(row=4, column=0, sticky="w", pady=(3, 0))
        etiqueta(g, "Referencia", 12, "bold", C["muted"]).grid(row=2, column=1, sticky="w")
        ref = campo(g, 300)
        ref.grid(row=3, column=1, sticky="ew", pady=(5, 0))
        lb_ref = tenue(g, "", 12)
        lb_ref.grid(row=4, column=1, sticky="w", pady=(3, 0))
        btn_add = Boton(g, "Agregar pago", None, "accion")
        btn_add.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        heads = {"metodo": "MÉTODO", "moneda": "MONEDA", "monto": "MONTO RECIBIDO", "equiv": "EQUIVALE EN USD", "ref": "REFERENCIA"}
        marco, tv = tabla(card, ("metodo", "moneda", "monto", "equiv", "ref"), heads, (140, 75, 130, 130, 200),
                          {"metodo": "w", "moneda": "center", "monto": "e", "equiv": "e", "ref": "w"})
        tv.configure(height=5)
        marco.pack(fill="x")
        lb_res = etiqueta(card, "", 14, "bold")
        lb_res.pack(anchor="w", pady=(12, 4))
        fila = transparente(card)
        fila.pack(fill="x", pady=(4, 0))
        btn_quitar = Boton(fila, "Quitar seleccionado", None, "accion", ancho=180, alto=38)
        btn_quitar.pack(side="left")
        btn_cancel = Boton(fila, "Cancelar", None, "ghost", ancho=110, alto=38)
        btn_cancel.pack(side="left", padx=8)
        btn_ok = Boton(card, "Confirmar pago y emitir factura", None, "pri", alto=50, tam=14)
        btn_ok.pack(fill="x", pady=(12, 0))

        pagos = []   # dicts: id_metodo, nombre, moneda, monto (en su moneda), usd (equivalente), referencia

        def moneda_sel():
            return "VES" if moneda.get() == OPC_VES else "USD"

        def pagado_usd():
            return sum((p["usd"] for p in pagos), Decimal("0"))

        def pendiente():
            return total - pagado_usd()

        def sugerir():
            falta = pendiente()
            monto.delete(0, "end")
            if falta > TOL:
                if moneda_sel() == "VES":
                    v = total_bs if not pagos else mon.a_bs(falta, tasa)
                else:
                    v = falta
                monto.insert(0, f"{v:.2f}")

        def actualizar_ayudas(_e=None):
            try:
                v = mon.parse_monto(monto.get())
                if moneda_sel() == "VES":
                    lb_eq.configure(text=f"Equivale a {mon.fmt_usd(mon.a_usd(v, tasa))} USD")
                else:
                    lb_eq.configure(text=f"Equivale a {mon.fmt_bs(mon.a_bs(v, tasa))}")
            except ValueError:
                lb_eq.configure(text="")
            lb_ref.configure(text="Obligatoria para este método." if metodo.get() in REQUIERE_REF else "Opcional (efectivo).")

        def refrescar():
            tv.delete(*tv.get_children())
            for i, p in enumerate(pagos):
                tv.insert("", "end", iid=str(i), values=(
                    p["nombre"], "Bs." if p["moneda"] == "VES" else "USD", f"{p['monto']:,.2f}",
                    mon.fmt_usd(p["usd"]), p["referencia"] or "—"), tags=tags_fila(i))
            falta = pendiente()
            if falta > TOL:
                lb_res.configure(text=f"Pagado: {mon.fmt_usd(pagado_usd())}   ·   Falta: {mon.fmt_usd(falta)}  ({mon.fmt_bs(mon.a_bs(falta, tasa))})",
                                 text_color=C["warn"])
            else:
                lb_res.configure(text=f"Pagado: {mon.fmt_usd(pagado_usd())}   ·   Pago completo", text_color=C["ok"])
            btn_ok.configure(state="normal" if pagos and abs(falta) <= TOL else "disabled")
            sugerir()
            ref.delete(0, "end")
            actualizar_ayudas()

        def cambio_metodo(_e=None):
            sugerida = MONEDA_POR_METODO.get(metodo.get())
            if sugerida:
                moneda.set(OPC_VES if sugerida == "VES" else OPC_USD)
            sugerir(); actualizar_ayudas()

        def cambio_moneda(_e=None):
            sugerir(); actualizar_ayudas()

        def agregar():
            try:
                m = mon.q2(mon.parse_monto(monto.get()))
            except ValueError:
                return messagebox.showwarning("Pago", "Introduzca un monto numérico.", parent=d)
            if m <= 0:
                return messagebox.showwarning("Pago", "El monto debe ser mayor que cero.", parent=d)
            mon_sel = moneda_sel()
            usd = m if mon_sel == "USD" else mon.a_usd(m, tasa)
            if usd > pendiente() + TOL:
                return messagebox.showwarning("Pago", f"El monto supera lo pendiente ({mon.fmt_usd(pendiente())} / {mon.fmt_bs(mon.a_bs(pendiente(), tasa))}).", parent=d)
            nombre = metodo.get(); referencia = ref.get().strip()
            if nombre in REQUIERE_REF and not referencia:
                return messagebox.showwarning("Referencia requerida", f"Indique la referencia del pago por {nombre}.", parent=d)
            idm = next(x["id"] for x in metodos if x["nombre"] == nombre)
            pagos.append({"id_metodo": idm, "nombre": nombre, "moneda": mon_sel, "monto": m, "usd": usd,
                          "referencia": referencia or None})
            refrescar()

        def quitar():
            s_ = tv.focus()
            if s_:
                pagos.pop(int(s_)); refrescar()

        def cancelar():
            d.destroy(); abortar()

        def confirmar():
            if abs(pendiente()) > TOL:
                return messagebox.showwarning("Pago", "El pago no cubre el total de la factura.", parent=d)
            d.destroy()
            self.facturar(cliente_id, list(pagos), dialogo_padre, boton, estado, total)

        btn_add.configure(command=agregar); btn_quitar.configure(command=quitar)
        btn_cancel.configure(command=cancelar); btn_ok.configure(command=confirmar)
        d.protocol("WM_DELETE_WINDOW", cancelar)
        monto.bind("<KeyRelease>", actualizar_ayudas)
        metodo.al_cambiar(lambda _v: cambio_metodo())
        moneda.al_cambiar(lambda _v: cambio_moneda())
        cambio_metodo(); refrescar(); monto.focus_set()

    def facturar(self, cliente_id, pagos, dialogo=None, boton=None, estado=None, total_esperado=None):
        """Emite la factura con la tasa que se ve en pantalla (la misma con la que se calcularon los pagos)."""
        def error(ex):
            if boton and boton.winfo_exists(): boton.configure(state="normal")
            if estado and estado.winfo_exists(): estado.configure(text="")
            messagebox.showerror("Error al generar la factura", str(ex),
                                 parent=dialogo if dialogo and dialogo.winfo_exists() else self)

        t = self.tasa
        if not t:
            return error(ValueError("No hay tasa BCV disponible."))
        items = [{"id_piston": i, "cantidad": it["cant"]} for i, it in self.carrito.items()]
        lista_pagos = [{"id_metodo": p["id_metodo"], "monto": p["monto"], "moneda": p["moneda"],
                        "referencia": p["referencia"]} for p in pagos]
        try:
            r = ventas_repo.emitir_factura(cliente_id, self.user["id"], items, t["valor"], t["fecha"],
                                           t["fuente"], lista_pagos, IVA, total_esperado)
        except Exception as ex:
            db.log(self.user["id"], "FACTURA_EMITIDA", str(ex), "ERROR")
            if "cambió" in str(ex):
                self._recargar_precios_carrito()
            return error(ex)
        db.log(self.user["id"], "FACTURA_EMITIDA",
               f"{r['numero']} · total {mon.fmt_usd(r['total'])} USD / {mon.fmt_bs(r['total_bs'])}")
        if dialogo and dialogo.winfo_exists(): dialogo.destroy()
        self.carrito.clear(); self.v_refrescar(); self.cargar_fac(); self.cargar_inv()
        try:
            self._abrir_pdf_factura(r["id_factura"])
        except Exception as ex:
            messagebox.showwarning(
                "Comprobante PDF",
                f"La factura {r['numero']} se emitió correctamente, pero no se pudo crear el PDF.\n\n{ex}\n\n"
                "Puede generarlo después desde Facturación con «Descargar PDF».", parent=self)

    @staticmethod
    def texto_factura(num, fecha, cli, rif, items, sub, iva, tot, tasa=None, fecha_tasa=None, sub_bs=None, iva_bs=None, tot_bs=None, fuente_tasa=None, pagos=None):
        """Factura en texto con TODOS los importes en USD y en Bs. (a la tasa guardada en la factura)."""
        W = 98
        td = mon.D(tasa) if tasa else None
        L = ["MANUFACTURAS DE ALUMINIO I, C.A.", "=" * W, f"FACTURA N°: {num}", f"Fecha: {fecha}",
             f"Cliente: {cli}   RIF/C.I.: {rif}", "-" * W,
             f"{'Código':<22}{'Cant':>6}{'P.Unit USD':>14}{'P.Unit Bs.':>18}{'Importe USD':>18}{'Importe Bs.':>20}"]
        for c, q, p in items:
            p = mon.D(p); imp = mon.q2(p * q)
            pbs = f"{mon.a_bs(p, td):,.2f}" if td else "—"
            ibs = f"{mon.a_bs(imp, td):,.2f}" if td else "—"
            L.append(f"{c:<22}{q:>6}{p:>14,.2f}{pbs:>18}{imp:>18,.2f}{ibs:>20}")

        def bs(v):
            return f"{mon.D(v):,.2f}" if v is not None else "—"

        def fila(et, usd, b):
            return f"{et:<40}{usd:>28}{b:>30}"
        L += ["-" * W, fila("", "USD", "Bs."),
              fila("SUBTOTAL", f"{mon.D(sub):,.2f}", bs(sub_bs)),
              fila("IVA (16%)", f"{mon.D(iva):,.2f}", bs(iva_bs)),
              fila("TOTAL", f"{mon.D(tot):,.2f}", bs(tot_bs))]
        if td is not None and tot_bs is not None:
            fecha_txt = fecha_tasa.strftime("%d/%m/%Y") if hasattr(fecha_tasa, "strftime") else str(fecha_tasa)
            L += ["", f"Tasa BCV aplicada: Bs. {mon.fmt_tasa(td)} por USD · Fecha efectiva: {fecha_txt}"]
            if fuente_tasa:
                L.append(str(fuente_tasa))
        else:
            L += ["", "Factura histórica anterior al registro de tasa BCV.",
                  "Los importes USD se conservan tal como fueron emitidos; no se recalculan."]
        if pagos:
            L += ["", "FORMA(S) DE PAGO"]
            for n, m, mo, ta, r in pagos:
                m = mon.D(m)
                if (mo or "USD") == "VES":
                    usd = mon.a_usd(m, ta) if ta else None
                    cuerpo = f"Bs. {m:,.2f}" + (f"   (equivale a {mon.fmt_usd(usd)}, tasa {mon.fmt_tasa(ta)})" if usd is not None else "")
                else:
                    cuerpo = f"USD {m:,.2f}" + (f"   (equivale a {mon.fmt_bs(mon.a_bs(m, td))})" if td else "")
                L.append(f"{n:<16}{cuerpo}" + (f"   Ref: {r}" if r else ""))
        return "\n".join(L)

    def _recargar_precios_carrito(self):
        """Si un precio cambió mientras se cobraba, la orden vuelve a mostrar los precios vigentes."""
        for i, it in list(self.carrito.items()):
            p = db.piston("p.id_piston=%s", (i,))
            if p:
                it["p"] = p
        self.v_refrescar()

    def _texto_factura_id(self, fid):
        """Arma el texto de una factura a partir de lo que quedó guardado en la base de datos."""
        f, det, pg = ventas_repo.obtener_factura(int(fid))
        if not f:
            raise ValueError("La factura ya no existe.")
        fecha = f["fecha_hora"].strftime("%d/%m/%Y %H:%M") if hasattr(f["fecha_hora"], "strftime") else str(f["fecha_hora"])
        return self.texto_factura(
            f["nro_factura"], fecha, f["cliente"], f["documento_cliente"],
            [(i["codigo"], i["cantidad"], i["precio_unitario"]) for i in det],
            f["subtotal"], f["iva"], f["total"], f.get("tasa_bcv"), f.get("fecha_tasa"),
            f.get("subtotal_bs"), f.get("iva_bs"), f.get("total_bs"),
            f.get("observacion") if f.get("tasa_bcv") else None,
            [(p["nombre_metodo"], p["monto"], p["moneda"], p["tasa_aplicada"], p["referencia"]) for p in pg] or None)

    def mostrar_texto(self, titulo, txt, id_factura=None):
        w = Dialogo(self, titulo, 960, 660, modal=False, redim=True)
        c = w.cuerpo(22)
        cab = transparente(c)
        cab.pack(fill="x", pady=(0, 12))
        titulo_seccion(cab, titulo).pack(side="left")

        Boton(cab, "Cerrar", w.destroy, "accion", ancho=100, alto=36).pack(side="right")
        if id_factura is not None:
            Boton(cab, "Descargar PDF", lambda: self.descargar_pdf(id_factura, w), "accion", ancho=150,
                  alto=36).pack(side="right", padx=(0, 8))
        t = ctk.CTkTextbox(c, font=ctk.CTkFont(family="Consolas", size=13), wrap="none", fg_color=C["surface"],
                           text_color=C["text"], border_width=1, border_color=C["border"], corner_radius=14)
        t.pack(fill="both", expand=True)
        t.insert("1.0", txt)
        t.configure(state="disabled")

    def _abrir_pdf_factura(self, id_factura):
        """Genera el comprobante en la carpeta facturas/ (solo lectura de la base de datos) y lo abre al instante."""
        datos = comprobante_pdf.datos_comprobante(int(id_factura))
        os.makedirs(FAC_DIR, exist_ok=True)
        ruta = os.path.join(FAC_DIR, comprobante_pdf.nombre_sugerido(datos["nro_factura"]))
        try:
            comprobante_pdf.generar_pdf(datos, ruta)
        except PermissionError:
            if not os.path.exists(ruta):      # si ya existe pero está abierto en el visor, se abre ese mismo archivo
                raise
        if hasattr(os, "startfile"):
            os.startfile(ruta)
        else:
            import subprocess, sys
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ruta])
        return ruta

    def descargar_pdf(self, id_factura, padre=None):
        """Comprobante de pago en PDF. Solo lee la factura guardada: no registra ventas, pagos ni cambios."""
        padre = padre if padre is not None and padre.winfo_exists() else self
        try:
            datos = comprobante_pdf.datos_comprobante(int(id_factura))
        except Exception as ex:
            return messagebox.showerror("Comprobante PDF", f"No se pudo leer la factura.\n\n{ex}", parent=padre)
        faltan = empresa.faltantes(datos["empresa"])
        if faltan and not messagebox.askyesno(
                "Datos de la empresa incompletos",
                f"Falta registrar: {', '.join(faltan)}.\n\nEscríbalos en recursos/empresa.json para que aparezcan en el "
                "comprobante.\n\n¿Desea generar el PDF de todos modos (sin esos datos)?", parent=padre):
            return
        ruta = filedialog.asksaveasfilename(
            parent=padre, title="Guardar comprobante de pago", defaultextension=".pdf",
            filetypes=[("Documento PDF", "*.pdf")], initialfile=comprobante_pdf.nombre_sugerido(datos["nro_factura"]))
        if not ruta:
            return                                    # el usuario canceló
        try:
            comprobante_pdf.generar_pdf(datos, ruta)
        except comprobante_pdf.DependenciaFaltante as ex:
            return messagebox.showerror("Comprobante PDF", str(ex), parent=padre)
        except PermissionError:
            return messagebox.showerror("Comprobante PDF", "No se pudo guardar el archivo. Si está abierto en otro "
                                        "programa, ciérrelo o elija otro nombre o carpeta.", parent=padre)
        except Exception as ex:
            return messagebox.showerror("Comprobante PDF", f"No se pudo generar el PDF.\n\n{ex}", parent=padre)
        messagebox.showinfo("Comprobante PDF", f"El comprobante se guardó en:\n{ruta}", parent=padre)

    # ------------------------------------------------------------ FACTURAS
    def ui_facturas(self):
        cols = ("numero", "fecha", "cliente", "subtotal", "total", "total_bs", "tasa")
        heads = {"numero": "FACTURA", "fecha": "FECHA", "cliente": "CLIENTE", "subtotal": "SUBTOTAL USD",
                 "total": "TOTAL USD", "total_bs": "TOTAL BS.", "tasa": "TASA BCV"}
        anclas = {"numero": "w", "fecha": "w", "cliente": "w", "subtotal": "e", "total": "e", "total_bs": "e", "tasa": "e"}
        bar = tarjeta(self.t_fac)
        bar.pack(fill="x", pady=(0, 14))
        Boton(bar, "Descargar PDF", self.descargar_pdf_seleccion, "accion", ancho=170).pack(side="left", padx=16, pady=14)
        tenue(bar, "Seleccione una factura. Doble clic: abrir su comprobante en PDF.", 12).pack(side="left", padx=8)
        marco, self.tv_f = tabla(self.t_fac, cols, heads, (110, 145, 240, 120, 120, 160, 110), anclas)
        marco.pack(fill="both", expand=True)
        self.tv_f.bind("<Double-1>", self.ver_factura)

    def cargar_fac(self):
        if not hasattr(self, "tv_f"): return
        self.tv_f.delete(*self.tv_f.get_children())
        try:
            filas = ventas_repo.listar_facturas()
        except Exception as ex:
            return messagebox.showerror("Facturación", f"No se pudo cargar el registro de facturas.\n\n{ex}", parent=self)
        for i, r in enumerate(filas):
            fecha = r["fecha_hora"].strftime("%d/%m/%Y %H:%M") if hasattr(r["fecha_hora"], "strftime") else str(r["fecha_hora"])
            self.tv_f.insert("", "end", iid=r["id_factura"], values=(
                r["nro_factura"], fecha, r["cliente"], mon.fmt_usd(r["subtotal"]), mon.fmt_usd(r["total"]),
                mon.fmt_bs(r["total_bs"], sin_tasa="Histórica") if r["total_bs"] is not None else "Histórica",
                mon.fmt_tasa(r["tasa_bcv"]) if r["tasa_bcv"] else "—"), tags=tags_fila(i))

    def ver_factura(self, _=None):
        s_ = self.tv_f.focus()
        if not s_: return
        try:
            self._abrir_pdf_factura(int(s_))
        except Exception as ex:
            messagebox.showerror("Factura", f"No se pudo abrir el comprobante PDF.\n\n{ex}", parent=self)

    def descargar_pdf_seleccion(self):
        s_ = self.tv_f.focus()
        if not s_:
            return messagebox.showinfo("Comprobante PDF", "Seleccione una factura de la lista.", parent=self)
        self.descargar_pdf(int(s_), self)

    # ------------------------------------------------------------ USUARIOS
    def ui_usuarios(self):
        bar = tarjeta(self.t_usr)
        bar.pack(fill="x", pady=(0, 14))
        Boton(bar, "Agregar usuario", self.agregar_usuario, "accion", ancho=190, icono="user-plus").pack(side="left", padx=(16, 8), pady=14)
        Boton(bar, "Editar usuario", self.editar_usuario, "accion", ancho=180).pack(side="left", padx=4, pady=14)
        Boton(bar, "Activar / desactivar", self.toggle_usuario, "accion", ancho=180).pack(side="left", padx=4, pady=14)
        heads = {"usuario": "USUARIO", "rol": "ROL", "etapa": "ETAPA ASIGNADA", "estado": "ESTADO"}
        marco, self.tv_u = tabla(self.t_usr, ("usuario", "rol", "etapa", "estado"), heads, (260, 180, 330, 130))
        marco.pack(fill="both", expand=True)
        self.tv_u.bind("<Double-1>", lambda _e: self.editar_usuario())
        self.cargar_usuarios()

    def cargar_usuarios(self):
        if not hasattr(self, "tv_u"): return
        self.tv_u.delete(*self.tv_u.get_children())
        for i, u in enumerate(db.consulta(db.SQL_USUARIO + " ORDER BY u.nombre_usuario")):
            # Verde si está activo, rojo si está inactivo (se conserva el color alterno de las filas).
            etapa = prod.nombre_control(u["etapa"]) if u["rol"] == prod.ROL_CONTROL else "—"
            self.tv_u.insert("", "end", iid=u["id"],
                             values=(u["usuario"], u["rol"], etapa, "● Activo" if u["activo"] else "● Inactivo"),
                             tags=(tags_fila(i)[0], "usr_activo" if u["activo"] else "usr_inactivo"))

    def _selector_rol_etapa(self, card, rol_inicial="Cajero", etapa_inicial=None, rol_editable=True):
        """Rol + (solo si es CONTROL) la etapa asignada. Devuelve (rol, etapa_o_None) mediante la función ``leer()``."""
        etiqueta(card, "Rol", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        rol = Combo(card, values=ROLES, ancho=400)
        rol.set(rol_inicial if rol_inicial in ROLES else "Cajero")
        rol.pack(fill="x", pady=(5, 0))
        if not rol_editable:
            rol.configure(state="disabled")
        hueco = transparente(card)
        hueco.pack(fill="x")
        caja = transparente(hueco)
        etiqueta(caja, "Etapa asignada (la única que podrá modificar)", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        opciones = [prod.nombre_control(i) for i in range(1, prod.ULTIMO_PASO + 1)]
        etapa = Combo(caja, values=opciones, ancho=400)
        valida = etapa_inicial is not None and 1 <= int(etapa_inicial) <= prod.ULTIMO_PASO
        etapa.set(prod.nombre_control(etapa_inicial) if valida else opciones[0])
        etapa.pack(fill="x", pady=(5, 0))
        tenue(caja, "Podrá consultar las nueve etapas, pero solo registrar o completar la suya.", 11, wraplength=380,
              justify="left").pack(anchor="w", pady=(4, 0))

        def mostrar(_v=None):
            if rol.get() == prod.ROL_CONTROL:
                caja.pack(fill="x")
            else:
                caja.pack_forget()
        rol.al_cambiar(mostrar)
        mostrar()

        def leer():
            r = rol.get()
            return r, (etapa.current() + 1 if r == prod.ROL_CONTROL else None)
        return leer

    def agregar_usuario(self):
        d = Dialogo(self, "Agregar usuario", 480, 660)
        card = d.cuerpo(26, scroll=True)
        titulo_seccion(card, "Nuevo usuario").pack(anchor="w", pady=(0, 6))
        etiqueta(card, "Usuario", 12, "bold", C["muted"]).pack(anchor="w", pady=(8, 0))
        e_user = campo(card, 400)
        e_user.pack(fill="x", pady=(5, 0))
        etiqueta(card, "Contraseña", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        e_pass = campo(card, 400, mostrar="•")
        e_pass.pack(fill="x", pady=(5, 0))
        leer = self._selector_rol_etapa(card)
        e_user.focus_set()

        def guardar():
            u = e_user.get().strip(); p = e_pass.get(); rr, etapa = leer()
            if not u or not p: return messagebox.showwarning("Datos", "Complete todos los campos.", parent=d)
            try:
                nuevo_id = db.consulta("INSERT INTO usuarios(id_rol,nombre_usuario,clave_hash,etapa_asignada) SELECT id_rol,%s,%s,%s FROM roles WHERE nombre_rol=%s", (u, db.hash_clave(p), etapa, rr), commit=True)
                if not nuevo_id: raise ValueError("El rol seleccionado no existe.")
                db.log(self.user["id"], "USUARIO_CREADO", f"Usuario {u} ({rr}{' · ' + prod.nombre_control(etapa) if etapa else ''})")
            except Exception as ex:
                return messagebox.showerror("Usuario", f"No se pudo crear el usuario.\n\n{ex}", parent=d)
            d.destroy(); self.cargar_usuarios()
        Boton(card, "Guardar usuario", guardar, "pri").pack(fill="x", pady=(22, 0))

    def editar_usuario(self):
        """Ventana con la ficha completa del usuario: nombre, contraseña, rol, etapa (CONTROL) y estado."""
        if not self.admin:
            return messagebox.showwarning("Permiso denegado", "Solo el administrador puede editar usuarios.", parent=self)
        u = self._usuario_seleccionado()
        if not u: return
        propio = u["id"] == self.user["id"]
        extra = db.consulta("SELECT u.fecha_creacion AS creado, (SELECT MAX(l.fecha_hora) FROM log_usuarios l WHERE l.id_usuario=u.id_usuario "
                            "AND l.accion='LOGIN' AND l.resultado='OK') AS ultimo FROM usuarios u WHERE u.id_usuario=%s", (u["id"],), uno=True) or {}
        fmt = lambda v: v.strftime("%d/%m/%Y %H:%M") if hasattr(v, "strftime") else "—"
        d = Dialogo(self, f"Editar usuario · {u['usuario']}", 500, 780)
        card = d.cuerpo(26, scroll=True)
        titulo_seccion(card, f"Editar usuario · {u['usuario']}").pack(anchor="w")
        tenue(card, f"ID {u['id']}  ·  Creado: {fmt(extra.get('creado'))}  ·  Último acceso: {fmt(extra.get('ultimo'))}", 12).pack(anchor="w", pady=(2, 0))
        etiqueta(card, "Nombre de usuario", 12, "bold", C["muted"]).pack(anchor="w", pady=(14, 0))
        e_user = campo(card, 400)
        e_user.insert(0, u["usuario"])
        e_user.pack(fill="x", pady=(5, 0))
        etiqueta(card, "Nueva contraseña", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        e_pass = campo(card, 400, "Dejar en blanco para conservar la actual", mostrar="•")
        e_pass.pack(fill="x", pady=(5, 0))
        etiqueta(card, "Confirmar contraseña", 12, "bold", C["muted"]).pack(anchor="w", pady=(12, 0))
        e_conf = campo(card, 400, mostrar="•")
        e_conf.pack(fill="x", pady=(5, 0))
        leer = self._selector_rol_etapa(card, u["rol"], u["etapa"], rol_editable=not propio)
        etiqueta(card, "Estado", 12, "bold", C["muted"]).pack(anchor="w", pady=(14, 0))
        sw = ctk.CTkSwitch(card, text="Activo" if u["activo"] else "Desactivado", font=fuente(13, "bold"), switch_width=46, switch_height=24,
                           fg_color=COLOR_INACTIVO, progress_color=COLOR_ACTIVO, button_color="#FFFFFF", button_hover_color="#F1F5F9",
                           text_color=C["text"], state="normal" if not propio else "disabled")
        sw.configure(command=lambda: sw.configure(text="Activo" if sw.get() else "Desactivado"))
        sw.pack(anchor="w", pady=(6, 0))
        if u["activo"]:
            sw.select()
        if propio:
            tenue(card, "En su propia cuenta puede cambiar el nombre y la contraseña, pero no su rol ni su estado.", 11,
                  wraplength=400, justify="left").pack(anchor="w", pady=(8, 0))
        e_user.focus_set()

        def guardar():
            nombre, clave, conf = e_user.get().strip(), e_pass.get(), e_conf.get()
            rol_nuevo, etapa = leer()
            activo_nuevo = 1 if sw.get() else 0
            if propio:                                     # nunca se puede quitar el acceso de administrador a sí mismo
                rol_nuevo, etapa, activo_nuevo = u["rol"], u["etapa"], 1
            if not nombre:
                return messagebox.showwarning("Datos", "Escriba el nombre de usuario.", parent=d)
            if len(nombre) > 40:
                return messagebox.showwarning("Datos", "El nombre de usuario admite como máximo 40 caracteres.", parent=d)
            if clave or conf:
                if clave != conf:
                    return messagebox.showwarning("Datos", "La contraseña y su confirmación no coinciden.", parent=d)
            if rol_nuevo == prod.ROL_CONTROL and not etapa:
                return messagebox.showwarning("Datos", "Asigne la etapa de producción al usuario CONTROL.", parent=d)
            try:
                actual = db.consulta(db.SQL_USUARIO + " WHERE u.id_usuario=%s", (u["id"],), uno=True)
                if not actual:
                    d.destroy(); self.cargar_usuarios()
                    return messagebox.showwarning("Usuarios", "El usuario ya no existe.", parent=self)
                if db.consulta("SELECT id_usuario FROM usuarios WHERE nombre_usuario=%s AND id_usuario<>%s", (nombre, u["id"]), uno=True):
                    return messagebox.showwarning("Datos", f"Ya existe un usuario llamado «{nombre}».", parent=d)
                cambios, sets, par = [], ["nombre_usuario=%s", "id_rol=(SELECT id_rol FROM roles WHERE nombre_rol=%s)",
                                          "etapa_asignada=%s", "estado=%s"], [nombre, rol_nuevo, etapa, activo_nuevo]
                if nombre != actual["usuario"]: cambios.append(f"nombre {actual['usuario']} → {nombre}")
                if rol_nuevo != actual["rol"]: cambios.append(f"rol {actual['rol']} → {rol_nuevo}")
                if (etapa or None) != (actual["etapa"] or None): cambios.append(f"etapa → {prod.nombre_control(etapa) if etapa else 'ninguna'}")
                if activo_nuevo != int(actual["activo"]): cambios.append("activado" if activo_nuevo else "desactivado")
                if clave:
                    sets.append("clave_hash=%s"); par.append(db.hash_clave(clave)); cambios.append("contraseña cambiada")
                if not cambios:
                    d.destroy()
                    return messagebox.showinfo("Usuarios", "No hay cambios que guardar.", parent=self)
                db.consulta(f"UPDATE usuarios SET {', '.join(sets)} WHERE id_usuario=%s", tuple(par) + (u["id"],), commit=True)
                db.log(self.user["id"], "USUARIO_EDITADO", f"Usuario {actual['usuario']}: " + "; ".join(cambios))
            except Exception as ex:
                return messagebox.showerror("Usuario", f"No se pudo guardar el cambio.\n\n{ex}", parent=d)
            if propio and nombre != self.user.get("usuario"):
                self.user["usuario"] = self.user["nombre"] = nombre
                self.title(f"Manufacturas de Aluminio I, C.A. - {nombre} ({self.user['rol']})")
            d.destroy(); self.cargar_usuarios()
            messagebox.showinfo("Usuarios", "Usuario actualizado. Los cambios de rol, etapa o contraseña rigen en su próximo inicio de sesión.", parent=self)
        Boton(card, "Guardar cambios", guardar, "pri").pack(fill="x", pady=(22, 0))

    def _usuario_seleccionado(self):
        s = self.tv_u.focus()
        if not s: messagebox.showwarning("Usuarios", "Seleccione un usuario.", parent=self); return None
        return db.consulta(db.SQL_USUARIO + " WHERE u.id_usuario=%s", (s,), uno=True)

    def toggle_usuario(self):
        u = self._usuario_seleccionado()
        if not u: return
        if u["id"] == self.user["id"]:
            return messagebox.showwarning("Usuarios", "No puede desactivarse a sí mismo.", parent=self)
        db.consulta("UPDATE usuarios SET estado=%s WHERE id_usuario=%s", (0 if u["activo"] else 1, u["id"]), commit=True); db.log(self.user["id"], "USUARIO_ESTADO", f"Usuario {u['usuario']} {'desactivado' if u['activo'] else 'activado'}"); self.cargar_usuarios()


# ============================================================================ FICHA DEL PISTÓN
class Ficha(Dialogo):
    def __init__(self, app, p):
        super().__init__(app, f"Ficha - {p['codigo']}", 980, 800, modal=False, redim=True)
        self.minsize(820, 600)
        self.app, self.p = app, p
        cont = self.cuerpo(24, scroll=True)
        etiqueta(cont, f"Ficha del pistón · {p['codigo']}", 24, "bold").pack(anchor="w")
        tenue(cont, "Los cambios técnicos se guardan y regeneran la etiqueta QR.", 12).pack(anchor="w", pady=(2, 14))
        top = transparente(cont)
        top.pack(fill="x")
        top.grid_columnconfigure(0, weight=1)
        f = tarjeta(top)
        f.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        g = transparente(f)
        g.pack(fill="x", padx=22, pady=18)
        self.e = construir_campos_piston(g, p, editable=app.admin, extra=(SECCION_OTRAS_MEDIDAS,))
        self.e["codigo"].configure(text_color=C["muted"])
        imgcard = tarjeta(top)
        imgcard.grid(row=0, column=1, sticky="nsew")
        etiqueta(imgcard, "Imagen del pistón", 14, "bold").pack(padx=22, pady=(18, 8), anchor="w")
        self.lb = ctk.CTkLabel(imgcard, text="(sin imagen)", width=280, height=220, corner_radius=14,
                               fg_color=C["surface2"], text_color=C["muted"])
        self.lb.pack(padx=22, pady=(0, 18))
        self.ph = cargar_img(p["imagen"], (280, 220))
        if self.ph:
            self.lb.configure(image=self.ph, text="")

        pr = mon.D(p.get("precio")); tasa = app.tasa_valor()
        precio = ctk.CTkFrame(cont, fg_color=C["primary_soft"], corner_radius=16)
        precio.pack(fill="x", pady=(14, 0))
        tenue(precio, "PRECIO DE VENTA", 11).pack(anchor="w", padx=20, pady=(12, 0))
        self.lb_precio = etiqueta(precio, self._texto_precio(pr, tasa), 18, "bold", C["primary"])
        self.lb_precio.pack(anchor="w", padx=20, pady=(0, 12))
        if app.admin or app.gestion_stock:
            bt = transparente(cont)
            bt.pack(fill="x", pady=(14, 0))
            if app.admin:
                Boton(bt, "Guardar cambios", self.guardar, "pri", ancho=190).pack(side="left")
                Boton(bt, "Cambiar imagen", self.cambiar_img, "accion", ancho=170).pack(side="left", padx=10)
            Boton(bt, "Modificar precio", self.modificar_precio, "accion", ancho=170).pack(side="left", padx=(0, 10))
        etq = tarjeta(cont)
        etq.pack(fill="x", pady=(16, 0))
        etiqueta(etq, "Etiqueta QR", 14, "bold").pack(anchor="w", padx=22, pady=(16, 0))
        self.lq = ctk.CTkLabel(etq, text="(sin etiqueta)", text_color=C["muted"])
        self.lq.pack(padx=22, pady=16)
        self.pintar_etq()

    @staticmethod
    def _texto_precio(pr, tasa):
        return (mon.fmt_usd(pr) + "   ·   " + mon.fmt_bs(a_bs_o_none(pr, tasa)) if pr > 0 else "Sin precio asignado")

    def modificar_precio(self):
        """Abre el diálogo de precio de este pistón y, al guardar, actualiza el precio mostrado en la ficha."""
        def refrescar():
            nuevo = db.piston("p.id_piston=%s", (self.p["id"],))
            if nuevo:
                self.p["precio"] = nuevo.get("precio")
                self.lb_precio.configure(text=self._texto_precio(mon.D(nuevo.get("precio")), self.app.tasa_valor()))
        self.app.dialogo_precio(self.p["id"], refrescar, padre=self)

    def pintar_etq(self):
        self.pq = cargar_img(self.p["etiqueta"], (640, 460))
        if self.pq:
            self.lq.configure(image=self.pq, text="")

    def cambiar_img(self):
        r = filedialog.askopenfilename(filetypes=[("Imágenes", "*.jpg *.jpeg *.png")])
        if r:
            ext = os.path.splitext(r)[1].lower()
            os.makedirs(IMG_DIR, exist_ok=True)
            for otra in (".jpg", ".jpeg", ".png"):      # evita dejar dos fotos con el mismo código
                viejo = os.path.join(IMG_DIR, self.p["codigo"] + otra)
                if otra != ext and os.path.exists(viejo):
                    os.remove(viejo)
            dest = os.path.join(IMG_DIR, self.p["codigo"] + ext)
            if os.path.abspath(r) != os.path.abspath(dest):
                shutil.copy(r, dest)
            self.p["imagen"] = dest
            self.ph = cargar_img(dest, (280, 220))
            if self.ph:
                self.lb.configure(image=self.ph, text="")
            self.p["qr"], self.p["etiqueta"] = regenerar_etiqueta(self.p); self.pintar_etq()

    def guardar(self):
        try:
            v = validar({k: en.get().strip() for k, en in self.e.items()}, nuevo=False,
                        descripcion_actual=self.p.get("descripcion", ""))
        except ValueError as ex:
            return messagebox.showwarning("Datos", str(ex), parent=self)
        try:
            db.actualizar_piston(self.p["id"], v)
        except Exception as ex:
            return messagebox.showerror("No se pudo guardar", str(ex), parent=self)
        self.p.update(v)
        db.log(self.app.user["id"], "PISTON_EDITADO", f"Pistón {self.p['codigo']}")
        try:
            self.p["qr"], self.p["etiqueta"] = regenerar_etiqueta(self.p)
        except Exception as ex:
            messagebox.showwarning("Etiqueta", f"Los datos se guardaron, pero no se pudo regenerar la etiqueta.\n\n{ex}", parent=self)
        self.pintar_etq(); self.app.cargar_inv()
        messagebox.showinfo("Actualizado", "Datos técnicos actualizados. El precio se modifica con el botón «Modificar precio».", parent=self.app)


def actualizar_qrs_existentes():
    """Regenera etiquetas/QR con el formato actual y los registra en CODIGOS_QR."""
    try:
        lista = db.pistones()
    except Exception:
        return
    for p in lista:
        try:
            regenerar_etiqueta(p)
        except Exception:
            pass


def principal():
    configurar_estilo()
    try:
        db.init_db()
    except Exception as e:
        r = ctk.CTk(); r.withdraw()
        messagebox.showerror("Base de datos", f"No se pudo preparar la base de datos.\nSi el mensaje habla de conexión, encienda MySQL en XAMPP.\n\n{e}", parent=r)
        r.destroy()
        return
    actualizar_qrs_existentes()
    while True:                      # permite cerrar sesión y volver a entrar sin reiniciar el programa
        lg = Login()
        lg.mainloop()
        if not lg.usuario:
            break
        app = App(lg.usuario)
        app.mainloop()
        if not app.cerrar_sesion:
            break


if __name__ == "__main__":
    principal()
