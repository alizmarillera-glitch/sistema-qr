"""Producción por lotes: materia prima, órdenes con sus 9 pasos, control de calidad, no conformes y liberación a stock.

Cada orden (lote) tiene su propio seguimiento de 9 etapas: crear una orden nueva genera filas nuevas en ``orden_etapas``
y nunca reutiliza ni modifica las de órdenes anteriores. Todas las escrituras son transacciones (se confirman o se
revierten completas) y bloquean el registro de la orden con ``FOR UPDATE`` para que dos usuarios no avancen el mismo
paso a la vez.

Reglas del flujo
* Al crear una orden se descuenta la materia prima indicada y el paso 1 queda «En proceso»; los demás, «Pendiente».
* Al completar un paso se registra su resultado (recibidas, procesadas, aprobadas, rechazadas, pendientes, motivo,
  defectos, observaciones, responsable, fecha y hora). Solo las piezas aprobadas continúan al paso siguiente, que pasa
  a «En proceso». Si no queda ninguna aprobada, el lote se cierra sin producción aprobada.
* Las piezas rechazadas se guardan en ``productos_no_conformes`` (registro independiente) y nunca llegan al stock.
* Las piezas pendientes de evaluación quedan retenidas en la etapa hasta que se resuelvan.
* Los pasos 1 a 3 trabajan con materia prima (sin conteo de piezas); desde el paso 4 se cuentan piezas.
* Al completar el paso 9 (liberación) las piezas aprobadas entran UNA sola vez al stock del pistón con un movimiento
  de tipo PRODUCCION vinculado al lote y a la orden. La bandera ``liberada`` y el bloqueo de la fila impiden repetirlo.
* Un reproceso de no conformes es una operación aparte, con su propia inspección, limitada al saldo no conforme.
* Cada pieza que el reproceso descarta es un rechazo DEFINITIVO: se copia en ``rechazos_definitivos``, un historial permanente
  (la base de datos impide modificarlo o borrarlo) que alimenta el botón «Historial» de Existencias.

Permisos (se validan aquí, no solo en la pantalla)
* El Administrador gestiona todo el flujo (Inventario es un módulo, no un rol).
* CONTROL solo modifica la etapa que tiene asignada (``usuarios.etapa_asignada``, 1 a 9): únicamente cuando el lote está en
  ese paso, y solo los pendientes y no conformes originados en ese paso. Puede consultar todo lo demás.
"""
import re
from datetime import date, datetime, timedelta

import conexion as db

PASOS = (
    "Recepción de materia prima",
    "Inspección de materia prima",
    "Fundición del aluminio",
    "Moldeado del pistón",
    "Tratamiento térmico",
    "Mecanizado y acabado",
    "Inspección final",
    "Almacén de productos aprobados",
    "Liberación de productos para la venta",
)
PRIMER_PASO_PIEZAS = 4          # desde aquí se cuentan piezas aprobadas/rechazadas/pendientes
PASO_INSPECCION_FINAL = 7
PASO_ALMACEN = 8
PASO_LIBERACION = 9
ULTIMO_PASO = len(PASOS)

ESTADO_TXT = {
    "PENDIENTE": "Pendiente",
    "EN_PROCESO": "En proceso",
    "COMPLETADO": "Completado",
    "COMPLETADO_OBS": "Completado con observaciones",
    "BLOQUEADO": "Bloqueado",
}
ESTADOS_COMPLETOS = ("COMPLETADO", "COMPLETADO_OBS")
ROL_CONTROL = "CONTROL"
ROLES_GESTION = ("Administrador",)
_RE_LOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,29}$")


# =========================================================================== reglas puras (sin base de datos)
def _n(v):
    return int(v or 0)


def pendiente_vigente(etapa):
    """Piezas de la etapa que siguen retenidas, sin evaluar."""
    return max(0, _n(etapa.get("pendientes")) - _n(etapa.get("pend_aprobados")) - _n(etapa.get("pend_rechazados")))


def piezas_recibidas(etapas_orden, cantidad_plan, paso):
    """Piezas que llegan al ``paso``: el plan en el primero con piezas; después, las aprobadas de la etapa anterior."""
    if paso < PRIMER_PASO_PIEZAS:
        return 0
    if paso == PRIMER_PASO_PIEZAS:
        return int(cantidad_plan)
    ant = next((e for e in etapas_orden if e["paso"] == paso - 1), None)
    if not ant or ant["estado"] not in ESTADOS_COMPLETOS:
        return 0
    return _n(ant["aprobados"]) + _n(ant.get("pend_aprobados"))


def validar_resultado(recibida, procesada, aprobada, rechazada, pendiente, motivo, responsable):
    """Valida el resultado de una etapa con piezas. Lanza ValueError con un mensaje claro si algo no cuadra."""
    for rotulo, v in (("procesada", procesada), ("aprobada", aprobada), ("rechazada", rechazada), ("pendiente", pendiente)):
        if v < 0:
            raise ValueError(f"La cantidad {rotulo} no puede ser negativa.")
    if procesada != recibida:
        raise ValueError(f"Deben procesarse las {recibida} piezas recibidas (indicó {procesada}). "
                         "Las que no pudo evaluar regístrelas como pendientes.")
    if aprobada + rechazada + pendiente != procesada:
        raise ValueError(f"Aprobadas ({aprobada}) + rechazadas ({rechazada}) + pendientes ({pendiente}) = "
                         f"{aprobada + rechazada + pendiente}; debe coincidir con las procesadas ({procesada}).")
    if rechazada > 0 and not (motivo or "").strip():
        raise ValueError("Indique el motivo de los rechazos.")
    if not (responsable or "").strip():
        raise ValueError("Indique el responsable de la inspección.")


def estado_resultado(rechazada, pendiente, observaciones):
    """«Completado» si todo salió limpio; «Completado con observaciones» si hubo rechazos, retenidas u observaciones."""
    return "COMPLETADO_OBS" if (rechazada or pendiente or (observaciones or "").strip()) else "COMPLETADO"


def estado_nc(nc):
    """Texto del estado de un registro de no conformes según lo recuperado y descartado."""
    cant, rec, des = _n(nc["cantidad"]), _n(nc["recuperadas"]), _n(nc["descartadas"])
    if rec + des == 0:
        return "No conforme"
    if rec + des < cant:
        return "Reproceso parcial"
    if rec == cant:
        return "Recuperado"
    return "Descartado" if rec == 0 else "Cerrado"


def saldo_nc(nc):
    return max(0, _n(nc["cantidad"]) - _n(nc["recuperadas"]) - _n(nc["descartadas"]))


def resumen_lote(orden, etapas_orden, recuperadas=0):
    """Cifras de UN lote para la pantalla: aprobadas, rechazadas, pendientes, etapa actual y avance.

    ``recuperadas``: piezas del lote que ya se recuperaron por reproceso. Se restan de las rechazadas para que una pieza
    recuperada no se siga contando como rechazada (el historial de cada etapa conserva el rechazo original).
    """
    if not orden:
        return {"aprobadas": 0, "rechazadas": 0, "pendientes": 0, "paso": 1, "completados": 0, "pct": 0,
                "estado_paso": "PENDIENTE"}
    rechazadas = max(0, sum(_n(e["rechazados"]) + _n(e.get("pend_rechazados")) for e in etapas_orden) - _n(recuperadas))
    pendientes = sum(pendiente_vigente(e) for e in etapas_orden)
    con_piezas = [e for e in etapas_orden if e["paso"] >= PRIMER_PASO_PIEZAS and e["estado"] in ESTADOS_COMPLETOS]
    if _n(orden.get("liberada")):
        aprobadas = _n(orden.get("aprobados_final"))
    elif con_piezas:
        ult = max(con_piezas, key=lambda e: e["paso"])
        aprobadas = _n(ult["aprobados"]) + _n(ult.get("pend_aprobados"))
    else:
        aprobadas = 0
    completados = sum(1 for e in etapas_orden if e["estado"] in ESTADOS_COMPLETOS)
    actual = next((e for e in etapas_orden if e["paso"] == _n(orden["paso_actual"])), None)
    return {"aprobadas": aprobadas, "rechazadas": rechazadas, "pendientes": pendientes,
            "paso": _n(orden["paso_actual"]), "completados": completados,
            "pct": round(100 * completados / ULTIMO_PASO), "estado_paso": actual["estado"] if actual else "PENDIENTE"}


def _limpiar(texto, largo):
    return (texto or "").strip()[:largo]


# =========================================================================== permisos por rol y etapa
class SinPermiso(ValueError):
    """El usuario no puede realizar la operación. Hereda de ValueError: la pantalla la muestra como aviso."""


def nombre_control(etapa):
    """«Control 5 · Tratamiento térmico» (o «Sin etapa asignada»)."""
    e = _n(etapa)
    return f"Control {e} · {PASOS[e - 1]}" if 1 <= e <= ULTIMO_PASO else "Sin etapa asignada"


def puede_modificar_paso(rol, etapa, paso):
    """Regla pura: ¿puede un usuario con ``rol`` y ``etapa`` asignada modificar el ``paso`` indicado?"""
    if rol in ROLES_GESTION:
        return True
    if rol == ROL_CONTROL:
        return 1 <= _n(etapa) <= ULTIMO_PASO and _n(etapa) == _n(paso)
    return False


def _datos_usuario(id_usuario, cur=None):
    sql = ("SELECT r.nombre_rol AS rol, u.etapa_asignada AS etapa, u.estado AS activo FROM usuarios u "
           "JOIN roles r ON r.id_rol=u.id_rol WHERE u.id_usuario=%s")
    if cur is not None:
        cur.execute(sql, (id_usuario,))
        return cur.fetchone()
    return db.consulta(sql, (id_usuario,), uno=True)


def motivo_sin_permiso(rol, etapa, paso):
    """Texto que explica por qué ``rol``/``etapa`` no puede modificar ``paso``; None si sí puede (la pantalla lo reutiliza)."""
    if puede_modificar_paso(rol, etapa, paso):
        return None
    if rol == ROL_CONTROL:
        if not 1 <= _n(etapa) <= ULTIMO_PASO:
            return "Su usuario CONTROL no tiene una etapa asignada. Solicítela al administrador."
        return (f"Su usuario solo puede modificar el paso {_n(etapa)} ({PASOS[_n(etapa) - 1]}). "
                f"Esta operación corresponde al paso {_n(paso)} ({PASOS[_n(paso) - 1]}).")
    return "No tiene permiso para modificar la producción."


def exigir_paso(id_usuario, paso, cur=None):
    """Lanza SinPermiso si el usuario no puede modificar ``paso``. ``id_usuario=None`` = operación interna (sin control)."""
    if id_usuario is None:
        return
    u = _datos_usuario(id_usuario, cur)
    if not u or not _n(u["activo"]):
        raise SinPermiso("Su usuario no existe o está desactivado.")
    motivo = motivo_sin_permiso(u["rol"], u["etapa"], paso)
    if motivo:
        raise SinPermiso(motivo)


def exigir_gestion(id_usuario, cur=None, accion="realizar esta operación"):
    """Operaciones que no pertenecen a una etapa (crear órdenes, recibir materia prima): solo el Administrador."""
    if id_usuario is None:
        return
    u = _datos_usuario(id_usuario, cur)
    if not u or not _n(u["activo"]):
        raise SinPermiso("Su usuario no existe o está desactivado.")
    if u["rol"] in ROLES_GESTION:
        return
    if u["rol"] == ROL_CONTROL:
        raise SinPermiso(f"Los usuarios CONTROL solo pueden modificar su etapa asignada; no pueden {accion}.")
    raise SinPermiso(f"No tiene permiso para {accion}.")


# =========================================================================== lectura
_SQL_ORDEN = """SELECT o.*, p.codigo_piston AS codigo, p.descripcion AS modelo,
    (SELECT et.estado FROM orden_etapas et WHERE et.id_orden=o.id_orden AND et.paso=o.paso_actual) AS estado_paso
    FROM ordenes_produccion o LEFT JOIN pistones p ON p.id_piston=o.id_piston"""


def saldo_materia_prima(cur=None):
    sql = "SELECT COALESCE(SUM(CASE WHEN tipo='CONSUMO' THEN -kg ELSE kg END),0) AS kg FROM materia_prima_mov"
    if cur is not None:
        cur.execute(sql)
        fila = cur.fetchone()
        return float((list(fila.values())[0] if isinstance(fila, dict) else fila[0]) or 0)
    return float((db.consulta(sql, uno=True) or {}).get("kg") or 0)


def resumen():
    """Indicadores superiores: siempre los totales de TODOS los lotes y del inventario."""
    r = db.consulta("""SELECT
        (SELECT COALESCE(SUM(CASE WHEN tipo='CONSUMO' THEN -kg ELSE kg END),0) FROM materia_prima_mov) AS mp_kg,
        (SELECT COALESCE(SUM(stock),0) FROM existencias) AS aprobados,
        (SELECT COALESCE(SUM(GREATEST(0, pendientes-pend_aprobados-pend_rechazados)),0) FROM orden_etapas) AS pendientes,
        (SELECT COALESCE(SUM(cantidad-recuperadas),0) FROM productos_no_conformes) AS rechazados,
        (SELECT COUNT(*) FROM ordenes_produccion WHERE estado='EN_PRODUCCION') AS activas""", uno=True) or {}
    return {"mp_kg": float(r.get("mp_kg") or 0), "aprobados": _n(r.get("aprobados")),
            "pendientes": _n(r.get("pendientes")), "rechazados": _n(r.get("rechazados")),
            "activas": _n(r.get("activas"))}


def ordenes_activas():
    return db.consulta(_SQL_ORDEN + " WHERE o.estado='EN_PRODUCCION' ORDER BY o.id_orden")


def ordenes_finalizadas(limite=300):
    return db.consulta(_SQL_ORDEN + " WHERE o.estado='FINALIZADA' ORDER BY COALESCE(o.fecha_fin,o.creada) DESC, o.id_orden DESC LIMIT %s",
                       (int(limite),))


def orden(id_orden):
    return db.consulta(_SQL_ORDEN + " WHERE o.id_orden=%s", (id_orden,), uno=True)


def etapas(id_orden):
    return db.consulta("SELECT * FROM orden_etapas WHERE id_orden=%s ORDER BY paso", (id_orden,))


def historial(id_orden):
    return db.consulta("""SELECT h.*, u.nombre_usuario AS usuario FROM orden_historial h
        LEFT JOIN usuarios u ON u.id_usuario=h.id_usuario WHERE h.id_orden=%s
        ORDER BY h.fecha_hora, h.id_hist""", (id_orden,))


def movimientos_materia_prima(id_orden):
    return db.consulta("""SELECT m.*, u.nombre_usuario AS usuario FROM materia_prima_mov m
        LEFT JOIN usuarios u ON u.id_usuario=m.id_usuario WHERE m.id_orden=%s ORDER BY m.fecha_hora, m.id_mov""", (id_orden,))


def movimientos_stock_lote(id_orden):
    return db.consulta("""SELECT m.*, p.codigo_piston AS codigo FROM movimientos_inventario m
        JOIN pistones p ON p.id_piston=m.id_piston WHERE m.id_orden=%s ORDER BY m.id_movimiento""", (id_orden,))


def movimientos_inventario(limite=500):
    """Historial general de existencias (apertura, producción, ventas y movimientos anteriores)."""
    return db.consulta("""SELECT m.*, p.codigo_piston AS codigo, f.nro_factura AS numero, u.nombre_usuario AS usuario_nombre
        FROM movimientos_inventario m JOIN pistones p ON p.id_piston=m.id_piston
        LEFT JOIN facturas f ON f.id_factura=m.id_factura LEFT JOIN usuarios u ON u.id_usuario=m.id_usuario
        ORDER BY m.id_movimiento DESC LIMIT %s""", (int(limite),))


def no_conformes(id_orden=None, solo_con_saldo=False, limite=500):
    """Registro independiente de productos rechazados, con lote, modelo y etapa de origen."""
    donde, par = ["1=1"], []
    if id_orden:
        donde.append("nc.id_orden=%s")
        par.append(id_orden)
    if solo_con_saldo:
        donde.append("nc.cantidad-nc.recuperadas-nc.descartadas>0")
    return db.consulta(f"""SELECT nc.*, o.lote, o.codigo_orden, o.liberada, p.codigo_piston AS codigo, p.descripcion AS modelo
        FROM productos_no_conformes nc JOIN ordenes_produccion o ON o.id_orden=nc.id_orden
        LEFT JOIN pistones p ON p.id_piston=nc.id_piston WHERE {' AND '.join(donde)}
        ORDER BY nc.fecha_hora DESC, nc.id_nc DESC LIMIT %s""", tuple(par) + (int(limite),))


def recuperadas_lote(id_orden):
    """Piezas del lote que ya fueron recuperadas por reproceso (salen del conteo de rechazadas)."""
    r = db.consulta("SELECT COALESCE(SUM(recuperadas),0) AS n FROM productos_no_conformes WHERE id_orden=%s", (id_orden,), uno=True)
    return _n((r or {}).get("n"))


def estado_revision(fila):
    """Texto del estado de piezas retenidas de una etapa: En revisión / Revisión parcial / Evaluado."""
    total, vig = _n(fila.get("pendientes")), pendiente_vigente(fila)
    if vig <= 0:
        return "Evaluado"
    return "En revisión" if vig == total else "Revisión parcial"


def puede_aprobar_revision(fila):
    """Las piezas en revisión solo pueden continuar el flujo si el lote sigue en producción y el paso siguiente no se completó."""
    return (fila.get("estado_orden") == "EN_PRODUCCION" and fila.get("estado_siguiente") is not None
            and fila["estado_siguiente"] not in ESTADOS_COMPLETOS)


def en_revision(id_orden=None, solo_vigentes=True, limite=500):
    """Piezas retenidas «en revisión» de TODOS los lotes (o de uno), con el resultado original de la etapa.

    ``solo_vigentes=False`` incluye también las etapas cuyas piezas ya se evaluaron (historial de revisiones).
    """
    donde = ["et.pendientes>0"]
    par = []
    if solo_vigentes:
        donde.append("et.pendientes-et.pend_aprobados-et.pend_rechazados>0")
    if id_orden:
        donde.append("et.id_orden=%s")
        par.append(id_orden)
    return db.consulta(f"""SELECT et.*, o.lote, o.codigo_orden, o.estado AS estado_orden, o.liberada, o.id_piston,
        p.codigo_piston AS codigo, p.descripcion AS modelo,
        (SELECT sg.estado FROM orden_etapas sg WHERE sg.id_orden=et.id_orden AND sg.paso=et.paso+1) AS estado_siguiente
        FROM orden_etapas et JOIN ordenes_produccion o ON o.id_orden=et.id_orden
        LEFT JOIN pistones p ON p.id_piston=o.id_piston WHERE {' AND '.join(donde)}
        ORDER BY et.fecha_hora DESC, et.id_orden DESC, et.paso LIMIT %s""", tuple(par) + (int(limite),))


def reprocesos(id_nc):
    return db.consulta("SELECT r.*, u.nombre_usuario AS usuario FROM nc_reprocesos r LEFT JOIN usuarios u "
                       "ON u.id_usuario=r.id_usuario WHERE r.id_nc=%s ORDER BY r.id_rep", (id_nc,))


# =========================================================================== historial permanente de rechazos definitivos
def _como_fecha_hora(v):
    """datetime de un valor de la base (datetime, date o texto «aaaa-mm-dd hh:mm:ss»)."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    texto = str(v or "").strip()
    for fmt, largo in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(texto[:largo], fmt)
        except ValueError:
            continue
    return None


def limites_periodo(anio, mes=None):
    """(inicio, fin_exclusivo) de un año completo o de un mes concreto."""
    if mes:
        sig = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
        return date(anio, mes, 1), sig
    return date(anio, 1, 1), date(anio + 1, 1, 1)


def rechazos_definitivos(desde=None, hasta=None, mes=None, anio=None, lote=None, id_piston=None, paso=None):
    """Pistones rechazados definitivamente, del más reciente al más antiguo. Todos los filtros son opcionales y se combinan.

    ``desde``/``hasta``: fechas (``date``), ambas inclusive. ``mes`` (1-12) y ``anio``: periodo. ``lote``: código exacto.
    ``id_piston``: modelo. ``paso``: etapa donde ocurrió el defecto (1-9). No hay límite de filas: es un historial completo.
    """
    inicio = desde
    fin = hasta + timedelta(days=1) if hasta else None            # exclusivo
    if anio:
        a, b = limites_periodo(int(anio), int(mes) if mes else None)
        inicio = max(inicio, a) if inicio else a
        fin = min(fin, b) if fin else b
    donde, par = ["1=1"], []
    if inicio:
        donde.append("d.fecha_rechazo>=%s")
        par.append(f"{inicio:%Y-%m-%d} 00:00:00")
    if fin:
        donde.append("d.fecha_rechazo<%s")
        par.append(f"{fin:%Y-%m-%d} 00:00:00")
    if lote:
        donde.append("d.lote=%s")
        par.append(lote)
    if id_piston:
        donde.append("d.id_piston=%s")
        par.append(id_piston)
    if paso:
        donde.append("d.paso=%s")
        par.append(int(paso))
    filas = db.consulta(f"SELECT d.* FROM rechazos_definitivos d WHERE {' AND '.join(donde)} "
                        "ORDER BY d.fecha_rechazo DESC, d.id_rechazo DESC", tuple(par))
    if mes and not anio:                    # un mes «de cualquier año»
        filas = [f for f in filas if (_como_fecha_hora(f["fecha_rechazo"]) or datetime.min).month == int(mes)]
    return filas


def resumen_rechazos(filas):
    """Totales de una lista de rechazos definitivos: piezas, registros y lotes distintos."""
    return {"piezas": sum(_n(f["cantidad"]) for f in filas), "registros": len(filas),
            "lotes": len({f["lote"] for f in filas})}


def rechazados_del_mes(anio, mes):
    """Contador mensual: piezas rechazadas definitivamente en ese mes. Cambiar de mes lo «reinicia» sin borrar nada."""
    return resumen_rechazos(rechazos_definitivos(mes=mes, anio=anio))["piezas"]


def opciones_rechazos():
    """Valores disponibles para los filtros del historial: lotes, modelos y años con rechazos registrados."""
    lotes = [r["lote"] for r in db.consulta("SELECT DISTINCT lote FROM rechazos_definitivos ORDER BY lote")]
    modelos = db.consulta("SELECT DISTINCT id_piston, codigo_piston, modelo FROM rechazos_definitivos "
                          "WHERE id_piston IS NOT NULL ORDER BY codigo_piston")
    dias = db.consulta("SELECT DISTINCT DATE(fecha_rechazo) AS dia FROM rechazos_definitivos")
    anios = sorted({(_como_fecha_hora(r["dia"]) or datetime.min).year for r in dias} - {1}, reverse=True)
    return {"lotes": lotes, "modelos": modelos, "anios": anios}


def trazabilidad(id_orden):
    """Todo lo registrado de un lote, en vivo o finalizado."""
    o = orden(id_orden)
    et = etapas(id_orden) if o else []
    return {"orden": o, "etapas": et, "resumen": resumen_lote(o, et, recuperadas_lote(id_orden) if o else 0),
            "revisiones": en_revision(id_orden, solo_vigentes=False) if o else [],
            "historial": historial(id_orden) if o else [],
            "materia_prima": movimientos_materia_prima(id_orden) if o else [],
            "no_conformes": no_conformes(id_orden) if o else [],
            "stock": movimientos_stock_lote(id_orden) if o else []}


def proximo_lote():
    """Sugerencia de código de lote (AL-001, AL-002…) que no esté usado."""
    usados = {r["lote"] for r in db.consulta("SELECT lote FROM ordenes_produccion")}
    n = 1 + max([int(m.group(1)) for m in (re.match(r"^AL-(\d+)$", x) for x in usados) if m] or [0])
    return f"AL-{n:03d}"


# =========================================================================== escritura
def entrada_materia_prima(kg, descripcion, id_usuario=None):
    exigir_gestion(id_usuario, accion="registrar materia prima")
    if kg <= 0:
        raise ValueError("Los kilogramos deben ser mayores que cero.")
    db.consulta("INSERT INTO materia_prima_mov(tipo,kg,descripcion,id_usuario) VALUES('ENTRADA',%s,%s,%s)",
                (kg, descripcion.strip() or "Recepción de aluminio", id_usuario), commit=True)


def _hist(cur, id_orden, movimiento, cantidad, estado, id_usuario, obs=None):
    cur.execute("INSERT INTO orden_historial(id_orden,movimiento,cantidad,estado,id_usuario,observaciones) "
                "VALUES(%s,%s,%s,%s,%s,%s)", (id_orden, movimiento, cantidad, estado, id_usuario, _limpiar(obs, 255) or None))


def _bloquear_orden(cur, id_orden):
    cur.execute("SELECT * FROM ordenes_produccion WHERE id_orden=%s FOR UPDATE", (id_orden,))
    o = cur.fetchone()
    if not o:
        raise ValueError("La orden ya no existe.")
    return o


def nueva_orden(lote, id_piston, cantidad_plan, kg, fecha_inicio, responsable, observaciones="", id_usuario=None):
    """Crea la orden con su seguimiento NUEVO de 9 etapas y descuenta la materia prima.

    Devuelve (id_orden, codigo_orden, lote). No toca ninguna orden anterior.
    """
    lote = (lote or "").strip().upper()
    if not _RE_LOTE.match(lote):
        raise ValueError("El código del lote debe tener entre 2 y 30 caracteres (letras, números, guion, punto o guion bajo).")
    if not id_piston:
        raise ValueError("Seleccione el pistón (código o modelo) que se fabricará.")
    if cantidad_plan <= 0 or kg <= 0:
        raise ValueError("Indique kilogramos y cantidad de pistones mayores que cero.")
    if not (responsable or "").strip():
        raise ValueError("Indique el responsable de la orden.")
    with db.transaccion(dictionary=True) as (_c, cur):
        exigir_gestion(id_usuario, cur, "crear órdenes de producción")
        cur.execute("SELECT 1 AS x FROM ordenes_produccion WHERE lote=%s", (lote,))
        if cur.fetchone():
            raise ValueError(f"Ya existe un lote con el código {lote}. Use otro código.")
        cur.execute("SELECT activo FROM pistones WHERE id_piston=%s", (id_piston,))
        pis = cur.fetchone()
        if not pis:
            raise ValueError("El pistón seleccionado ya no existe.")
        if not pis["activo"]:
            raise ValueError("El pistón seleccionado está desactivado.")
        disponible = saldo_materia_prima(cur)
        if kg > disponible + 1e-9:
            raise ValueError(f"Materia prima insuficiente. Disponible: {disponible:,.1f} kg.")
        cur.execute("SELECT COALESCE(MAX(id_orden),0)+1 AS n FROM ordenes_produccion")
        n = int(cur.fetchone()["n"])
        codigo = f"OP-{n:03d}"
        cur.execute("INSERT INTO ordenes_produccion(codigo_orden,lote,id_piston,cantidad_plan,kg_aluminio,id_usuario,"
                    "responsable,observaciones,fecha_inicio) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (codigo, lote, id_piston, cantidad_plan, kg, id_usuario, _limpiar(responsable, 80),
                     _limpiar(observaciones, 255) or None, fecha_inicio))
        oid = cur.lastrowid
        for paso in range(1, ULTIMO_PASO + 1):
            cur.execute("INSERT INTO orden_etapas(id_orden,paso,estado,inicio) VALUES(%s,%s,%s,%s)",
                        (oid, paso, "EN_PROCESO" if paso == 1 else "PENDIENTE", datetime.now() if paso == 1 else None))
        cur.execute("INSERT INTO materia_prima_mov(tipo,kg,descripcion,id_orden,id_usuario) VALUES('CONSUMO',%s,%s,%s,%s)",
                    (kg, f"Consumo para producción · {codigo} · lote {lote}", oid, id_usuario))
        _hist(cur, oid, "Consumo de materia prima", f"{kg:g} kg", None, id_usuario, f"Orden {codigo}")
        _hist(cur, oid, "Orden creada", f"{cantidad_plan} pistones", "En proceso", id_usuario,
              f"Lote {lote} · responsable {_limpiar(responsable, 80)}")
    return oid, codigo, lote


def _liberar(cur, o, aprobadas, id_usuario):
    """Entrada de producción al stock. Se ejecuta UNA vez por orden (bandera ``liberada`` + fila bloqueada)."""
    if _n(o["liberada"]):
        raise ValueError("Este lote ya fue liberado al almacén; sus piezas no se vuelven a sumar.")
    anterior = nuevo = None
    if aprobadas > 0:
        if not o["id_piston"]:
            raise ValueError("El lote no tiene un pistón asignado; no se puede incorporar al stock.")
        cur.execute(db.SQL_STOCK_BLOQUEAR, (o["id_piston"],))
        fila = cur.fetchone()
        if not fila:
            raise ValueError("El pistón del lote ya no existe.")
        valores = list(fila.values()) if isinstance(fila, dict) else list(fila)
        if not valores[1]:
            raise ValueError("El pistón del lote está desactivado y no admite entradas.")
        anterior = int(valores[0] or 0)
        nuevo = anterior + aprobadas
        cur.execute(db.SQL_STOCK_FIJAR, (o["id_piston"], nuevo))
        cur.execute("INSERT INTO movimientos_inventario(id_piston,tipo,cantidad,motivo,id_usuario,stock_anterior,stock_nuevo,"
                    "id_orden,lote) VALUES(%s,'PRODUCCION',%s,%s,%s,%s,%s,%s,%s)",
                    (o["id_piston"], aprobadas, f"Entrada de producción · lote {o['lote']} · orden {o['codigo_orden']}",
                     id_usuario, anterior, nuevo, o["id_orden"], o["lote"]))
    cur.execute("UPDATE ordenes_produccion SET liberada=1, aprobados_final=%s, fecha_liberacion=NOW(), estado='FINALIZADA', "
                "fecha_fin=NOW() WHERE id_orden=%s AND liberada=0", (aprobadas, o["id_orden"]))
    if cur.rowcount != 1:
        raise ValueError("El lote ya fue liberado por otro usuario.")
    if aprobadas > 0:
        _hist(cur, o["id_orden"], "Entrada de producción al almacén", f"{aprobadas} pistones", "Liberado", id_usuario,
              f"Stock {anterior} → {nuevo}")
    return anterior, nuevo


def completar_paso(id_orden, resultado, id_usuario=None):
    """Registra el resultado del paso vigente y lo completa.

    ``resultado``: recibida, procesada, aprobada, rechazada, pendiente, motivo, defectos, observaciones,
    responsable y fecha_hora (datetime). Para los pasos 1 a 3 solo se usan responsable, observaciones y fecha_hora.
    """
    r = resultado or {}
    responsable = _limpiar(r.get("responsable"), 80)
    motivo, defectos, obs = _limpiar(r.get("motivo"), 255), _limpiar(r.get("defectos"), 500), _limpiar(r.get("observaciones"), 255)
    momento = r.get("fecha_hora") or datetime.now()
    with db.transaccion(dictionary=True) as (_c, cur):
        o = _bloquear_orden(cur, id_orden)
        if o["estado"] != "EN_PRODUCCION":
            raise ValueError("La orden ya está finalizada o cancelada.")
        paso = _n(o["paso_actual"])
        exigir_paso(id_usuario, paso, cur)
        cur.execute("SELECT * FROM orden_etapas WHERE id_orden=%s ORDER BY paso", (id_orden,))
        et = cur.fetchall()
        actual = next((e for e in et if e["paso"] == paso), None)
        if not actual or actual["estado"] == "BLOQUEADO":
            raise ValueError("El paso está bloqueado por una incidencia. Desbloquéelo antes de completarlo.")
        if actual["estado"] != "EN_PROCESO":
            raise ValueError("El paso ya no está en proceso. Actualice la pantalla.")
        if paso >= PRIMER_PASO_PIEZAS:
            recibida = piezas_recibidas(et, o["cantidad_plan"], paso)
            if r.get("recibida") is not None and _n(r["recibida"]) != recibida:
                raise ValueError(f"La cantidad recibida cambió ({recibida}). Actualice la pantalla.")
            procesada, aprob, rech, pend = _n(r.get("procesada")), _n(r.get("aprobada")), _n(r.get("rechazada")), _n(r.get("pendiente"))
            validar_resultado(recibida, procesada, aprob, rech, pend, motivo, responsable)
            if aprob == 0 and pend > 0:
                raise ValueError("No hay piezas aprobadas para continuar y quedan pendientes. Evalúe las pendientes antes de completar.")
        else:
            if not responsable:
                raise ValueError("Indique el responsable del paso.")
            recibida = procesada = aprob = rech = pend = 0
            motivo = defectos = ""
        estado = estado_resultado(rech, pend, obs)
        cur.execute("UPDATE orden_etapas SET estado=%s, fecha=%s, aprobados=%s, rechazados=%s, pendientes=%s, motivo=%s, "
                    "defectos=%s, observaciones=%s, cant_recibida=%s, cant_procesada=%s, responsable=%s, fecha_hora=%s "
                    "WHERE id_orden=%s AND paso=%s",
                    (estado, momento.date(), aprob, rech, pend, motivo or None, defectos or None, obs or None,
                     recibida if paso >= PRIMER_PASO_PIEZAS else None, procesada if paso >= PRIMER_PASO_PIEZAS else None,
                     responsable, momento, id_orden, paso))
        if paso >= PRIMER_PASO_PIEZAS:
            _hist(cur, id_orden, PASOS[paso - 1], f"{aprob} aprobadas", ESTADO_TXT[estado], id_usuario,
                  obs or f"Recibidas {recibida} · aprobadas {aprob} · rechazadas {rech} · pendientes {pend}")
            if rech > 0:
                cur.execute("INSERT INTO productos_no_conformes(id_orden,id_piston,paso,cantidad,motivo,defectos,observaciones,"
                            "responsable,origen,fecha_hora,id_usuario) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'ETAPA',%s,%s)",
                            (id_orden, o["id_piston"], paso, rech, motivo, defectos or None, obs or None, responsable, momento, id_usuario))
                _hist(cur, id_orden, "Productos no conformes", f"{rech} pistones", "Rechazado", id_usuario, motivo)
            if pend > 0:
                _hist(cur, id_orden, "Piezas retenidas por evaluar", f"{pend} pistones", "Pendiente", id_usuario,
                      f"Retenidas en el paso {paso}")
        else:
            _hist(cur, id_orden, PASOS[paso - 1], "—", ESTADO_TXT[estado], id_usuario, obs or None)

        res = {"paso": paso, "estado": estado, "aprobadas": aprob, "rechazadas": rech, "pendientes": pend,
               "finalizada": False, "liberadas": 0, "stock_anterior": None, "stock_nuevo": None, "sin_piezas": False}
        if paso == PASO_LIBERACION:
            res["stock_anterior"], res["stock_nuevo"] = _liberar(cur, o, aprob, id_usuario)
            res["finalizada"], res["liberadas"] = True, aprob
        elif paso >= PRIMER_PASO_PIEZAS and aprob == 0:
            motivo_cierre = f"Sin piezas aprobadas para continuar después del paso {paso}"
            cur.execute("UPDATE ordenes_produccion SET estado='FINALIZADA', fecha_fin=NOW(), liberada=1, aprobados_final=0, "
                        "motivo_cierre=%s WHERE id_orden=%s", (motivo_cierre, id_orden))
            _hist(cur, id_orden, "Lote cerrado sin producción aprobada", "0 pistones", "Finalizado", id_usuario, motivo_cierre)
            res["finalizada"] = res["sin_piezas"] = True
        else:
            cur.execute("UPDATE orden_etapas SET estado='EN_PROCESO', inicio=NOW() WHERE id_orden=%s AND paso=%s", (id_orden, paso + 1))
            cur.execute("UPDATE ordenes_produccion SET paso_actual=%s WHERE id_orden=%s", (paso + 1, id_orden))
    return res


def bloquear_paso(id_orden, motivo, id_usuario=None):
    """Marca el paso vigente como Bloqueado por una incidencia que impide continuar."""
    motivo = _limpiar(motivo, 255)
    if not motivo:
        raise ValueError("Describa la incidencia que bloquea el paso.")
    with db.transaccion(dictionary=True) as (_c, cur):
        o = _bloquear_orden(cur, id_orden)
        if o["estado"] != "EN_PRODUCCION":
            raise ValueError("La orden ya está finalizada o cancelada.")
        paso = _n(o["paso_actual"])
        exigir_paso(id_usuario, paso, cur)
        cur.execute("UPDATE orden_etapas SET estado='BLOQUEADO', bloqueo=%s WHERE id_orden=%s AND paso=%s AND estado='EN_PROCESO'",
                    (motivo, id_orden, paso))
        if cur.rowcount != 1:
            raise ValueError("Solo se puede bloquear un paso que esté en proceso.")
        _hist(cur, id_orden, f"Paso {paso} bloqueado", "—", "Bloqueado", id_usuario, motivo)
    return paso


def desbloquear_paso(id_orden, observacion="", id_usuario=None):
    with db.transaccion(dictionary=True) as (_c, cur):
        o = _bloquear_orden(cur, id_orden)
        paso = _n(o["paso_actual"])
        exigir_paso(id_usuario, paso, cur)
        cur.execute("UPDATE orden_etapas SET estado='EN_PROCESO', bloqueo=NULL WHERE id_orden=%s AND paso=%s AND estado='BLOQUEADO'",
                    (id_orden, paso))
        if cur.rowcount != 1:
            raise ValueError("El paso no está bloqueado.")
        _hist(cur, id_orden, f"Paso {paso} desbloqueado", "—", "En proceso", id_usuario, observacion)
    return paso


def resolver_pendientes(id_orden, paso, aprobadas, rechazadas, motivo="", defectos="", observaciones="",
                        responsable="", id_usuario=None):
    """Evalúa piezas retenidas de una etapa.

    Las aprobadas se suman a lo que recibe la etapa siguiente (solo si esa etapa aún no se completó); las rechazadas
    pasan al registro de no conformes. Si la siguiente etapa ya se completó, solo pueden rechazarse.
    """
    aprobadas, rechazadas = _n(aprobadas), _n(rechazadas)
    motivo, defectos, obs, responsable = _limpiar(motivo, 255), _limpiar(defectos, 500), _limpiar(observaciones, 255), _limpiar(responsable, 80)
    if aprobadas < 0 or rechazadas < 0 or aprobadas + rechazadas == 0:
        raise ValueError("Indique cuántas piezas se aprueban o se rechazan.")
    if rechazadas and not motivo:
        raise ValueError("Indique el motivo de los rechazos.")
    if not responsable:
        raise ValueError("Indique el responsable de la inspección.")
    with db.transaccion(dictionary=True) as (_c, cur):
        o = _bloquear_orden(cur, id_orden)
        exigir_paso(id_usuario, paso, cur)
        cur.execute("SELECT * FROM orden_etapas WHERE id_orden=%s ORDER BY paso", (id_orden,))
        et = cur.fetchall()
        e = next((x for x in et if x["paso"] == paso), None)
        if not e:
            raise ValueError("La etapa no existe.")
        vigente = pendiente_vigente(e)
        if aprobadas + rechazadas > vigente:
            raise ValueError(f"Solo hay {vigente} pieza(s) pendientes de evaluación en este paso.")
        if aprobadas:
            sig = next((x for x in et if x["paso"] == paso + 1), None)
            if o["estado"] != "EN_PRODUCCION" or not sig or sig["estado"] in ESTADOS_COMPLETOS:
                raise ValueError("El paso siguiente ya se completó: estas piezas ya no pueden continuar el flujo; solo pueden rechazarse.")
        cur.execute("UPDATE orden_etapas SET pend_aprobados=pend_aprobados+%s, pend_rechazados=pend_rechazados+%s "
                    "WHERE id_orden=%s AND paso=%s", (aprobadas, rechazadas, id_orden, paso))
        if rechazadas:
            cur.execute("INSERT INTO productos_no_conformes(id_orden,id_piston,paso,cantidad,motivo,defectos,observaciones,"
                        "responsable,origen,id_usuario) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'PENDIENTE',%s)",
                        (id_orden, o["id_piston"], paso, rechazadas, motivo, defectos or None, obs or None, responsable, id_usuario))
        _hist(cur, id_orden, f"Evaluación de pendientes · paso {paso}", f"{aprobadas} aprobadas / {rechazadas} rechazadas",
              "Evaluado", id_usuario, obs or motivo or None)
    return {"aprobadas": aprobadas, "rechazadas": rechazadas}


def _registrar_rechazo_definitivo(cur, id_rep, nc, o, cantidad, responsable, obs, id_usuario):
    """Copia permanente de un descarte (rechazo definitivo): lote, modelo, etapa, motivo y quién lo decidió.

    Guarda también el código y el modelo como texto, de modo que el registro sigue completo aunque el catálogo cambie.
    """
    cur.execute("SELECT codigo_piston, descripcion FROM pistones WHERE id_piston=%s", (nc["id_piston"],))
    pis = cur.fetchone() or {}
    usuario = None
    if id_usuario is not None:
        cur.execute("SELECT nombre_usuario FROM usuarios WHERE id_usuario=%s", (id_usuario,))
        usuario = (cur.fetchone() or {}).get("nombre_usuario")
    cur.execute("INSERT INTO rechazos_definitivos(id_rep,id_nc,id_orden,id_piston,codigo_piston,modelo,lote,cantidad,fecha_rechazo,"
                "paso,motivo,defectos,observaciones,responsable,id_usuario,usuario) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s)",
                (id_rep, nc["id_nc"], nc["id_orden"], nc["id_piston"], pis.get("codigo_piston"), pis.get("descripcion"),
                 o["lote"], cantidad, nc["paso"], nc["motivo"], nc.get("defectos"), obs or None, responsable, id_usuario, usuario))


def reprocesar(id_nc, aprobadas, rechazadas, responsable, observaciones="", id_usuario=None):
    """Reproceso controlado de no conformes: nueva inspección, sin duplicar existencias.

    Las piezas recuperadas entran al stock una sola vez (el saldo no conforme baja en la misma transacción, por lo que
    no pueden volver a recuperarse). Requiere que el lote ya esté liberado.
    """
    aprobadas, rechazadas = _n(aprobadas), _n(rechazadas)
    responsable, obs = _limpiar(responsable, 80), _limpiar(observaciones, 255)
    if aprobadas < 0 or rechazadas < 0 or aprobadas + rechazadas == 0:
        raise ValueError("Indique cuántas piezas se recuperan o se descartan.")
    if not responsable:
        raise ValueError("Indique el responsable de la nueva inspección.")
    with db.transaccion(dictionary=True) as (_c, cur):
        cur.execute("SELECT * FROM productos_no_conformes WHERE id_nc=%s FOR UPDATE", (id_nc,))
        nc = cur.fetchone()
        if not nc:
            raise ValueError("El registro de no conformes ya no existe.")
        o = _bloquear_orden(cur, nc["id_orden"])
        exigir_paso(id_usuario, nc["paso"], cur)          # CONTROL: solo los no conformes originados en su etapa
        saldo = saldo_nc(nc)
        if aprobadas + rechazadas > saldo:
            raise ValueError(f"Solo quedan {saldo} pieza(s) por reprocesar en este registro.")
        anterior = nuevo = None
        if aprobadas:
            if not _n(o["liberada"]):
                raise ValueError("El lote aún está en producción. Las piezas recuperadas pueden ingresar al stock cuando el lote sea liberado.")
            if not o["id_piston"]:
                raise ValueError("El lote no tiene un pistón asignado.")
            cur.execute(db.SQL_STOCK_BLOQUEAR, (o["id_piston"],))
            fila = cur.fetchone()
            if not fila:
                raise ValueError("El pistón del lote ya no existe.")
            anterior = int(list(fila.values())[0] or 0)
            nuevo = anterior + aprobadas
            cur.execute(db.SQL_STOCK_FIJAR, (o["id_piston"], nuevo))
            cur.execute("INSERT INTO movimientos_inventario(id_piston,tipo,cantidad,motivo,id_usuario,stock_anterior,stock_nuevo,"
                        "id_orden,lote) VALUES(%s,'PRODUCCION',%s,%s,%s,%s,%s,%s,%s)",
                        (o["id_piston"], aprobadas, f"Recuperación por reproceso · lote {o['lote']} · no conforme #{id_nc}",
                         id_usuario, anterior, nuevo, o["id_orden"], o["lote"]))
        cur.execute("UPDATE productos_no_conformes SET recuperadas=recuperadas+%s, descartadas=descartadas+%s WHERE id_nc=%s",
                    (aprobadas, rechazadas, id_nc))
        cur.execute("INSERT INTO nc_reprocesos(id_nc,aprobadas,rechazadas,responsable,observaciones,id_usuario) "
                    "VALUES(%s,%s,%s,%s,%s,%s)", (id_nc, aprobadas, rechazadas, responsable, obs or None, id_usuario))
        if rechazadas:
            _registrar_rechazo_definitivo(cur, cur.lastrowid, nc, o, rechazadas, responsable, obs, id_usuario)
        _hist(cur, o["id_orden"], f"Reproceso de no conformes #{id_nc}", f"{aprobadas} recuperadas / {rechazadas} descartadas",
              "Reproceso", id_usuario, obs or None)
    return {"recuperadas": aprobadas, "descartadas": rechazadas, "stock_anterior": anterior, "stock_nuevo": nuevo}
