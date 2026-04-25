"""
Test anti-regresion del Pipeline 3 Capas.

Garantiza que el patron de busqueda Capa3 -> Capa2 -> Capa1 NO se rompa.

Ejecucion:
    python notebooklm_skill/scripts/test_pipeline_3_capas.py

Exit code:
    0 = todas las capas funcionan, codigos esperados correctos
    1 = REGRESION DETECTADA — algo rompio el patron arquitectonico
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline_3_capas import ejecutar_pipeline

# Casos de prueba canonicos: cada uno debe retornar el codigo esperado pasando
# por las 3 capas en orden. Si se agrega ficha merceologica nueva, agregar caso aqui.
CASOS_CANONICOS = [
    {
        "consulta": "Dron aereo para agricultura",
        "codigo_esperado": "8806.23.19",
        "gravamen_esperado": "8%",
        "beneficio_legal": "Ley 150-97",
    },
    {
        "consulta": "Camara zoom 10K para sala de conferencias",
        "codigo_esperado": "8525.89.19",
        "gravamen_esperado": "20%",
        "beneficio_legal": None,
    },
]


def test_caso(caso: dict) -> tuple[bool, str]:
    """Ejecuta un caso y retorna (paso, mensaje)."""
    consulta = caso["consulta"]
    esperado = caso["codigo_esperado"]
    gravamen = caso.get("gravamen_esperado")

    traz = ejecutar_pipeline(consulta, notebook_id="biblioteca-de-nomenclaturas")
    capas = traz.get("capas", [])

    # Las 3 capas deben haberse ejecutado en orden
    if len(capas) != 3:
        return False, f"Solo {len(capas)} capas ejecutadas (esperaba 3)"
    if [c.get("capa") for c in capas] != [3, 2, 1]:
        return False, f"Orden capas roto: {[c.get('capa') for c in capas]}"

    # Capas con ok=True
    for i, c in enumerate(capas):
        if not c.get("ok"):
            return False, f"Capa {c.get('capa')} fallo: {c.get('error', 'sin detalle')}"

    # Codigo final correcto
    codigo = traz.get("codigo_final")
    if codigo != esperado:
        return False, f"Codigo {codigo} != esperado {esperado}"

    # Gravamen correcto
    if gravamen and traz.get("gravamen_final") != gravamen:
        return False, f"Gravamen {traz.get('gravamen_final')} != {gravamen}"

    # Beneficio legal detectado cuando aplica
    if caso.get("beneficio_legal"):
        bases = traz.get("base_legal", [])
        if not any(caso["beneficio_legal"] in str(b) for b in bases):
            return False, f"Beneficio {caso['beneficio_legal']} no detectado"

    # Patron intacto
    if not traz.get("patron_intacto"):
        return False, "patron_intacto = False"

    return True, f"OK ({traz.get('tiempo_total_ms')}ms, {codigo})"


def main():
    print("=== Anti-regresion Pipeline 3 Capas ===\n")
    fallos = 0
    for i, caso in enumerate(CASOS_CANONICOS, 1):
        ok, msg = test_caso(caso)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] Caso {i}: {caso['consulta'][:60]}")
        print(f"        {msg}")
        if not ok:
            fallos += 1

    print(f"\nResultado: {len(CASOS_CANONICOS) - fallos}/{len(CASOS_CANONICOS)} casos pasaron")
    if fallos:
        print(f"\n*** {fallos} REGRESION(ES) DETECTADA(S) — patron arquitectonico roto ***")
        sys.exit(1)
    print("OK — patron 3 capas intacto.")
    sys.exit(0)


if __name__ == "__main__":
    main()
