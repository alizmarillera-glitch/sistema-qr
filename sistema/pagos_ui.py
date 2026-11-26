# -*- coding: utf-8 -*-
"""Ventana Tkinter para registrar pagos parciales o combinados."""
import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal
import pagos_repo
from tasa_bcv import obtener_tasa
import tasas_repo


def abrir_ventana_pagos(parent, id_pago, tasa_actual=None, fecha_tasa=None):
    resumen = pagos_repo.obtener_resumen_pago(id_pago)
    metodos = pagos_repo.metodos_activos()
    if not metodos:
        messagebox.showerror("Pagos", "No hay métodos de pago activos configurados.", parent=parent)
        return
    w = tk.Toplevel(parent)
    w.title(f"Registrar pagos - {resumen['nro_factura']}")
    w.geometry("650x570")
    w.transient(parent)
    w.grab_set()
    marco = ttk.Frame(w, padding=18)
    marco.pack(fill="both", expand=True)
    ttk.Label(marco, text=f"Factura {resumen['nro_factura']}", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    resumen_var = tk.StringVar()
    ttk.Label(marco, textvariable=resumen_var, justify="left").pack(anchor="w", pady=8)
    ttk.Label(marco, text="Método de pago").pack(anchor="w")
    metodo_var = tk.StringVar(value=metodos[0]["nombre_metodo"])
    metodo_ids = {m["nombre_metodo"]: m["id_metodo_pago"] for m in metodos}
    ttk.Combobox(marco, textvariable=metodo_var, state="readonly", values=list(metodo_ids)).pack(fill="x", pady=(2,8))
    ttk.Label(marco, text="Moneda recibida").pack(anchor="w")
    moneda_var = tk.StringVar(value="USD")
    ttk.Combobox(marco, textvariable=moneda_var, state="readonly", values=("USD", "VES")).pack(fill="x", pady=(2,8))
    ttk.Label(marco, text="Monto recibido en la moneda seleccionada").pack(anchor="w")
    monto_var = tk.StringVar()
    ttk.Entry(marco, textvariable=monto_var).pack(fill="x", pady=(2,8))
    ttk.Label(marco, text="Referencia / número de operación (opcional)").pack(anchor="w")
    ref_var = tk.StringVar()
    ttk.Entry(marco, textvariable=ref_var).pack(fill="x", pady=(2,8))
    ttk.Label(marco, text="Observación (opcional)").pack(anchor="w")
    obs_var = tk.StringVar()
    ttk.Entry(marco, textvariable=obs_var).pack(fill="x", pady=(2,8))
    tasa_estado = {"valor": tasa_actual, "fecha": fecha_tasa}
    tasa_label = tk.StringVar(value=(f"Tasa BCV: {float(tasa_actual):,.4f} Bs/USD · {fecha_tasa}" if tasa_actual
                                     else "Actualice la tasa BCV antes de registrar pagos en bolívares."))
    ttk.Label(marco, textvariable=tasa_label).pack(anchor="w", pady=4)
    def actualizar_tasa_pago():
        try:
            valor, fecha, fuente = obtener_tasa()
            tasas_repo.guardar_tasa(valor, fecha, fuente)
            tasa_estado.update({"valor": valor, "fecha": fecha})
            tasa_label.set(f"Tasa BCV verificada: {float(valor):,.4f} Bs/USD · {fecha} · {fuente}")
        except Exception as exc:
            if not tasa_estado["valor"]:
                tasa_label.set("No se pudo validar la tasa BCV. Los pagos en VES quedan bloqueados.")
            messagebox.showwarning("Tasa BCV", str(exc), parent=w)
    ttk.Button(marco, text="Actualizar tasa BCV", command=actualizar_tasa_pago).pack(anchor="w", pady=(0,6))
    columnas = ("fecha", "metodo", "moneda", "monto", "referencia")
    tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=7)
    for c, t, ancho in (("fecha","Fecha",130),("metodo","Método",110),("moneda","Moneda",65),("monto","Monto",100),("referencia","Referencia",150)):
        tabla.heading(c,text=t); tabla.column(c,width=ancho)
    tabla.pack(fill="both", expand=True, pady=8)

    def refrescar():
        r = pagos_repo.obtener_resumen_pago(id_pago)
        resumen_var.set(f"Total factura: ${r['total_factura']:,.2f} USD\n"
                        f"Pagado: ${r['pagado_usd']:,.2f} USD\n"
                        f"Saldo pendiente: ${r['saldo_usd']:,.2f} USD\nEstado: {r['estado']}")
        tabla.delete(*tabla.get_children())
        for d in pagos_repo.listar_detalles_pago(id_pago):
            fecha = d["fecha_pago"].strftime("%d/%m/%Y %H:%M") if hasattr(d["fecha_pago"],"strftime") else str(d["fecha_pago"])
            tabla.insert("", "end", values=(fecha,d["nombre_metodo"],d["moneda"],f"{d['monto']:,.2f}",d["referencia"] or "—"))
    def guardar():
        try:
            moneda = moneda_var.get()
            tasa = tasa_estado["valor"] if moneda == "VES" else None
            if moneda == "VES" and not tasa:
                raise ValueError("Actualice la tasa BCV antes de registrar un pago en bolívares.")
            pagos_repo.registrar_pago(id_pago, metodo_ids[metodo_var.get()], monto_var.get(), moneda,
                                      ref_var.get(), tasa, obs_var.get())
            monto_var.set(""); ref_var.set(""); obs_var.set("")
            refrescar()
            messagebox.showinfo("Pago registrado", "El pago se registró correctamente.", parent=w)
        except Exception as exc:
            messagebox.showerror("No se pudo registrar el pago", str(exc), parent=w)
    acciones = ttk.Frame(marco); acciones.pack(fill="x", pady=(5,0))
    ttk.Button(acciones, text="Registrar pago", command=guardar).pack(side="left")
    ttk.Button(acciones, text="Cerrar", command=w.destroy).pack(side="right")
    refrescar()
    return w
