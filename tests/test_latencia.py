"""/health/latencia: resumen de tiempos de /consultar sin guardar el texto de las preguntas."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server  # noqa: E402


def test_resumen_y_meta():
    server._LATENCIAS.clear()
    for ms, ruta in [(900, "cache"), (4000, "orquestador_v2"), (6000, "orquestador_v2"), (20000, "general")]:
        server._LATENCIAS.append({"ms": ms, "cuaderno": "biblioteca-de-nomenclaturas", "ruta": ruta, "ts": 1})
    datos = server.app.test_client().get("/health/latencia").get_json()
    assert datos["sin_cache"]["n"] == 3 and datos["sin_cache"]["max_ms"] == 20000
    assert datos["cumple_meta"] is False
    assert datos["por_ruta"]["cache"]["n"] == 1
    assert all("pregunta" not in d and "question" not in d for d in server._LATENCIAS)


def test_sin_datos():
    server._LATENCIAS.clear()
    datos = server.app.test_client().get("/health/latencia").get_json()
    assert datos["sin_cache"] == {"n": 0} and datos["cumple_meta"] is None
