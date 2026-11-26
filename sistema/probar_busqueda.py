# -*- coding: utf-8 -*-
"""Pruebas de la lógica de búsqueda del inventario (no necesita base de datos ni interfaz).

Ejecutar desde Sistema_QR_V3/sistema:   py probar_busqueda.py
"""
import copy
import busqueda as b

# (id, código, descripción). Los códigos son los de las etiquetas del proyecto; las descripciones, de ejemplo.
DATOS = [
    (1, "EPV-4029R-STD-2", "Hyundai Accent 1.6 motor G4EC"),
    (2, "21-22", "Toyota Hilux 2.7 motor 2TR"),
    (3, "21-12GRU", "Chevrolet Aveo 1.6 motor F16D3"),
    (4, "EPV-1725R-060-9", "Ford Fiesta 1.6 Zetec"),
    (5, "18-05", "Toyota Corolla 1.8 motor 1ZZ"),
    (6, "12-87uy", "Chevrolet Optra 1.8"),
    (7, "1009", "Ford F-150 5.4 V8"),
    (8, "41-56AYUDA", "Hyundai Elantra 2.0 motor G4GC"),
    (9, "32-76", "Chevrolet Spark 1.0"),
    (10, "12-54ASU", "Ford Ranger 2.3"),
    (11, "14-09ZA", "Toyota Camry 2.4 motor 2AZ"),
    (12, "18-18ALI", "Ford EcoSport 2.0"),
    (13, "EPV-4029R-STD-3", "Hyundai Accent 1.6 motor G4EC (sobremedida)"),
    (14, "EPV-1725R-060-3", "Camión Ford Cargo"),
]
FILAS = [{"id": i, "codigo": c, "descripcion": d, "especificacion_camara": None} for i, c, d in DATOS]

fallos = 0


def comprobar(nombre, obtenido, esperado):
    global fallos
    ok = obtenido == esperado
    fallos += 0 if ok else 1
    print(("  ok   " if ok else "  FALLA"), nombre)
    if not ok:
        print("         obtenido:", obtenido)
        print("         esperado:", esperado)


def codigos(consulta):
    res, modo = b.buscar(FILAS, consulta)
    return [f["codigo"] for f in res], modo


def marcas(consulta):
    res, _ = b.buscar(FILAS, consulta)
    return [f["descripcion"].split()[0] for f in res]


print("Orden natural de códigos")
cods, modo = codigos("")
comprobar("sin texto: orden natural por código",
          cods, ["12-54ASU", "12-87uy", "14-09ZA", "18-05", "18-18ALI", "21-12GRU", "21-22", "32-76", "41-56AYUDA",
                 "1009", "EPV-1725R-060-3", "EPV-1725R-060-9", "EPV-4029R-STD-2", "EPV-4029R-STD-3"])
comprobar("sin texto: modo código", modo, b.MODO_CODIGO)
comprobar("9 antes que 10 (números como números)",
          sorted(["A-10", "A-9", "A-100", "A-1"], key=b.clave_codigo), ["A-1", "A-9", "A-10", "A-100"])
comprobar("a igual número, sufijo en orden alfabético",
          sorted(["7B", "7A", "7", "07C"], key=b.clave_codigo), ["7", "7A", "7B", "07C"])

print("Búsqueda por código")
cods, modo = codigos("epv")
comprobar("«epv» ordenado por código natural", cods,
          ["EPV-1725R-060-3", "EPV-1725R-060-9", "EPV-4029R-STD-2", "EPV-4029R-STD-3"])
comprobar("modo código", modo, b.MODO_CODIGO)
comprobar("«21» -> 21-12GRU, 21-22", codigos("21")[0][:2], ["21-12GRU", "21-22"])
comprobar("código sin guiones: «epv1725» encuentra EPV-1725R-060-x", codigos("epv1725")[0],
          ["EPV-1725R-060-3", "EPV-1725R-060-9"])
comprobar("código con espacio en lugar de guion: «21 22»", codigos("21 22")[0], ["21-22"])
comprobar("minúsculas/mayúsculas indiferentes en códigos", codigos("12-87UY")[0], ["12-87uy"])
comprobar("código sin guion de 4+ caracteres: «1254asu»", codigos("1254asu")[0], ["12-54ASU"])
comprobar("«25» NO encuentra «12-54ASU» por casualidad", "12-54ASU" in codigos("25")[0], False)
comprobar("«2.5» (cilindrada) NO encuentra «12-54ASU»", "12-54ASU" in codigos("2.5")[0], False)

print("Búsqueda por descripción / marca / modelo / motor / aplicación")
comprobar("«1.6» devuelve marcas en orden alfabético (Chevrolet, Ford, Hyundai, Hyundai)",
          marcas("1.6"), ["Chevrolet", "Ford", "Hyundai", "Hyundai"])
res, modo = b.buscar(FILAS, "1.6")
comprobar("«1.6»: modo texto (no está en ningún código)", modo, b.MODO_TEXTO)
comprobar("«1.6»: orden alfabético de la descripción", [f["descripcion"] for f in res],
          sorted([f["descripcion"] for f in res], key=b.normalizar))
comprobar("marca: «toyota»", marcas("TOYOTA"), ["Toyota", "Toyota", "Toyota"])
comprobar("modelo: «accent» (sin mayúsculas)", codigos("accent")[0], ["EPV-4029R-STD-2", "EPV-4029R-STD-3"])
comprobar("motor: «g4ec»", codigos("g4ec")[0], ["EPV-4029R-STD-2", "EPV-4029R-STD-3"])
comprobar("aplicación: «camion» encuentra «Camión» (sin tildes)", codigos("camion")[0], ["EPV-1725R-060-3"])
comprobar("aplicación: «CAMIÓN» con tilde y mayúsculas", codigos("CAMIÓN")[0], ["EPV-1725R-060-3"])
comprobar("varias palabras (todas deben coincidir): «ford 1.6»", codigos("ford 1.6")[0], ["EPV-1725R-060-9"])
comprobar("palabras en otro orden: «1.6 ford»", codigos("1.6 ford")[0], ["EPV-1725R-060-9"])
comprobar("espacios extra y comas: « ford ,  fiesta »", codigos(" ford ,  fiesta ")[0], ["EPV-1725R-060-9"])
res, _ = b.buscar(FILAS, "motor")
comprobar("«motor»: alfabético por descripción",
          [f["descripcion"] for f in res], sorted([f["descripcion"] for f in res], key=b.normalizar))
comprobar("alfabético ignora mayúsculas y tildes",
          [f["id"] for f in b.buscar([{"id": 1, "codigo": "A", "descripcion": "ford"},
                                      {"id": 2, "codigo": "B", "descripcion": "Álamo ford"},
                                      {"id": 3, "codigo": "C", "descripcion": "Chevrolet ford"}], "ford")[0]],
          [2, 3, 1])
comprobar("sin coincidencias", b.buscar(FILAS, "zzzz")[0], [])

print("Duplicados y no modificar los datos originales")
duplicadas = FILAS + [dict(FILAS[0]), dict(FILAS[3]), dict(FILAS[3])]
res, _ = b.buscar(duplicadas, "")
comprobar("sin duplicados con filas repetidas", len(res), len(FILAS))
comprobar("sin duplicados en una búsqueda", [f["id"] for f in b.buscar(duplicadas, "ford")[0]].count(4), 1)
antes = copy.deepcopy(FILAS)
orden_antes = [f["id"] for f in FILAS]
for q in ("", "epv", "ford", "1.6", "zzz"):
    b.buscar(FILAS, q)
comprobar("la lista original no cambia (contenido)", FILAS, antes)
comprobar("la lista original no cambia (orden)", [f["id"] for f in FILAS], orden_antes)
res, _ = b.buscar(FILAS, "")
comprobar("el resultado es una lista nueva", res is not FILAS, True)

print("Campos opcionales (marca/modelo/motor propios, si algún día existen)")
extra = [{"id": 1, "codigo": "X-1", "descripcion": "Pistón estándar", "marca": "Mazda", "modelo": "Demio", "motor": "ZJ"}]
comprobar("busca en «marca»", len(b.buscar(extra, "mazda")[0]), 1)
comprobar("busca en «modelo»", len(b.buscar(extra, "demio")[0]), 1)
comprobar("busca en «motor»", len(b.buscar(extra, "zj")[0]), 1)
comprobar("filas con None no fallan", len(b.buscar([{"id": 1, "codigo": None, "descripcion": None}], "a")[0]), 0)

print()
print("TODO CORRECTO" if not fallos else f"{fallos} PRUEBA(S) FALLARON")
raise SystemExit(1 if fallos else 0)
