# Comprobante de pago en PDF («Descargar PDF»)

## Qué cambió
- En la ventana de la factura (al emitirla y al abrirla desde Facturación), el botón **Copiar** se sustituyó por **Descargar PDF**.
  Pide dónde guardar el archivo (nombre sugerido `Comprobante_Pago_000125.pdf`) y genera un PDF A4 con diseño empresarial.
- Es solo consulta: lee la factura ya guardada. No registra ventas, no toca pagos, IVA, inventario ni la base de datos.

## Archivos
| Archivo | Cambio |
|---|---|
| `sistema/comprobante_pdf.py` | **Nuevo.** Arma los datos y dibuja el PDF (ReportLab). |
| `sistema/empresa.py` | **Nuevo.** Lee los datos de la empresa. |
| `recursos/empresa.json` | **Nuevo.** RIF y dirección fiscal de la empresa (ver abajo). |
| `sistema/main_gui.py` | Botón «Descargar PDF» y método `descargar_pdf`. |
| `sistema/ventas_repo.py` | `obtener_factura` ahora también devuelve (solo lectura) dirección, teléfono y código del cliente, y fecha, nota y estado de cada pago. |
| `requirements.txt` | Se agregó `reportlab`. |
| `pruebas/probar_comprobante_pdf.py` | Genera PDF de ejemplo sin base de datos. |

## ANTES DE USARLO
1. Instalar la dependencia: `py -m pip install reportlab`
2. **Completar `recursos/empresa.json`** con el RIF y la dirección fiscal reales. La base de datos del sistema no guarda esos datos,
   y no se inventaron. Si faltan, el programa avisa antes de generar y esas líneas no se imprimen.

## Contenido del PDF
- Encabezado: logotipo (proporciones originales), razón social, RIF, dirección fiscal; N° de comprobante, factura asociada, fecha y hora.
- Cliente: nombre, tipo y número de documento, teléfono, código y dirección fiscal (los que existan).
- Detalle: precios unitarios e importes **solo en bolívares**; base imponible, IVA y TOTAL A PAGAR en bolívares (valores guardados en la factura).
- Pagos tal como se registraron: método, moneda, importe recibido, referencia, fecha, nota y tasa aplicada (pagos en Bs.). Uno por fila; sin conversiones.
- Al final, aparte: «Referencia informativa» con equivalente aproximado en USD (total guardado) y tasa aplicada.
- Nota al pie: comprobante de pago que no sustituye la factura fiscal. Varias páginas con encabezado repetido y «Página X de Y».

## Facturas históricas
Las anteriores al registro de la tasa BCV no tienen importes en Bs. guardados. Se imprimen en USD tal como fueron emitidas, con un aviso, sin convertir.

## Notas
- El número de comprobante es el mismo número de la factura (F-000125 → 000125); no existe otra numeración guardada.
- El precio e importe por línea en Bs. se calculan con la tasa guardada de la factura; los totales son los guardados. Por redondeo, la suma de líneas podría diferir en céntimos del subtotal.
- La pantalla de texto de la factura y el archivo `facturas/F-xxxxxx.txt` no cambiaron.

## Actualización: PDF automático y datos de la empresa
- `recursos/empresa.json` ya trae razón social, RIF (J-3108592-3) y dirección fiscal (según la nota del 7/2/2026). Verifique el RIF.
  Los teléfonos de esa nota son contactos internos (RR.HH. y consultora de TI), por eso no se imprimen; el campo `telefono` queda vacío.
- Encabezado del PDF: logotipo a la izquierda, datos de la empresa al centro justo al lado, y el recuadro del comprobante a la derecha.
- Al **emitir una factura** ya no aparece la pantalla de texto: el PDF se crea solo en `facturas/Comprobante_Pago_XXXXXX.pdf` y se abre de inmediato.
  Si falla, la factura queda emitida y se avisa el motivo.
- En **Facturación**, doble clic abre el PDF de esa factura; el botón «Descargar PDF» permite elegir dónde guardarlo.
- Ya no se crea el `.txt` de cada factura nueva (los existentes se conservan).
