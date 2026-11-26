# -*- coding: utf-8 -*-
"""Comprobante de pago en PDF (A4) de Sistema_QR.

Es una operación de SOLO CONSULTA: lee la factura ya guardada (``ventas_repo.obtener_factura``) y los datos de la
empresa (``empresa.cargar``) y dibuja un documento PDF con ReportLab. No escribe en la base de datos, no recalcula
ventas, IVA, inventario ni pagos: todos los importes salen tal como están guardados.

Contenido (en este orden):
  1. Encabezado: logotipo, razón social, RIF y dirección fiscal de la empresa + número del comprobante.
  2. Datos del cliente.
  3. Detalle de la operación con precios e importes en bolívares (sin columnas en dólares).
  4. Base imponible, IVA y TOTAL A PAGAR en bolívares.
  5. Forma(s) de pago EXACTAMENTE como se registraron (método, moneda, importe recibido, referencia, fecha, notas).
  6. Referencia informativa: equivalente aproximado en USD y tasa aplicada (aparte, claramente informativa).
Las facturas históricas (anteriores al registro de la tasa BCV) no tienen importes en Bs.: se imprimen en USD tal como
fueron emitidas, con un aviso, y no se inventa ninguna conversión.

Requiere ``reportlab`` (pip install reportlab).
"""
from __future__ import annotations

import datetime
import io
import os
import re
from decimal import Decimal
from xml.sax.saxutils import escape

import empresa as emp
import moneda as mon
import ventas_repo

# ---- Paleta (azul oscuro, azul y plateado, igual que la identidad del sistema)
AZUL_OSCURO = "#0B1F3A"
AZUL = "#1D4ED8"
PLATA = "#C9D1DC"
PLATA_CLARA = "#F3F5F9"
GRIS_TEXTO = "#5B6675"
TEXTO = "#17202E"
ROJO = "#B4232F"

NOTA_PIE = "Este documento es un comprobante de pago y no sustituye la factura fiscal."


class DependenciaFaltante(RuntimeError):
    """ReportLab no está instalado."""


# --------------------------------------------------------------------------- formato
def _num(valor) -> str:
    """1234567.8 -> '1.234.567,80' (formato venezolano: punto para miles y coma para decimales)."""
    s = f"{mon.q2(valor):,.2f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _bs(valor) -> str:
    return f"Bs. {_num(valor)}"


def _usd(valor) -> str:
    return f"USD {_num(valor)}"


def _tasa(valor) -> str:
    s = f"{mon.D(valor):,.4f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _fecha_hora(v) -> str:
    return v.strftime("%d/%m/%Y %H:%M") if hasattr(v, "strftime") else (str(v) if v else "—")


def _fecha(v) -> str:
    return v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else (str(v) if v else "—")


def _t(v) -> str:
    """Texto seguro para el PDF: espacios normalizados y solo caracteres que la fuente estándar puede dibujar."""
    s = " ".join(str(v).split()) if v is not None else ""
    return s.encode("cp1252", "replace").decode("cp1252")


def _p(v) -> str:
    """Texto listo para un Paragraph de ReportLab (escapado)."""
    return escape(_t(v))


def nombre_sugerido(nro_factura: str) -> str:
    """F-000125 -> Comprobante_Pago_000125.pdf"""
    digitos = re.sub(r"\D", "", str(nro_factura or ""))
    base = digitos or re.sub(r"[^A-Za-z0-9_-]", "", str(nro_factura or "")) or "SN"
    return f"Comprobante_Pago_{base}.pdf"


def _numero_comprobante(nro_factura: str) -> str:
    return re.sub(r"\D", "", str(nro_factura or "")) or str(nro_factura or "")


# --------------------------------------------------------------------------- datos
def datos_comprobante(id_factura: int) -> dict:
    """Reúne, solo leyendo, todo lo que lleva el comprobante de una factura ya emitida."""
    f, detalle, pagos = ventas_repo.obtener_factura(int(id_factura))
    if not f:
        raise ValueError("La factura ya no existe.")
    return {
        "empresa": emp.cargar(),
        "nro_factura": f["nro_factura"],
        "numero_comprobante": _numero_comprobante(f["nro_factura"]),
        "fecha_emision": f["fecha_hora"],
        "estado": f.get("estado"),
        "cliente": {
            "nombre": f.get("cliente"),
            "tipo": f.get("tipo_documento"),
            "numero": f.get("documento"),
            "documento": f.get("documento_cliente"),
            "direccion": f.get("direccion_cliente"),
            "telefono": f.get("telefono_cliente"),
            "codigo": f.get("codigo_cliente"),
        },
        "tasa": f.get("tasa_bcv"),
        "fecha_tasa": f.get("fecha_tasa"),
        "lineas": [{"codigo": d["codigo"], "descripcion": d.get("descripcion"), "cantidad": d["cantidad"],
                    "precio_usd": d["precio_unitario"], "importe_usd": d["subtotal_linea"]} for d in detalle],
        "subtotal_usd": f["subtotal"], "iva_usd": f["iva"], "total_usd": f["total"],
        "subtotal_bs": f.get("subtotal_bs"), "iva_bs": f.get("iva_bs"), "total_bs": f.get("total_bs"),
        "pagos": [{"metodo": p["nombre_metodo"], "monto": p["monto"], "moneda": p["moneda"],
                   "tasa": p.get("tasa_aplicada"), "referencia": p.get("referencia"),
                   "fecha": p.get("fecha_pago"), "observacion": p.get("observacion"),
                   "estado": p.get("estado")} for p in pagos],
    }


# --------------------------------------------------------------------------- dibujo
def _logo_png(ancho_px: int = 1400):
    """(BytesIO, ancho, alto) del logotipo sobre blanco, sin deformarlo; None si el archivo no existe."""
    try:
        import marca
        from PIL import Image
        logo = marca.logo_pil(ancho_px)
        if logo is None:
            return None
        alfa = logo.getchannel("A").point(lambda v: 0 if v < 40 else v)     # quita la neblina tenue del archivo original
        fondo = Image.new("RGB", logo.size, (255, 255, 255))
        fondo.paste(logo, mask=alfa)
        buf = io.BytesIO()
        fondo.save(buf, "PNG")
        buf.seek(0)
        return buf, logo.width, logo.height
    except Exception:
        return None


def generar_pdf(datos: dict, ruta: str) -> str:
    """Dibuja el comprobante y lo guarda en ``ruta``. Devuelve la ruta."""
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer,
                                        Table, TableStyle)
    except ImportError as ex:
        raise DependenciaFaltante(
            "Falta la biblioteca «reportlab» para crear PDF.\n\n"
            "Instálela con:  py -m pip install reportlab") from ex

    H = HexColor
    ancho_pag, alto_pag = A4
    mizq = mder = 18 * mm
    msup, minf = 20 * mm, 24 * mm
    W = ancho_pag - mizq - mder

    e = datos["empresa"]
    c = datos["cliente"]
    tasa = datos.get("tasa")
    en_bs = bool(tasa) and datos.get("total_bs") is not None      # False = factura histórica sin tasa BCV
    moneda_txt = _bs if en_bs else _usd

    # ---- estilos
    def est(nombre, **kw):
        base = dict(fontName="Helvetica", fontSize=9, leading=11.5, textColor=H(TEXTO))
        base.update(kw)
        return ParagraphStyle(nombre, **base)

    s_normal = est("n")
    s_pequeno = est("pq", fontSize=7.5, leading=9.5, textColor=H(GRIS_TEXTO))
    s_label = est("lb", fontName="Helvetica-Bold", fontSize=6.8, leading=8.5, textColor=H(GRIS_TEXTO))
    s_valor = est("vl", fontName="Helvetica-Bold", fontSize=9.5, leading=12)
    s_seccion = est("sec", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=H(AZUL_OSCURO))
    s_th = est("th", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=H("#FFFFFF"))
    s_th_der = est("thd", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=H("#FFFFFF"),
                   alignment=TA_RIGHT)
    s_th_cen = est("thc", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=H("#FFFFFF"),
                   alignment=TA_CENTER)
    s_celda = est("ce", fontSize=8.5, leading=10.5)
    s_celda_b = est("ceb", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)
    s_der = est("de", fontSize=8.5, leading=10.5, alignment=TA_RIGHT)
    s_der_b = est("deb", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, alignment=TA_RIGHT)
    s_cen = est("cen", fontSize=8.5, leading=10.5, alignment=TA_CENTER)
    s_tot_et = est("te", fontSize=9, leading=11, textColor=H(GRIS_TEXTO))
    s_tot_val = est("tv", fontName="Helvetica-Bold", fontSize=9.5, leading=11.5, alignment=TA_RIGHT)
    s_gran_et = est("ge", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=H("#FFFFFF"))
    s_gran_val = est("gv", fontName="Helvetica-Bold", fontSize=13, leading=15, textColor=H("#FFFFFF"),
                     alignment=TA_RIGHT)

    def seccion(titulo):
        t = Table([[Paragraph(_p(titulo), s_seccion)]], colWidths=[W])
        t.setStyle(TableStyle([
            ("LINEBEFORE", (0, 0), (0, 0), 3, H(AZUL)), ("LINEBELOW", (0, 0), (0, 0), 0.8, H(PLATA)),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    historia = []

    # ================================================================ 1. ENCABEZADO: logo | datos de la empresa (centro) | comprobante
    logo = _logo_png()
    ancho_logo = 46 * mm
    izq = ""
    if logo:
        buf, lw, lh = logo
        izq = Image(buf, width=ancho_logo, height=ancho_logo * lh / lw)
    s_cen_rs = est("rs", fontName="Helvetica-Bold", fontSize=8.6, leading=11, textColor=H(AZUL_OSCURO), alignment=TA_CENTER)
    s_cen_tx = est("ctx", fontSize=8.3, leading=10.8, alignment=TA_CENTER)
    centro = [Paragraph(_p(e["razon_social"]), s_cen_rs), Spacer(1, 3)]
    if e.get("rif"):
        centro.append(Paragraph(f"<b>RIF:</b> {_p(e['rif'])}", s_cen_tx))
    if e.get("direccion_fiscal"):
        centro.append(Paragraph(f"<b>Dirección fiscal:</b> {_p(e['direccion_fiscal'])}", s_cen_tx))
    contacto = " · ".join(x for x in (
        f"Tel.: {_t(e['telefono'])}" if e.get("telefono") else "", _t(e.get("correo"))) if x)
    if contacto:
        centro.append(Paragraph(escape(contacto), est("ct", fontSize=7.5, leading=9.5, textColor=H(GRIS_TEXTO),
                                                      alignment=TA_CENTER)))

    s_blanco_p = est("bp", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=H(PLATA))
    s_blanco_g = est("bg", fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=H("#FFFFFF"))
    s_blanco_l = est("bl", fontSize=6.8, leading=8.5, textColor=H(PLATA))
    s_blanco_v = est("bv", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=H("#FFFFFF"))
    der = [Paragraph("COMPROBANTE DE PAGO", s_blanco_p),
           Paragraph(f"N° {_p(datos['numero_comprobante'])}", s_blanco_g),
           Spacer(1, 4),
           Paragraph("FACTURA ASOCIADA", s_blanco_l), Paragraph(_p(datos["nro_factura"]), s_blanco_v),
           Spacer(1, 3),
           Paragraph("FECHA Y HORA DE EMISIÓN", s_blanco_l), Paragraph(_p(_fecha_hora(datos["fecha_emision"])), s_blanco_v)]
    estado = _t(datos.get("estado"))
    if estado and estado.upper() != "EMITIDA":
        der += [Spacer(1, 3), Paragraph("ESTADO", s_blanco_l), Paragraph(_p(estado.upper()), s_blanco_v)]

    ancho_der = 158
    ancho_izq = ancho_logo + 10
    cab = Table([[izq, centro, der]], colWidths=[ancho_izq, W - ancho_izq - ancho_der, ancho_der])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (1, 0), "MIDDLE"), ("VALIGN", (2, 0), (2, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 8), ("RIGHTPADDING", (1, 0), (1, 0), 12),
        ("LINEBEFORE", (1, 0), (1, 0), 0.8, H(PLATA)),
        ("BACKGROUND", (2, 0), (2, 0), H(AZUL_OSCURO)), ("LINEBEFORE", (2, 0), (2, 0), 3, H(AZUL)),
        ("LEFTPADDING", (2, 0), (2, 0), 12), ("RIGHTPADDING", (2, 0), (2, 0), 8),
        ("TOPPADDING", (2, 0), (2, 0), 10), ("BOTTOMPADDING", (2, 0), (2, 0), 10),
        ("TOPPADDING", (0, 0), (1, 0), 0), ("BOTTOMPADDING", (0, 0), (1, 0), 0)]))
    historia += [cab, Spacer(1, 16)]

    # ================================================================ 2. CLIENTE
    def celda(label, valor):
        return [Paragraph(_p(label).upper(), s_label), Paragraph(_p(valor) or "—", s_valor)]

    filas, spans = [[celda("Cliente / Razón social", c.get("nombre")), "", ""]], [("SPAN", (0, 0), (2, 0))]
    trio = [celda("Tipo y N° de documento", c.get("documento") or f"{c.get('tipo') or ''}-{c.get('numero') or ''}")]
    if c.get("telefono"):
        trio.append(celda("Teléfono", c["telefono"]))
    if c.get("codigo"):
        trio.append(celda("Código de cliente", c["codigo"]))
    while len(trio) < 3:
        trio.append("")
    filas.append(trio)
    if c.get("direccion"):
        filas.append([celda("Dirección fiscal", c["direccion"]), "", ""])
        spans.append(("SPAN", (0, 2), (2, 2)))
    ct = Table(filas, colWidths=[W * 0.42, W * 0.30, W * 0.28])
    ct.setStyle(TableStyle(spans + [
        ("BACKGROUND", (0, 0), (-1, -1), H(PLATA_CLARA)), ("BOX", (0, 0), (-1, -1), 0.6, H(PLATA)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    historia += [seccion("DATOS DEL CLIENTE"), Spacer(1, 6), ct, Spacer(1, 16)]

    # ================================================================ 3. DETALLE (Bs.)
    suf = "(Bs.)" if en_bs else "(USD)"
    filas = [[Paragraph("N°", s_th_cen), Paragraph("CÓDIGO", s_th), Paragraph("DESCRIPCIÓN", s_th),
              Paragraph("CANT.", s_th_cen), Paragraph(f"PRECIO UNIT. {suf}", s_th_der),
              Paragraph(f"IMPORTE {suf}", s_th_der)]]
    for i, ln in enumerate(datos["lineas"], 1):
        pu = mon.D(ln["precio_usd"])
        imp = mon.D(ln["importe_usd"]) if ln.get("importe_usd") is not None else mon.q2(pu * ln["cantidad"])
        if en_bs:
            pu_txt, imp_txt = _num(mon.a_bs(pu, tasa)), _num(mon.a_bs(imp, tasa))
        else:
            pu_txt, imp_txt = _num(pu), _num(imp)
        filas.append([Paragraph(str(i), s_cen), Paragraph(_p(ln["codigo"]), s_celda_b),
                      Paragraph(_p(ln.get("descripcion")) or "—", s_celda),
                      Paragraph(str(int(ln["cantidad"])), s_cen), Paragraph(pu_txt, s_der), Paragraph(imp_txt, s_der_b)])
    anchos = [26, 92, 0, 38, 92, 96]
    anchos[2] = W - sum(anchos)
    det = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [("BACKGROUND", (0, 0), (-1, 0), H(AZUL_OSCURO)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
              ("LINEBELOW", (0, 1), (-1, -1), 0.5, H(PLATA)), ("LINEBELOW", (0, -1), (-1, -1), 1, H(AZUL_OSCURO))]
    for r in range(2, len(filas), 2):
        estilo.append(("BACKGROUND", (0, r), (-1, r), H(PLATA_CLARA)))
    det.setStyle(TableStyle(estilo))
    historia += [seccion("DETALLE DE LA OPERACIÓN"), Spacer(1, 6), det, Spacer(1, 10)]

    # ================================================================ 4. TOTALES
    sub = datos["subtotal_bs"] if en_bs else datos["subtotal_usd"]
    iva = datos["iva_bs"] if en_bs else datos["iva_usd"]
    tot = datos["total_bs"] if en_bs else datos["total_usd"]
    pct = ""
    try:
        if abs(mon.D(datos["iva_usd"]) - mon.q2(mon.D(datos["subtotal_usd"]) * ventas_repo.IVA)) <= Decimal("0.01"):
            pct = f" ({(ventas_repo.IVA * 100).normalize():f}%)"     # solo si el IVA guardado coincide con la tasa del sistema
    except Exception:
        pct = ""
    tt = Table([
        [Paragraph("Base imponible", s_tot_et), Paragraph(moneda_txt(sub), s_tot_val)],
        [Paragraph(f"IVA{pct}", s_tot_et), Paragraph(moneda_txt(iva), s_tot_val)],
        [Paragraph("TOTAL A PAGAR", s_gran_et), Paragraph(moneda_txt(tot), s_gran_val)]],
        colWidths=[130, 170], hAlign="RIGHT")
    tt.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, H(PLATA)), ("BACKGROUND", (0, 2), (-1, 2), H(AZUL)),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, 1), 5), ("BOTTOMPADDING", (0, 0), (-1, 1), 5),
        ("TOPPADDING", (0, 2), (-1, 2), 8), ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    historia += [KeepTogether([tt]), Spacer(1, 18)]

    # ================================================================ 5. PAGOS (tal como se registraron)
    filas = [[Paragraph("MÉTODO DE PAGO", s_th), Paragraph("MONEDA", s_th), Paragraph("IMPORTE RECIBIDO", s_th_der),
              Paragraph("REFERENCIA", s_th), Paragraph("FECHA DEL PAGO", s_th)]]
    nombres_moneda = {"USD": "Dólares (USD)", "VES": "Bolívares (VES)"}
    for pg in datos["pagos"]:
        mo = _t(pg.get("moneda") or "USD").upper()
        importe = _bs(pg["monto"]) if mo == "VES" else (_usd(pg["monto"]) if mo == "USD" else f"{mo} {_num(pg['monto'])}")
        celda_imp = [Paragraph(f"<b>{escape(importe)}</b>", s_der)]
        if mo == "VES" and pg.get("tasa"):
            celda_imp.append(Paragraph(f"Tasa: Bs. {_tasa(pg['tasa'])} por USD", est(
                "tp", fontSize=7, leading=9, textColor=H(GRIS_TEXTO), alignment=TA_RIGHT)))
        metodo = [Paragraph(_p(pg["metodo"]), s_celda_b)]
        extra = []
        if pg.get("estado") and _t(pg["estado"]).upper() != "REGISTRADO":
            extra.append(f"Estado: {_t(pg['estado'])}")
        if pg.get("observacion"):
            extra.append(_t(pg["observacion"]))
        if extra:
            metodo.append(Paragraph(escape(" · ".join(extra)), est("ob", fontName="Helvetica-Oblique", fontSize=7,
                                                                   leading=9, textColor=H(GRIS_TEXTO))))
        filas.append([metodo, Paragraph(_p(nombres_moneda.get(mo, mo)), s_celda), celda_imp,
                      Paragraph(_p(pg.get("referencia")) or "—", s_celda),
                      Paragraph(_p(_fecha_hora(pg.get("fecha"))), s_celda)])
    if not datos["pagos"]:
        filas.append([Paragraph("No hay pagos registrados para esta factura.", s_celda), "", "", "", ""])
    anchos = [112, 80, 134, 0, 88]
    anchos[3] = W - sum(anchos)
    pt = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [("BACKGROUND", (0, 0), (-1, 0), H(AZUL_OSCURO)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
              ("LINEBELOW", (0, 1), (-1, -1), 0.5, H(PLATA)), ("LINEBELOW", (0, -1), (-1, -1), 1, H(AZUL_OSCURO))]
    if not datos["pagos"]:
        estilo.append(("SPAN", (0, 1), (-1, 1)))
    for r in range(2, len(filas), 2):
        estilo.append(("BACKGROUND", (0, r), (-1, r), H(PLATA_CLARA)))
    pt.setStyle(TableStyle(estilo))
    historia += [KeepTogether([seccion("FORMA(S) DE PAGO REGISTRADA(S)"), Spacer(1, 6), pt]), Spacer(1, 16)]

    # ================================================================ 6. REFERENCIA INFORMATIVA (USD)
    s_ref_t = est("rt", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=H(GRIS_TEXTO))
    s_ref = est("rf", fontSize=8.5, leading=11.5, textColor=H(GRIS_TEXTO))
    if en_bs:
        ref = [Paragraph("REFERENCIA INFORMATIVA", s_ref_t),
               Paragraph(f"Equivalente aproximado: <b>{escape(_usd(datos['total_usd']))}</b>", s_ref),
               Paragraph(f"Tasa aplicada: <b>Bs. {_tasa(tasa)} por USD</b> · Fecha efectiva de la tasa: "
                         f"{_p(_fecha(datos.get('fecha_tasa')))}", s_ref),
               Paragraph("Valor únicamente informativo; el importe a pagar es el total expresado en bolívares.",
                         est("ri", fontName="Helvetica-Oblique", fontSize=7.5, leading=9.5, textColor=H(GRIS_TEXTO)))]
    else:
        ref = [Paragraph("FACTURA HISTÓRICA", s_ref_t),
               Paragraph("Esta factura es anterior al registro de la tasa BCV en el sistema. Sus importes se muestran en "
                         "USD tal como fueron emitidos; no se recalculan ni se convierten a bolívares.", s_ref)]
    rt = Table([[ref]], colWidths=[W])
    rt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, H(PLATA), None, (3, 2)), ("BACKGROUND", (0, 0), (-1, -1), H(PLATA_CLARA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    historia.append(KeepTogether([rt]))

    # ================================================================ página
    generado = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    titulo_doc = f"Comprobante de pago N° {datos['numero_comprobante']}"

    def decorar(cv, doc, primera):
        cv.saveState()
        cv.setFillColor(H(AZUL_OSCURO))
        cv.rect(0, alto_pag - 9 * mm, ancho_pag, 9 * mm, stroke=0, fill=1)
        cv.setFillColor(H(AZUL))
        cv.rect(0, alto_pag - 9 * mm - 1.6 * mm, ancho_pag, 1.6 * mm, stroke=0, fill=1)
        cv.setFillColor(H(PLATA))
        cv.rect(0, alto_pag - 9 * mm - 2.4 * mm, ancho_pag, 0.8 * mm, stroke=0, fill=1)
        if not primera:
            cv.setFillColor(H(GRIS_TEXTO))
            cv.setFont("Helvetica-Bold", 8)
            cv.drawString(mizq, alto_pag - 16 * mm, _t(e["razon_social"]))
            cv.setFont("Helvetica", 8)
            cv.drawRightString(ancho_pag - mder, alto_pag - 16 * mm, f"{titulo_doc} · Factura {_t(datos['nro_factura'])}")
        # pie
        cv.setStrokeColor(H(PLATA))
        cv.setLineWidth(0.8)
        cv.line(mizq, 17 * mm, ancho_pag - mder, 17 * mm)
        cv.setFillColor(H(GRIS_TEXTO))
        cv.setFont("Helvetica-Oblique", 7.5)
        cv.drawString(mizq, 12.5 * mm, NOTA_PIE)
        cv.setFont("Helvetica", 7)
        cv.drawString(mizq, 8.5 * mm, f"Documento generado el {generado}")
        cv.restoreState()

    class _Lienzo(rl_canvas.Canvas):
        """Numeración «Página X de Y»: se dibuja al final, cuando ya se conoce el total de páginas."""
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado_pag in self._paginas:
                self.__dict__.update(estado_pag)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(H(GRIS_TEXTO))
                self.drawRightString(ancho_pag - mder, 12.5 * mm, f"Página {self._pageNumber} de {total}")
                super().showPage()
            super().save()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=mizq, rightMargin=mder, topMargin=msup, bottomMargin=minf,
                          title=titulo_doc, author=_t(e["razon_social"]),
                          subject=f"Factura {_t(datos['nro_factura'])}", creator="Sistema_QR")
    marco = Frame(mizq, minf, W, alto_pag - msup - minf, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="primera", frames=[marco], onPage=lambda cv, d: decorar(cv, d, True), autoNextPageTemplate="resto"),
        PageTemplate(id="resto", frames=[marco], onPage=lambda cv, d: decorar(cv, d, False))])
    doc.build(historia, canvasmaker=_Lienzo)

    with open(ruta, "wb") as f:        # el PDF ya está completo en memoria: no quedan archivos a medias si algo falla
        f.write(buf.getvalue())
    return ruta


def generar_comprobante_pdf(id_factura: int, ruta: str) -> str:
    """Lee la factura guardada y crea su comprobante en ``ruta``. No modifica nada en la base de datos."""
    return generar_pdf(datos_comprobante(id_factura), ruta)
