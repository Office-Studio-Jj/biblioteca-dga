"""
compress_subagent.py — Sub-agente autónomo de compresión DGA
Se ejecuta de forma autonoma: detecta cambios en fuentes y corre el pipeline.

Modos:
  python compress_subagent.py               → un ciclo + reporte
  python compress_subagent.py --watch       → loop continuo (daemon)
  python compress_subagent.py --forzar      → fuerza reprocesado completo
  python compress_subagent.py --endpoint    → expone resultados via Flask API

Integración con server.py:
  El sub-agente registra su estado en subagent_status.json.
  El endpoint /admin/compress-status de server.py puede consultarlo.
"""

import os
import sys
import json
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Asegurar que el directorio raiz esta en el path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "notebooklm_skill" / "data" / "fuentes_nomenclatura"
COMPRESSED_DIR = ROOT / "notebooklm_skill" / "data" / "compressed"
STATUS_FILE = COMPRESSED_DIR / "subagent_status.json"
LOG_FILE = COMPRESSED_DIR / "subagent.log"
PIPELINE_SCRIPT = SCRIPT_DIR / "auto_compress_pipeline.py"

WATCH_INTERVAL_S = 300          # Revisar cambios cada 5 minutos
PIPELINE_TIMEOUT_S = 600        # Pipeline max 10 minutos
VERSION = "1.0.0"


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str, nivel: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{ts}] [{nivel}] {msg}"
    print(linea, flush=True)
    try:
        COMPRESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


# ── Estado del sub-agente ────────────────────────────────────────────────────

def leer_estado() -> dict:
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "version": VERSION,
        "ultimo_run": None,
        "ultimo_modo": None,
        "archivos_procesados": 0,
        "tiempo_consulta_estimado": "desconocido",
        "estado": "inactivo",
        "errores": [],
    }


def escribir_estado(estado: dict):
    COMPRESSED_DIR.mkdir(parents=True, exist_ok=True)
    estado["timestamp"] = datetime.now().isoformat()
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


# ── Deteccion de cambios ─────────────────────────────────────────────────────

def hash_directorio(directorio: Path) -> str:
    """Hash colectivo de todos los archivos en el directorio."""
    h = hashlib.md5()
    for archivo in sorted(directorio.glob("*")):
        if archivo.is_file() and archivo.suffix.lower() in {
            ".pdf", ".json", ".txt", ".docx", ".xlsx"
        }:
            h.update(archivo.name.encode())
            h.update(str(archivo.stat().st_mtime).encode())
            h.update(str(archivo.stat().st_size).encode())
    return h.hexdigest()


def hay_cambios(estado: dict) -> tuple[bool, str]:
    """Compara hash actual del directorio con el almacenado."""
    hash_actual = hash_directorio(DATA_DIR)
    hash_previo = estado.get("hash_directorio", "")
    if hash_actual != hash_previo:
        return True, hash_actual
    return False, hash_previo


# ── Ejecucion del pipeline ───────────────────────────────────────────────────

def ejecutar_pipeline(modo: str = "incremental", forzar: bool = False) -> dict:
    """Llama al pipeline principal como subproceso."""
    cmd = [sys.executable, str(PIPELINE_SCRIPT), f"--modo={modo}"]
    if forzar:
        cmd.append("--forzar")

    log(f"Iniciando pipeline modo={modo} forzar={forzar}")
    resultado = {
        "exito": False,
        "codigo_salida": -1,
        "duracion_s": 0,
        "stats": {},
    }

    try:
        t0 = time.time()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PIPELINE_TIMEOUT_S,
            cwd=str(ROOT),
        )
        resultado["duracion_s"] = round(time.time() - t0, 1)
        resultado["codigo_salida"] = proc.returncode
        resultado["exito"] = proc.returncode == 0

        if proc.stdout:
            log(f"Pipeline stdout:\n{proc.stdout[-2000:]}")
        if proc.stderr and proc.returncode != 0:
            log(f"Pipeline stderr:\n{proc.stderr[-1000:]}", "WARN")

        # Leer stats generados por el pipeline
        stats_file = COMPRESSED_DIR / "stats.json"
        if stats_file.exists():
            with open(stats_file, "r", encoding="utf-8") as f:
                resultado["stats"] = json.load(f)

    except subprocess.TimeoutExpired:
        log(f"Pipeline timeout ({PIPELINE_TIMEOUT_S}s)", "ERR")
        resultado["error"] = "timeout"
    except Exception as e:
        log(f"Error ejecutando pipeline: {e}", "ERR")
        resultado["error"] = str(e)

    return resultado


# ── Reporte al supervisor interno ─────────────────────────────────────────────

def notificar_supervisor(resultado: dict) -> None:
    """Actualiza el estado que server.py puede consultar via /admin/compress-status."""
    estado = leer_estado()
    estado["ultimo_run"] = datetime.now().isoformat()
    estado["ultimo_modo"] = resultado.get("modo", "incremental")
    estado["estado"] = "ok" if resultado["exito"] else "error"

    if resultado["exito"] and resultado.get("stats"):
        stats = resultado["stats"]
        estado["archivos_procesados"] = stats.get("archivos_procesados", 0)
        estado["total_chunks"] = stats.get("total_chunks", 0)
        estado["tiempo_consulta_estimado"] = stats.get("tiempo_consulta_estimado", "?")
        estado["zip_kb"] = stats.get("zip_kb", 0)
        estado["reduccion_pct"] = stats.get("reduccion_pct", 0)
    elif not resultado["exito"]:
        error_msg = resultado.get("error", f"codigo={resultado['codigo_salida']}")
        estado.setdefault("errores", []).append({
            "timestamp": datetime.now().isoformat(),
            "error": error_msg,
        })
        estado["errores"] = estado["errores"][-10:]  # Solo los ultimos 10

    escribir_estado(estado)
    log(f"Estado actualizado: {estado['estado']}")


# ── Modo watch (daemon) ───────────────────────────────────────────────────────

def modo_watch(forzar_primero: bool = False) -> None:
    """Loop continuo: detecta cambios y ejecuta pipeline si es necesario."""
    log(f"Sub-agente iniciado en modo watch (intervalo={WATCH_INTERVAL_S}s)")
    estado = leer_estado()
    estado["estado"] = "watching"
    escribir_estado(estado)

    primer_ciclo = True
    while True:
        try:
            hay_cambio, hash_nuevo = hay_cambios(estado)

            modo = "incremental"
            debe_ejecutar = False

            if primer_ciclo and forzar_primero:
                debe_ejecutar = True
                modo = "full"
                log("Primer ciclo con --forzar: ejecutando pipeline completo")
            elif hay_cambio:
                debe_ejecutar = True
                log(f"Cambios detectados en {DATA_DIR.name}. Ejecutando pipeline...")
            else:
                log("Sin cambios en fuentes. Esperando...")

            if debe_ejecutar:
                resultado = ejecutar_pipeline(modo=modo, forzar=(primer_ciclo and forzar_primero))
                resultado["modo"] = modo
                notificar_supervisor(resultado)
                estado = leer_estado()
                estado["hash_directorio"] = hash_nuevo
                escribir_estado(estado)

                if resultado["exito"]:
                    stats = resultado.get("stats", {})
                    log(f"Pipeline OK: {stats.get('total_chunks', '?')} chunks, "
                        f"consulta ~{stats.get('tiempo_consulta_estimado', '?')}s")
                else:
                    log("Pipeline fallo. Reintentando en el proximo ciclo.", "WARN")

            primer_ciclo = False
            time.sleep(WATCH_INTERVAL_S)

        except KeyboardInterrupt:
            log("Sub-agente detenido por el usuario.")
            estado = leer_estado()
            estado["estado"] = "detenido"
            escribir_estado(estado)
            break
        except Exception as e:
            log(f"Error en loop watch: {e}", "ERR")
            time.sleep(30)


# ── Modo unico (un ciclo) ─────────────────────────────────────────────────────

def modo_unico(forzar: bool = False, modo_pipeline: str = "incremental") -> dict:
    """Ejecuta el pipeline una vez y reporta resultado."""
    log("Sub-agente: ejecucion unica")
    estado = leer_estado()
    hay_cambio, hash_nuevo = hay_cambios(estado)

    if not hay_cambio and not forzar:
        log("Sin cambios en fuentes. Usa --forzar para reprocesar igual.")
        return {"accion": "omitida", "razon": "sin_cambios"}

    resultado = ejecutar_pipeline(modo=modo_pipeline, forzar=forzar)
    resultado["modo"] = modo_pipeline
    notificar_supervisor(resultado)

    estado = leer_estado()
    estado["hash_directorio"] = hash_nuevo
    escribir_estado(estado)

    return resultado


# ── Endpoint Flask (opcional) ────────────────────────────────────────────────

def iniciar_endpoint(puerto: int = 5050) -> None:
    """Mini servidor que expone /status del sub-agente."""
    try:
        from flask import Flask, jsonify
        app = Flask("compress-subagent")

        @app.route("/status")
        def status():
            return jsonify(leer_estado())

        @app.route("/run", methods=["POST"])
        def run():
            resultado = modo_unico(forzar=True, modo_pipeline="full")
            return jsonify(resultado)

        log(f"Endpoint del sub-agente en http://localhost:{puerto}/status")
        app.run(host="127.0.0.1", port=puerto, debug=False)
    except ImportError:
        log("Flask no disponible para modo --endpoint", "WARN")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sub-agente autonomo de compresion — Biblioteca DGA"
    )
    parser.add_argument("--watch", action="store_true",
                        help="Modo daemon: monitorear cambios continuamente")
    parser.add_argument("--forzar", action="store_true",
                        help="Forzar reprocesado completo aunque no haya cambios")
    parser.add_argument("--modo", choices=["full", "rapido", "incremental"],
                        default="incremental", help="Modo del pipeline (default: incremental)")
    parser.add_argument("--endpoint", action="store_true",
                        help="Exponer estado via HTTP en puerto 5050")
    parser.add_argument("--status", action="store_true",
                        help="Mostrar estado actual del sub-agente y salir")
    args = parser.parse_args()

    if args.status:
        estado = leer_estado()
        print(json.dumps(estado, indent=2, ensure_ascii=False))
        return

    if args.endpoint:
        iniciar_endpoint()
        return

    if args.watch:
        modo_watch(forzar_primero=args.forzar)
    else:
        resultado = modo_unico(forzar=args.forzar, modo_pipeline=args.modo)
        if resultado.get("exito"):
            stats = resultado.get("stats", {})
            print(f"\nOK — {stats.get('total_chunks','?')} chunks | "
                  f"~{stats.get('tiempo_consulta_estimado','?')}s consulta | "
                  f"{stats.get('zip_kb','?')} KB zip")
        elif resultado.get("accion") == "omitida":
            print("\nSin cambios — pipeline omitido. Usa --forzar si necesitas reprocesar.")
        else:
            print(f"\nFALLO — {resultado.get('error', 'ver log')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
