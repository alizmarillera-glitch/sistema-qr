"""Prueba de la lógica de lotes con una base SQLite en memoria que imita a MySQL.

No necesita XAMPP: sirve para comprobar las reglas (lotes independientes, rechazados, pendientes, liberación única,
reproceso) antes de probar con MySQL real. Ejecutar:  py pruebas/probar_lotes.py
"""
import os
import re
import sqlite3
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timedelta

# ---------------------------------------------------------------- «conexion» falsa sobre SQLite
SQL = sqlite3.connect(":memory:", check_same_thread=False)
SQL.row_factory = sqlite3.Row
SQL.executescript("""
CREATE TABLE pistones(id_piston INTEGER PRIMARY KEY AUTOINCREMENT, codigo_piston TEXT, descripcion TEXT, activo INT DEFAULT 1);
CREATE TABLE existencias(id_piston INTEGER PRIMARY KEY, stock INT NOT NULL DEFAULT 0);
CREATE TABLE roles(id_rol INTEGER PRIMARY KEY, nombre_rol TEXT UNIQUE);
CREATE TABLE usuarios(id_usuario INTEGER PRIMARY KEY, nombre_usuario TEXT, id_rol INT, estado INT DEFAULT 1, etapa_asignada INT);
CREATE TABLE facturas(id_factura INTEGER PRIMARY KEY, nro_factura TEXT);
CREATE TABLE movimientos_inventario(id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT, id_piston INT, tipo TEXT, cantidad INT,
  motivo TEXT, fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP, id_usuario INT, id_factura INT, stock_anterior INT, stock_nuevo INT,
  id_orden INT, lote TEXT);
CREATE TABLE materia_prima_mov(id_mov INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, kg REAL, descripcion TEXT, id_orden INT,
  fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP, id_usuario INT);
CREATE TABLE ordenes_produccion(id_orden INTEGER PRIMARY KEY AUTOINCREMENT, codigo_orden TEXT UNIQUE, lote TEXT UNIQUE,
  id_piston INT, cantidad_plan INT, kg_aluminio REAL DEFAULT 0, estado TEXT DEFAULT 'EN_PRODUCCION', paso_actual INT DEFAULT 1,
  creada TEXT DEFAULT CURRENT_TIMESTAMP, id_usuario INT, responsable TEXT, observaciones TEXT, fecha_inicio TEXT, fecha_fin TEXT,
  aprobados_final INT DEFAULT 0, liberada INT DEFAULT 0, fecha_liberacion TEXT, motivo_cierre TEXT);
CREATE TABLE orden_etapas(id_etapa INTEGER PRIMARY KEY AUTOINCREMENT, id_orden INT, paso INT, estado TEXT DEFAULT 'PENDIENTE',
  fecha TEXT, aprobados INT DEFAULT 0, rechazados INT DEFAULT 0, motivo TEXT, observaciones TEXT, cant_recibida INT,
  cant_procesada INT, pendientes INT DEFAULT 0, pend_aprobados INT DEFAULT 0, pend_rechazados INT DEFAULT 0, defectos TEXT,
  responsable TEXT, fecha_hora TEXT, inicio TEXT, bloqueo TEXT, UNIQUE(id_orden, paso));
CREATE TABLE orden_historial(id_hist INTEGER PRIMARY KEY AUTOINCREMENT, id_orden INT, fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP,
  movimiento TEXT, cantidad TEXT, estado TEXT, id_usuario INT, observaciones TEXT);
CREATE TABLE productos_no_conformes(id_nc INTEGER PRIMARY KEY AUTOINCREMENT, id_orden INT, id_piston INT, paso INT, cantidad INT,
  recuperadas INT DEFAULT 0, descartadas INT DEFAULT 0, motivo TEXT, defectos TEXT, observaciones TEXT, responsable TEXT,
  origen TEXT DEFAULT 'ETAPA', fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP, id_usuario INT);
CREATE TABLE nc_reprocesos(id_rep INTEGER PRIMARY KEY AUTOINCREMENT, id_nc INT, fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP,
  aprobadas INT, rechazadas INT, responsable TEXT, observaciones TEXT, id_usuario INT);
CREATE TABLE rechazos_definitivos(id_rechazo INTEGER PRIMARY KEY AUTOINCREMENT, id_rep INT UNIQUE, id_nc INT, id_orden INT,
  id_piston INT, codigo_piston TEXT, modelo TEXT, lote TEXT, cantidad INT, fecha_rechazo TEXT, paso INT, motivo TEXT,
  defectos TEXT, observaciones TEXT, responsable TEXT, id_usuario INT, usuario TEXT);
INSERT INTO roles VALUES(1,'Administrador'),(3,'Cajero'),(4,'CONTROL');
INSERT INTO usuarios VALUES(1,'admin',1,1,NULL),(2,'control5',4,1,5),(3,'control2',4,1,2),(4,'control4',4,1,4),
  (5,'control_sin_etapa',4,1,NULL),(6,'cajero',3,1,NULL),(7,'control9_baja',4,0,9);
""")


def _t(sql):
    sql = re.sub(r"\s+FOR UPDATE", "", sql)
    sql = sql.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("%s", "?")
    return sql


class _Cur:
    def __init__(self, c, dic):
        self.c, self.dic = c.cursor(), dic

    def execute(self, sql, params=()):
        self.c.execute(_t(sql), tuple(params))

    def _f(self, r):
        return None if r is None else (dict(r) if self.dic else tuple(r))

    def fetchone(self):
        return self._f(self.c.fetchone())

    def fetchall(self):
        return [self._f(r) for r in self.c.fetchall()]

    lastrowid = property(lambda s: s.c.lastrowid)
    rowcount = property(lambda s: s.c.rowcount)


fake = types.ModuleType("conexion")
fake.SQL_STOCK_BLOQUEAR = ("SELECT COALESCE(e.stock,0), p.activo FROM pistones p LEFT JOIN existencias e "
                           "ON e.id_piston=p.id_piston WHERE p.id_piston=%s FOR UPDATE")
fake.SQL_STOCK_FIJAR = ("INSERT INTO existencias(id_piston,stock) VALUES(%s,%s) "
                        "ON CONFLICT(id_piston) DO UPDATE SET stock=excluded.stock")


@contextmanager
def transaccion(dictionary=False):
    cur = _Cur(SQL, dictionary)
    try:
        yield SQL, cur
        SQL.commit()
    except Exception:
        SQL.rollback()
        raise


def consulta(sql, params=(), uno=False, commit=False):
    cur = _Cur(SQL, True)
    cur.execute(sql, params)
    if commit:
        SQL.commit()
        return cur.lastrowid
    return cur.fetchone() if uno else cur.fetchall()


fake.transaccion, fake.consulta = transaccion, consulta
sys.modules["conexion"] = fake
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sistema"))
import produccion_repo as P  # noqa: E402

fallos = []


def verifica(cond, texto):
    print(("  ok  " if cond else "  FALLA  ") + texto)
    if not cond:
        fallos.append(texto)


def debe_fallar(fn, texto):
    try:
        fn()
    except ValueError as ex:
        verifica(True, f"{texto}: «{ex}»")
    else:
        verifica(False, f"{texto} (no lanzó error)")


def stock(pid):
    r = SQL.execute("SELECT stock FROM existencias WHERE id_piston=?", (pid,)).fetchone()
    return r[0] if r else 0


def res(**kw):
    base = dict(responsable="Inspector", observaciones="", motivo="", defectos="")
    base.update(kw)
    return base


def pasar_hasta(oid, paso_destino, rechazos=None):
    """Completa pasos hasta que el vigente sea ``paso_destino``. rechazos: {paso: (rech, pend)}."""
    rechazos = rechazos or {}
    while P.orden(oid)["paso_actual"] < paso_destino:
        o = P.orden(oid)
        paso = o["paso_actual"]
        if paso < 4:
            P.completar_paso(oid, res(), 1)
            continue
        rec = P.piezas_recibidas(P.etapas(oid), o["cantidad_plan"], paso)
        rech, pend = rechazos.get(paso, (0, 0))
        P.completar_paso(oid, res(recibida=rec, procesada=rec, aprobada=rec - rech - pend, rechazada=rech, pendiente=pend,
                                  motivo="Porosidad" if rech else ""), 1)


print("\n1) Materia prima y creación de lotes independientes")
for cod, desc in (("EPV-A", "Pistón modelo A"), ("EPV-B", "Pistón modelo B")):
    SQL.execute("INSERT INTO pistones(codigo_piston,descripcion) VALUES(?,?)", (cod, desc))
SQL.execute("INSERT INTO existencias VALUES(1,67)")
P.entrada_materia_prima(1000, "Aluminio grado A", 1)
verifica(P.proximo_lote() == "AL-001", "el primer lote sugerido es AL-001")
o1 = P.nueva_orden("AL-001", 1, 100, 300, "2026-11-21", "Carlos", "Primer lote", 1)
o2 = P.nueva_orden("AL-002", 2, 50, 200, "2026-11-21", "María", "", 1)
verifica(P.proximo_lote() == "AL-003", "la sugerencia avanza a AL-003")
e1, e2 = P.etapas(o1[0]), P.etapas(o2[0])
verifica(len(e1) == 9 and len(e2) == 9, "cada lote tiene sus propias 9 etapas")
verifica([e["estado"] for e in e1] == ["EN_PROCESO"] + ["PENDIENTE"] * 8, "paso 1 en proceso y 8 pendientes")
verifica({e["id_etapa"] for e in e1}.isdisjoint({e["id_etapa"] for e in e2}), "los seguimientos no comparten filas")
verifica(abs(P.saldo_materia_prima() - 500) < 1e-9, "la materia prima baja 300 + 200 kg")
verifica(P.resumen()["activas"] == 2, "KPI: 2 órdenes activas")
debe_fallar(lambda: P.nueva_orden("AL-001", 1, 10, 5, "2026-11-21", "X", "", 1), "lote duplicado")
debe_fallar(lambda: P.nueva_orden("AL-009", 1, 10, 9999, "2026-11-21", "X", "", 1), "materia prima insuficiente")
debe_fallar(lambda: P.nueva_orden("AL-009", None, 10, 5, "2026-11-21", "X", "", 1), "pistón obligatorio")
debe_fallar(lambda: P.nueva_orden("AL-009", 1, 10, 5, "2026-11-21", "", "", 1), "responsable obligatorio")

print("\n2) Pasos 1-3, validación del resultado y avance solo con aprobadas")
pasar_hasta(o1[0], 4)
verifica(P.orden(o1[0])["paso_actual"] == 4 and P.orden(o2[0])["paso_actual"] == 1, "avanzar AL-001 no mueve a AL-002")
debe_fallar(lambda: P.completar_paso(o1[0], res(recibida=100, procesada=100, aprobada=90, rechazada=5, pendiente=0, motivo="x"), 1),
            "la suma no coincide")
debe_fallar(lambda: P.completar_paso(o1[0], res(recibida=100, procesada=100, aprobada=95, rechazada=5), 1), "rechazo sin motivo")
debe_fallar(lambda: P.completar_paso(o1[0], res(recibida=100, procesada=100, aprobada=95, rechazada=5, motivo="m", responsable=""), 1),
            "sin responsable")
r = P.completar_paso(o1[0], res(recibida=100, procesada=100, aprobada=95, rechazada=5, motivo="Porosidad", defectos="Poros en falda"), 1)
et = P.etapas(o1[0])
verifica(et[3]["estado"] == "COMPLETADO_OBS" and et[4]["estado"] == "EN_PROCESO", "paso 4 con observaciones; paso 5 en proceso")
verifica(et[5]["estado"] == "PENDIENTE", "el paso 6 sigue pendiente")
nc = P.no_conformes(o1[0])
verifica(len(nc) == 1 and nc[0]["cantidad"] == 5 and nc[0]["paso"] == 4 and nc[0]["motivo"] == "Porosidad", "5 rechazados registrados como no conformes")
verifica(stock(1) == 67, "los rechazados no tocan el stock")
verifica(P.piezas_recibidas(P.etapas(o1[0]), 100, 5) == 95, "el paso 5 recibe solo las 95 aprobadas")

print("\n3) Bloqueo de pasos")
debe_fallar(lambda: P.bloquear_paso(o1[0], "", 1), "bloqueo sin incidencia")
P.bloquear_paso(o1[0], "Horno fuera de servicio", 1)
verifica(P.etapas(o1[0])[4]["estado"] == "BLOQUEADO", "el paso 5 queda Bloqueado")
debe_fallar(lambda: P.completar_paso(o1[0], res(recibida=95, procesada=95, aprobada=95), 1), "no se completa un paso bloqueado")
P.desbloquear_paso(o1[0], "Reparado", 1)
verifica(P.etapas(o1[0])[4]["estado"] == "EN_PROCESO", "al desbloquear vuelve a En proceso")

print("\n4) Pendientes retenidos")
r = P.completar_paso(o1[0], res(recibida=95, procesada=95, aprobada=90, rechazada=0, pendiente=5), 1)
verifica(P.etapas(o1[0])[5]["estado"] == "EN_PROCESO" and P.piezas_recibidas(P.etapas(o1[0]), 100, 6) == 90,
         "5 pendientes quedan retenidas; avanzan 90")
verifica(P.resumen()["pendientes"] == 5, "KPI pendientes = 5")
debe_fallar(lambda: P.resolver_pendientes(o1[0], 5, 6, 0, "", "", "", "Ana", 1), "más piezas de las retenidas")
P.resolver_pendientes(o1[0], 5, 3, 2, "Dimensión fuera de tolerancia", "", "", "Ana", 1)
verifica(P.piezas_recibidas(P.etapas(o1[0]), 100, 6) == 93, "3 aprobadas se suman a lo que recibe el paso 6")
verifica(P.resumen()["pendientes"] == 0 and P.resumen()["rechazados"] == 7, "KPI: 0 pendientes y 7 rechazados")
debe_fallar(lambda: P.resolver_pendientes(o1[0], 5, 1, 0, "", "", "", "Ana", 1), "ya no quedan pendientes")

print("\n5) Hasta la liberación: ejemplo 67 + 92 = 159")
pasar_hasta(o1[0], 7)                                              # pasos 6 (93 aprobadas)
r = P.completar_paso(o1[0], res(recibida=93, procesada=93, aprobada=92, rechazada=1, motivo="Rayadura"), 1)   # inspección final
r = P.completar_paso(o1[0], res(recibida=92, procesada=92, aprobada=92), 1)                              # almacén
verifica(P.orden(o1[0])["paso_actual"] == 9 and stock(1) == 67, "tras el almacén (paso 8) el stock aún no cambia")
r = P.completar_paso(o1[0], res(recibida=92, procesada=92, aprobada=92), 1)                              # liberación
verifica(stock(1) == 159 and r["stock_anterior"] == 67 and r["stock_nuevo"] == 159, "stock 67 + 92 = 159")
mv = P.movimientos_stock_lote(o1[0])
verifica(len(mv) == 1 and mv[0]["tipo"] == "PRODUCCION" and mv[0]["cantidad"] == 92 and mv[0]["lote"] == "AL-001", "un movimiento PRODUCCION vinculado al lote")
o = P.orden(o1[0])
verifica(o["estado"] == "FINALIZADA" and o["liberada"] == 1 and o["aprobados_final"] == 92, "orden finalizada y liberada con 92")
debe_fallar(lambda: P.completar_paso(o1[0], res(recibida=92, procesada=92, aprobada=92), 1), "no se puede completar otra vez")
debe_fallar(lambda: P._liberar(_Cur(SQL, True), P.orden(o1[0]), 92, 1), "la liberación directa repetida se bloquea")
verifica(stock(1) == 159, "el stock sigue en 159 tras reintentar")
verifica(P.trazabilidad(o1[0])["resumen"]["aprobadas"] == 92, "consultar el lote no vuelve a sumar")
verifica(P.resumen()["aprobados"] == 159 and P.resumen()["activas"] == 1, "KPI: 159 aprobados, 1 orden activa")
verifica(len(P.ordenes_finalizadas()) == 1 and len(P.ordenes_activas()) == 1, "listas de finalizadas y activas")

print("\n6) Reproceso controlado")
ncs = P.no_conformes(o1[0], solo_con_saldo=True)
verifica(sum(P.saldo_nc(n) for n in ncs) == 8, "8 no conformes con saldo (5 + 2 + 1)")
grande = max(ncs, key=lambda n: n["cantidad"])
debe_fallar(lambda: P.reprocesar(grande["id_nc"], 6, 0, "Luis", "", 1), "recuperar más del saldo")
debe_fallar(lambda: P.reprocesar(grande["id_nc"], 1, 0, "", "", 1), "sin responsable")
rp = P.reprocesar(grande["id_nc"], 3, 2, "Luis", "Retrabajo en torno", 1)
verifica(stock(1) == 162 and rp["stock_nuevo"] == 162, "3 recuperadas suben el stock a 162")
debe_fallar(lambda: P.reprocesar(grande["id_nc"], 1, 0, "Luis", "", 1), "el saldo de ese registro ya es 0")
verifica(stock(1) == 162, "no se duplicó el stock")
verifica(P.estado_nc(P.no_conformes(o1[0])[-1]) in ("Cerrado", "Recuperado", "Descartado", "Reproceso parcial", "No conforme"), "estado del no conforme calculable")

print("\n7) Lote sin piezas aprobadas se cierra; lotes distintos no se mezclan")
pasar_hasta(o2[0], 4)
r = P.completar_paso(o2[0], res(recibida=50, procesada=50, aprobada=0, rechazada=50, motivo="Molde dañado"), 1)
verifica(r["sin_piezas"] and P.orden(o2[0])["estado"] == "FINALIZADA", "con 0 aprobadas el lote se cierra")
verifica(P.etapas(o2[0])[4]["estado"] == "PENDIENTE" and stock(2) == 0, "el paso siguiente no arranca y no entra stock")
o3 = P.nueva_orden("AL-003", 1, 40, 100, "2026-11-22", "Pedro", "", 1)
verifica(all(e["aprobados"] == 0 and e["estado"] in ("EN_PROCESO", "PENDIENTE") for e in P.etapas(o3[0])), "el lote nuevo nace vacío")
verifica(P.orden(o1[0])["aprobados_final"] == 92, "el histórico de AL-001 no cambió")
verifica(len(P.historial(o1[0])) > 8 and len(P.movimientos_materia_prima(o1[0])) == 1, "historial y movimientos de materia prima del lote")

print("\n8) No conformes: piezas en revisión, recuperación y conteos (sin perder el historial)")
base_pend, base_rech, stock_ini = P.resumen()["pendientes"], P.resumen()["rechazados"], stock(1)
o4 = P.nueva_orden("AL-004", 1, 60, 100, "2026-11-23", "Rosa", "", 1)
pasar_hasta(o4[0], 4)
P.completar_paso(o4[0], res(recibida=60, procesada=60, aprobada=50, rechazada=4, pendiente=6, motivo="Porosidad", defectos="Poros en falda"), 1)
rev = [f for f in P.en_revision() if f["lote"] == "AL-004"]
verifica(len(rev) == 1 and P.pendiente_vigente(rev[0]) == 6 and rev[0]["paso"] == 4, "la pestaña «en revisión» lista las 6 piezas retenidas (de todos los lotes)")
verifica(P.estado_revision(rev[0]) == "En revisión" and P.puede_aprobar_revision(rev[0]), "estado «En revisión» y pueden aprobarse")
verifica(P.resumen()["pendientes"] == base_pend + 6, "KPI: +6 por evaluar")
P.resolver_pendientes(o4[0], 4, 2, 1, "Medida fuera de tolerancia", "Ovalizado", "", "Ana", 1)
rev = [f for f in P.en_revision() if f["lote"] == "AL-004"]
verifica(len(rev) == 1 and P.pendiente_vigente(rev[0]) == 3 and P.estado_revision(rev[0]) == "Revisión parcial", "evaluar 3 deja 3 en revisión parcial")
P.resolver_pendientes(o4[0], 4, 0, 3, "Medida fuera de tolerancia", "", "", "Ana", 1)
verifica(not [f for f in P.en_revision() if f["lote"] == "AL-004"], "evaluadas todas, ya no aparecen como en revisión")
hist = [f for f in P.en_revision(o4[0], solo_vigentes=False)]
verifica(len(hist) == 1 and P.estado_revision(hist[0]) == "Evaluado" and hist[0]["pend_aprobados"] == 2 and hist[0]["pend_rechazados"] == 4,
         "el historial de revisiones se conserva (2 aprobadas, 4 rechazadas)")
verifica(P.resumen()["pendientes"] == base_pend, "KPI: vuelve a 0 por evaluar")
verifica(P.resumen_lote(P.orden(o4[0]), P.etapas(o4[0]))["rechazadas"] == 8, "lote: 4 + 4 rechazadas, aún sin recuperar")
verifica(P.resumen()["rechazados"] == base_rech + 8, "KPI: +8 rechazados")
pasar_hasta(o4[0], 9)
rec9 = P.piezas_recibidas(P.etapas(o4[0]), 60, 9)
verifica(rec9 == 52, "al paso 9 llegan las 50 + 2 aprobadas desde revisión")
P.completar_paso(o4[0], res(recibida=rec9, procesada=rec9, aprobada=rec9), 1)
verifica(stock(1) == stock_ini + 52, "el lote liberado suma 52 al stock (las rechazadas no entran)")
ncs = P.no_conformes(o4[0], solo_con_saldo=True)
verifica(sum(P.saldo_nc(n) for n in ncs) == 8, "pestaña «rechazados»: 8 piezas con saldo")
etapa4 = next(n for n in ncs if n["origen"] == "ETAPA")
original = (etapa4["motivo"], etapa4["defectos"], etapa4["cantidad"], etapa4["paso"], etapa4["fecha_hora"])
P.reprocesar(etapa4["id_nc"], 3, 1, "Luis", "Retrabajo", 1)
verifica(stock(1) == stock_ini + 55, "recuperar 3 suma 3 al stock")
verifica(P.recuperadas_lote(o4[0]) == 3, "3 piezas recuperadas del lote")
verifica(P.resumen_lote(P.orden(o4[0]), P.etapas(o4[0]), P.recuperadas_lote(o4[0]))["rechazadas"] == 5, "lote: las recuperadas ya no cuentan como rechazadas (8 → 5)")
verifica(P.trazabilidad(o4[0])["resumen"]["rechazadas"] == 5, "la trazabilidad usa el mismo conteo neto")
verifica(P.resumen()["rechazados"] == base_rech + 5, "KPI general: 8 → 5 rechazados")
verifica(all(n["id_nc"] != etapa4["id_nc"] for n in P.no_conformes(o4[0], solo_con_saldo=True)), "el registro cerrado sale de la lista activa")
todo = {n["id_nc"]: n for n in P.no_conformes(o4[0])}
cerrado = todo[etapa4["id_nc"]]
verifica((cerrado["motivo"], cerrado["defectos"], cerrado["cantidad"], cerrado["paso"], cerrado["fecha_hora"]) == original,
         "el historial original (motivo, defectos, cantidad, etapa, fecha) no cambió")
verifica(cerrado["recuperadas"] == 3 and cerrado["descartadas"] == 1 and len(P.reprocesos(etapa4["id_nc"])) == 1, "la recuperación queda registrada")
verifica(any("Reproceso de no conformes" in h["movimiento"] for h in P.historial(o4[0])), "el historial del lote registra el reproceso")
fila_hist = P.en_revision(o4[0], solo_vigentes=False)[0]
verifica(not P.puede_aprobar_revision(fila_hist), "en un lote cerrado lo evaluado ya no puede aprobarse de nuevo")
debe_fallar(lambda: P.resolver_pendientes(o4[0], 4, 1, 0, "", "", "", "Ana", 1), "nada más por evaluar en ese paso")
debe_fallar(lambda: P.reprocesar(etapa4["id_nc"], 1, 0, "Luis", "", 1), "no se puede recuperar dos veces la misma pieza")
verifica(stock(1) == stock_ini + 55, "el stock no se duplicó")

print("\n9) Historial permanente de rechazos definitivos")
rd = P.rechazos_definitivos()
verifica(len(rd) == 2 and sum(f["cantidad"] for f in rd) == 3, "solo los descartes por reproceso son rechazos definitivos (2 registros, 3 piezas)")
verifica(all(f["cantidad"] > 0 for f in rd), "no se registran reprocesos que solo recuperaron piezas")
f_al4 = next(f for f in rd if f["lote"] == "AL-004")
verifica((f_al4["codigo_piston"], f_al4["modelo"], f_al4["cantidad"], f_al4["paso"], f_al4["motivo"], f_al4["responsable"], f_al4["usuario"])
         == ("EPV-A", "Pistón modelo A", 1, 4, "Porosidad", "Luis", "admin"),
         "cada registro guarda código, modelo, lote, cantidad, etapa, motivo y responsable de la decisión")
verifica(f_al4["fecha_rechazo"], "cada registro guarda la fecha del rechazo")
verifica(P.nombre_control(4) == "Control 4 · Moldeado del pistón" and P.PASOS[f_al4["paso"] - 1] == "Moldeado del pistón", "etapa legible del defecto")
verifica([f["lote"] for f in P.rechazos_definitivos(lote="AL-001")] == ["AL-001"], "filtro por lote")
verifica(len(P.rechazos_definitivos(id_piston=1)) == 2 and not P.rechazos_definitivos(id_piston=2), "filtro por modelo")
verifica(len(P.rechazos_definitivos(paso=4)) == 2 and not P.rechazos_definitivos(paso=7), "filtro por etapa")
ref = P._como_fecha_hora(f_al4["fecha_rechazo"])
dia = ref.date()
verifica(len(P.rechazos_definitivos(desde=dia, hasta=dia)) == 2, "filtro por fecha (desde y hasta el mismo día, inclusive)")
verifica(not P.rechazos_definitivos(desde=dia + timedelta(days=1)), "desde mañana no hay registros")
verifica(not P.rechazos_definitivos(hasta=dia - timedelta(days=1)), "hasta ayer no hay registros")
verifica(len(P.rechazos_definitivos(anio=ref.year)) == 2 and not P.rechazos_definitivos(anio=ref.year - 1), "filtro por año")
verifica(len(P.rechazos_definitivos(anio=ref.year, mes=ref.month)) == 2, "filtro por mes y año")
verifica(len(P.rechazos_definitivos(mes=ref.month)) == 2, "filtro por mes de cualquier año")
otro_mes = ref.month % 12 + 1
verifica(not P.rechazos_definitivos(mes=otro_mes) and not P.rechazos_definitivos(anio=ref.year, mes=otro_mes), "otro mes: sin registros")
verifica(len(P.rechazos_definitivos(lote="AL-001", paso=4, anio=ref.year, mes=ref.month, id_piston=1, desde=dia, hasta=dia)) == 1,
         "los filtros se combinan")
op = P.opciones_rechazos()
verifica(op["lotes"] == ["AL-001", "AL-004"] and op["anios"] == [ref.year] and [m["codigo_piston"] for m in op["modelos"]] == ["EPV-A"],
         "opciones de filtro: lotes, modelos y años con rechazos")
verifica(P.resumen_rechazos(rd) == {"piezas": 3, "registros": 2, "lotes": 2}, "totales del historial")

print("\n   Contador mensual: cambia de periodo y empieza en cero, pero el historial no se borra")
verifica(P.rechazados_del_mes(ref.year, ref.month) == 3, "contador del mes de los rechazos = 3")
mes_sig_anio = ref.year + (1 if ref.month == 12 else 0)
verifica(P.rechazados_del_mes(mes_sig_anio, ref.month % 12 + 1) == 0, "al cambiar de mes el contador comienza en cero")
verifica(len(P.rechazos_definitivos()) == 2 and P.rechazados_del_mes(ref.year, ref.month) == 3, "...y los registros anteriores siguen ahí")

print("\n   Permanencia: el registro no depende del catálogo ni de las demás tablas")
SQL.execute("UPDATE pistones SET descripcion='Modelo renombrado' WHERE id_piston=1")
SQL.execute("DELETE FROM pistones WHERE id_piston=2")
SQL.execute("UPDATE productos_no_conformes SET motivo='Alterado'")
f2 = next(f for f in P.rechazos_definitivos() if f["lote"] == "AL-004")
verifica(f2["modelo"] == "Pistón modelo A" and f2["motivo"] == "Porosidad", "renombrar/borrar pistones o alterar no conformes no cambia el historial")

print("\n10) Rol CONTROL: solo modifica su etapa")
verifica(P.puede_modificar_paso("Administrador", None, 7) and P.puede_modificar_paso("Administrador", None, 3), "Administrador: todas las etapas")
verifica(not P.puede_modificar_paso("Inventario", None, 3) and P.ROLES_GESTION == ("Administrador",), "el rol Inventario ya no otorga ningún permiso")
verifica(P.puede_modificar_paso("CONTROL", 5, 5) and not P.puede_modificar_paso("CONTROL", 5, 4) and not P.puede_modificar_paso("CONTROL", 5, 6),
         "CONTROL 5: solo el paso 5")
verifica(not P.puede_modificar_paso("CONTROL", None, 5) and not P.puede_modificar_paso("Cajero", None, 5), "CONTROL sin etapa y Cajero: ninguna")
SQL.execute("INSERT INTO pistones(id_piston,codigo_piston,descripcion) VALUES(2,'EPV-B','Pistón modelo B')")   # se había borrado arriba
P.entrada_materia_prima(500, "Aluminio", 1)
debe_fallar(lambda: P.entrada_materia_prima(10, "x", 2), "CONTROL no registra materia prima")
debe_fallar(lambda: P.nueva_orden("AL-050", 1, 10, 5, "2026-11-22", "Z", "", 2), "CONTROL no crea órdenes")
debe_fallar(lambda: P.nueva_orden("AL-050", 1, 10, 5, "2026-11-22", "Z", "", 6), "Cajero no crea órdenes")
oc = P.nueva_orden("AL-010", 1, 50, 50, "2026-11-22", "Admin", "", 1)[0]
verifica(P.orden(oc)["paso_actual"] == 1, "lote nuevo en el paso 1")
for uid, quien in ((2, "Control 5"), (3, "Control 2"), (4, "Control 4"), (5, "CONTROL sin etapa"), (6, "Cajero"), (7, "usuario desactivado")):
    debe_fallar(lambda u=uid: P.completar_paso(oc, res(), u), f"{quien} no puede completar el paso 1")
debe_fallar(lambda: P.bloquear_paso(oc, "Incidencia", 2), "Control 5 no bloquea el paso 1")
verifica(P.orden(oc)["paso_actual"] == 1 and P.etapas(oc)[0]["estado"] == "EN_PROCESO", "nada cambió tras los intentos rechazados")
P.completar_paso(oc, res(), 1)                                        # el administrador sí puede (paso 1)
verifica(P.orden(oc)["paso_actual"] == 2, "el administrador completa el paso 1")
debe_fallar(lambda: P.completar_paso(oc, res(), 2), "Control 5 no se adelanta con el lote en el paso 2")
debe_fallar(lambda: P.bloquear_paso(oc, "x", 2), "Control 5 no bloquea el paso 2")
P.completar_paso(oc, res(responsable="Control 2"), 3)                 # Control 2 completa SU etapa
verifica(P.orden(oc)["paso_actual"] == 3, "Control 2 completa el paso 2 cuando el lote está en su etapa")
debe_fallar(lambda: P.completar_paso(oc, res(), 3), "Control 2 no completa el paso 3 (etapa posterior)")
pasar_hasta(oc, 5)                                                    # pasos 3 y 4 por administrador
verifica(P.orden(oc)["paso_actual"] == 5 and P.etapas(oc)[4]["estado"] == "EN_PROCESO", "el lote llega al paso 5")
debe_fallar(lambda: P.completar_paso(oc, res(recibida=50, procesada=50, aprobada=50), 4), "Control 4 no completa el paso 5")
P.bloquear_paso(oc, "Horno detenido", 2)
verifica(P.etapas(oc)[4]["estado"] == "BLOQUEADO", "Control 5 bloquea su etapa")
debe_fallar(lambda: P.desbloquear_paso(oc, "ok", 4), "Control 4 no desbloquea el paso 5")
P.desbloquear_paso(oc, "Reparado", 2)
verifica(P.etapas(oc)[4]["estado"] == "EN_PROCESO", "Control 5 desbloquea su etapa")
r = P.completar_paso(oc, res(recibida=50, procesada=50, aprobada=43, rechazada=2, pendiente=5, motivo="Grieta", responsable="Control 5"), 2)
verifica(r["paso"] == 5 and P.orden(oc)["paso_actual"] == 6, "Control 5 registra aprobadas, rechazadas y pendientes y completa el paso 5")
verifica(P.etapas(oc)[4]["responsable"] == "Control 5", "el resultado queda a nombre del responsable")
debe_fallar(lambda: P.resolver_pendientes(oc, 5, 5, 0, "", "", "", "Control 4", 4), "Control 4 no evalúa pendientes del paso 5")
P.resolver_pendientes(oc, 5, 4, 1, "Dimensión", "", "", "Control 5", 2)
verifica(P.pendiente_vigente(P.etapas(oc)[4]) == 0, "Control 5 evalúa los pendientes de su etapa")
# no conformes: cada CONTROL solo los de su etapa
nc5 = [n for n in P.no_conformes(oc, solo_con_saldo=True) if n["paso"] == 5]
verifica(len(nc5) == 2, "dos registros no conformes originados en el paso 5")
debe_fallar(lambda: P.reprocesar(nc5[0]["id_nc"], 0, 1, "Control 4", "", 4), "Control 4 no decide sobre rechazos del paso 5")
debe_fallar(lambda: P.reprocesar(nc5[0]["id_nc"], 0, 1, "Cajero", "", 6), "Cajero no decide sobre rechazos")
antes = len(P.rechazos_definitivos())
P.reprocesar(nc5[0]["id_nc"], 0, 1, "Control 5", "Sin remedio", 2)
verifica(len(P.rechazos_definitivos()) == antes + 1, "Control 5 descarta una pieza de su etapa y queda en el historial")
nuevo = P.rechazos_definitivos(lote="AL-010")[0]
verifica((nuevo["paso"], nuevo["responsable"], nuevo["usuario"], nuevo["cantidad"]) == (5, "Control 5", "control5", 1),
         "el historial registra etapa, responsable y usuario que tomó la decisión")
# consulta libre
verifica(len(P.etapas(oc)) == 9 and P.trazabilidad(oc)["orden"]["lote"] == "AL-010", "todos pueden consultar las 9 etapas y la trazabilidad")
# la API de consulta no pide usuario: no hay barreras de lectura
verifica(P.rechazos_definitivos() and P.resumen()["activas"] >= 1, "consultas abiertas a todos los roles")

print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLO(S): {fallos}"))
sys.exit(1 if fallos else 0)
