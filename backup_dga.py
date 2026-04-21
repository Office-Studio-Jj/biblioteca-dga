#!/usr/bin/env python3
"""
BACKUP DGA — Sistema de respaldo 3 capas
=========================================
Capa 1: GitHub (codigo + cache via git push)
Capa 2: D:\\Backup-BibliotecaDGA\\ (todo, incluyendo usuarios)
Capa 3: Disco externo (si esta conectado)

Uso:
  python backup_dga.py              # Backup completo
  python backup_dga.py --status     # Ver ultimo backup
  python backup_dga.py --capa 2     # Solo copia local
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─── Rutas ───────────────────────────────────────────────────────────────────
PROYECTO = Path(__file__).parent
USUARIOS_DIR = Path(r"C:\Users\Usuario\Desktop\Biblioteca Notebooklm DGA\usuarios_y_administradores")
BACKUP_LOCAL = Path(r"D:\Backup-BibliotecaDGA")
LOG_PATH = PROYECTO / "backup_log.json"

ARCHIVOS_CRITICOS = [
    PROYECTO / "notebooklm_skill/data/fuentes_nomenclatura/arancel_cache.json",
    PROYECTO / "notebooklm_skill/data/fuentes_nomenclatura/gravamenes_lookup.json",
    PROYECTO / "notebooklm_skill/data/fuentes_nomenclatura/correcciones_manuales.json",
    PROYECTO / "notebooklm_skill/data/fuentes_nomenclatura/arancel_cache_backup_666.json",
    PROYECTO / "notebooklm_skill/data/state.json",
    PROYECTO / "notebooklm_skill/data/errores_recurrentes.json",
    PROYECTO / "server.py",
]

ARCHIVOS_USUARIOS = [
    USUARIOS_DIR / "usuarios.json",
    USUARIOS_DIR / "passwords.json",
    USUARIOS_DIR / "solicitudes.json",
    USUARIOS_DIR / "historial_invitados.json",
    USUARIOS_DIR / "cuadernos.json",
    USUARIOS_DIR / "recuperaciones.json",
]


def _log(resultado: dict):
    historial = []
    if LOG_PATH.exists():
        try:
            historial = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            historial = []
    historial.append(resultado)
    historial = historial[-30:]  # Mantener ultimos 30
    LOG_PATH.write_text(json.dumps(historial, indent=2, ensure_ascii=False), encoding="utf-8")


def _detectar_disco_externo() -> Path | None:
    """Detecta unidades extraibles conectadas."""
    try:
        import subprocess
        out = subprocess.check_output(
            "wmic logicaldisk where drivetype=2 get caption",
            shell=True, text=True, encoding="utf-8", errors="ignore"
        )
        for line in out.splitlines():
            letra = line.strip()
            if letra and len(letra) == 2 and letra[1] == ":":
                return Path(letra) / "Backup-BibliotecaDGA"
    except Exception:
        pass
    return None


def capa1_github() -> dict:
    """Git add + commit + push de archivos del proyecto."""
    resultado = {"capa": "GitHub", "ok": False, "detalle": ""}
    try:
        os.chdir(PROYECTO)
        subprocess.run(["git", "add",
            "notebooklm_skill/scripts/",
            "notebooklm_skill/data/fuentes_nomenclatura/arancel_cache.json",
            "notebooklm_skill/data/fuentes_nomenclatura/gravamenes_lookup.json",
            "notebooklm_skill/data/fuentes_nomenclatura/correcciones_manuales.json",
            "notebooklm_skill/data/errores_recurrentes.json",
            "backup_dga.py",
        ], check=False, capture_output=True)

        # Solo staged changes (lineas que empiezan con M/A/D, no ??)
        status_raw = subprocess.run(["git", "status", "--porcelain"],
            capture_output=True, text=True).stdout
        status = "\n".join(l for l in status_raw.splitlines()
                           if l and l[0] in ("M", "A", "D", "R", "C"))

        if status:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            commit = subprocess.run(["git", "commit", "-m",
                f"backup: auto-backup {ts} [backup_dga.py]"],
                capture_output=True, text=True)
            if commit.returncode != 0 and "nothing to commit" not in commit.stdout + commit.stderr:
                resultado["detalle"] = commit.stderr[:200]
                return resultado

        push = subprocess.run(["git", "push", "origin", "main"],
            capture_output=True, text=True)

        if push.returncode == 0:
            resultado["ok"] = True
            resultado["detalle"] = "Push exitoso" if status else "Sin cambios, push OK"
        else:
            resultado["detalle"] = push.stderr[:200]
    except Exception as e:
        resultado["detalle"] = str(e)
    return resultado


def _copiar_a_destino(destino: Path) -> dict:
    """Copia archivos criticos y de usuarios a un directorio destino."""
    copiados = 0
    errores = []

    # Subcarpeta con timestamp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = destino / ts
    carpeta.mkdir(parents=True, exist_ok=True)

    # Carpeta "latest" siempre con la version mas reciente
    latest = destino / "latest"
    if latest.exists():
        shutil.rmtree(latest)
    latest.mkdir(parents=True, exist_ok=True)

    for archivo in ARCHIVOS_CRITICOS + ARCHIVOS_USUARIOS:
        if archivo.exists():
            try:
                shutil.copy2(archivo, carpeta / archivo.name)
                shutil.copy2(archivo, latest / archivo.name)
                copiados += 1
            except Exception as e:
                errores.append(f"{archivo.name}: {e}")

    # Limpiar backups viejos — mantener solo los ultimos 10
    snapshots = sorted([d for d in destino.iterdir()
        if d.is_dir() and d.name != "latest"], reverse=True)
    for viejo in snapshots[10:]:
        shutil.rmtree(viejo, ignore_errors=True)

    return {"copiados": copiados, "errores": errores, "ruta": str(carpeta)}


def capa2_local() -> dict:
    resultado = {"capa": "D:\\Backup-BibliotecaDGA", "ok": False, "detalle": ""}
    try:
        info = _copiar_a_destino(BACKUP_LOCAL)
        resultado["ok"] = len(info["errores"]) == 0
        resultado["detalle"] = f"{info['copiados']} archivos ->{info['ruta']}"
        if info["errores"]:
            resultado["detalle"] += f" | Errores: {', '.join(info['errores'])}"
    except Exception as e:
        resultado["detalle"] = str(e)
    return resultado


def capa3_externo() -> dict:
    resultado = {"capa": "Disco externo", "ok": False, "detalle": ""}
    disco = _detectar_disco_externo()
    if not disco:
        resultado["detalle"] = "No hay disco externo conectado"
        return resultado
    try:
        info = _copiar_a_destino(disco)
        resultado["ok"] = len(info["errores"]) == 0
        resultado["detalle"] = f"{info['copiados']} archivos ->{info['ruta']}"
    except Exception as e:
        resultado["detalle"] = str(e)
    return resultado


def backup_completo(capas=(1, 2, 3)) -> list:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[BACKUP DGA] {ts}")
    resultados = []

    if 1 in capas:
        r = capa1_github()
        resultados.append(r)
        estado = "OK" if r["ok"] else "FALLO"
        print(f"  Capa 1 GitHub:       [{estado}] {r['detalle']}")

    if 2 in capas:
        r = capa2_local()
        resultados.append(r)
        estado = "OK" if r["ok"] else "FALLO"
        print(f"  Capa 2 Local (D:):   [{estado}] {r['detalle']}")

    if 3 in capas:
        r = capa3_externo()
        resultados.append(r)
        estado = "OK" if r["ok"] else "SKIP" if "No hay" in r["detalle"] else "FALLO"
        print(f"  Capa 3 Externo:      [{estado}] {r['detalle']}")

    _log({"fecha": ts, "resultados": resultados})
    print(f"[BACKUP DGA] Completado. Log: {LOG_PATH}\n")
    return resultados


def status():
    if not LOG_PATH.exists():
        print("[BACKUP DGA] Sin historial de backups.")
        return
    historial = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    if not historial:
        print("[BACKUP DGA] Sin historial.")
        return
    ultimo = historial[-1]
    print(f"\nUltimo backup: {ultimo['fecha']}")
    for r in ultimo.get("resultados", []):
        estado = "OK" if r["ok"] else "FALLO"
        print(f"  {r['capa']}: [{estado}] {r['detalle']}")
    print(f"Total backups registrados: {len(historial)}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--capa", type=int, choices=[1, 2, 3])
    args = parser.parse_args()

    if args.status:
        status()
    elif args.capa:
        backup_completo(capas=[args.capa])
    else:
        backup_completo()
