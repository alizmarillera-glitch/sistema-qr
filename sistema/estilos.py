"""Sistema visual de Sistema QR (CustomTkinter): paleta clara/oscura, tipografía y tablas.

Los colores se definen como tuplas (modo claro, modo oscuro): CustomTkinter elige
automáticamente el que corresponde al modo activo. Solo la tabla (ttk.Treeview)
necesita recolorearse a mano: ver ``estilizar_tablas``.
"""
import json
import os
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

FUENTE = "Segoe UI"

# (claro, oscuro)
# Diseño «panel industrial»: fondo azul casi negro, tarjetas de cristal con borde azul y acentos azul eléctrico.
C = {
    "bg":           ("#EEF2F9", "#050B14"),
    "surface":      ("#FFFFFF", "#0A1425"),
    "surface2":     ("#F0F3F8", "#0F1C31"),
    "border":       ("#DCE3EE", "#1B3258"),
    "text":         ("#17202E", "#F1F5FB"),
    "muted":        ("#66758B", "#9BAAC4"),
    "primary":      ("#2563EB", "#3B82FF"),
    "primary_h":    ("#1D4FC4", "#6AA0FF"),
    "primary_soft": ("#E4ECFF", "#0F2547"),
    "ok":           ("#0F8F5F", "#22C55E"),
    "ok_soft":      ("#E3F6EE", "#0C2A1F"),
    "danger":       ("#D23F4E", "#F0505F"),
    "danger_h":     ("#B9323F", "#FF7380"),
    "danger_soft":  ("#FDECEE", "#2E1219"),
    "warn":         ("#B86E00", "#FBBF24"),
    "warn_soft":    ("#FFF3DF", "#2E2410"),
    "hover":        ("#E6ECF7", "#10213B"),
    "side":         ("#FFFFFF", "#060E1A"),
    # --- Sistema de botones de tres estados (normal / hover / presionado). Ver ui.Boton.
    "cobalto":      ("#0047AB", "#0B46B8"),     # relleno de los botones principales
    "cobalto_h":    ("#1458BD", "#1659D6"),
    "cobalto_p":    ("#003A8F", "#08378F"),
    "cobalto_txt":  ("#0047AB", "#8DB8FF"),
    "cobalto_soft": ("#EAF1FC", "#0E2447"),
    "nav_sel":      ("#0047AB", "#1565F2"),     # opción activa del menú lateral (azul eléctrico del diseño)
    "nav_sel_h":    ("#1458BD", "#2A78FF"),
    "btn_texto":    ("#1B2638", "#E6ECF7"),
    "btn_borde":    ("#D3DAE6", "#25406E"),
    "btn_borde_h":  ("#6F97D6", "#4F86E6"),
    "danger_borde": ("#EBC3C9", "#7A2631"),
    "danger_press": ("#D23F4E", "#C93545"),
}

# Colores fijos del panel de marca (no cambian con el modo).
MARCA_1 = "#2748C9"
MARCA_2 = "#6A8CFF"
MARCA_3 = "#14224F"


def modo_actual():
    """'dark' o 'light'."""
    return ctk.get_appearance_mode().lower()


def _c(clave):
    """Color de la paleta para el modo vigente (para widgets ttk/tk que no admiten tuplas)."""
    t = C[clave]
    return t[1] if modo_actual() == "dark" else t[0]


def fuente(tam=13, peso="normal"):
    return ctk.CTkFont(family=FUENTE, size=tam, weight=peso)


_PREF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preferencias.json")


def cargar_modo():
    """Modo guardado la última vez ('light' u 'dark'); oscuro por defecto (es el diseño)."""
    try:
        with open(_PREF, encoding="utf-8") as f:
            m = json.load(f).get("modo", "dark")
        return m if m in ("light", "dark") else "dark"
    except Exception:
        return "dark"


def guardar_modo(modo):
    try:
        with open(_PREF, "w", encoding="utf-8") as f:
            json.dump({"modo": modo}, f)
    except Exception:
        pass


def configurar_estilo():
    """Se llama una vez al iniciar el programa."""
    ctk.set_default_color_theme("blue")
    ctk.set_appearance_mode(cargar_modo())


def estilizar_tablas(root):
    """(Re)aplica el aspecto moderno a todos los ttk.Treeview según el modo vigente."""
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    try:
        escala = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
    except Exception:
        escala = 1.0
    st.configure("Treeview", background=_c("surface"), fieldbackground=_c("surface"),
                 foreground=_c("text"), rowheight=int(44 * escala), borderwidth=0,
                 relief="flat", font=(FUENTE, 10))
    st.configure("Treeview.Heading", background=_c("surface2"), foreground=_c("muted"),
                 font=(FUENTE, 9, "bold"), padding=(12, 11), relief="flat", borderwidth=0)
    st.map("Treeview", background=[("selected", _c("primary_soft"))],
           foreground=[("selected", _c("primary"))])
    st.map("Treeview.Heading", background=[("active", _c("hover"))])
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    st.configure("Vertical.TScrollbar", background=_c("border"), troughcolor=_c("surface"),
                 bordercolor=_c("surface"), arrowcolor=_c("muted"), relief="flat", borderwidth=0)
    st.configure("Horizontal.TScrollbar", background=_c("border"), troughcolor=_c("surface"),
                 bordercolor=_c("surface"), arrowcolor=_c("muted"), relief="flat", borderwidth=0)


def colorear_filas(tv):
    """Etiquetas de fila (filas alternadas, inactivo, stock bajo) con colores del modo vigente."""
    dark = modo_actual() == "dark"
    tv.tag_configure("par", background=_c("surface"))
    tv.tag_configure("impar", background="#0D192C" if dark else "#F8FAFD")
    tv.tag_configure("inactivo", foreground="#7C879A")
    tv.tag_configure("usr_activo", foreground="#22C55E" if dark else "#0F8F5F")      # usuarios: activo en verde
    tv.tag_configure("usr_inactivo", foreground="#F0505F" if dark else "#D23F4E")    # usuarios: inactivo en rojo
    tv.tag_configure("stock_bajo", background="#2E2410" if dark else "#FFF3DF")
