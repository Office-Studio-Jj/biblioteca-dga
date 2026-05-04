#!/usr/bin/env python3
"""
descargar_pdfs_notion.py
Descarga PDFs adjuntados en Cuadernos 1,2,3,5,7 de Notion
hacia notebooklm_skill/data/fuentes_nomenclatura/
C6 (VUCERD) solo tiene link Google Drive — requiere descarga manual.
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(_HERE, "notebooklm_skill", "data", "fuentes_nomenclatura")


def _load_env():
    env_path = os.path.join(_HERE, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()
TOKEN = os.getenv("NOTION_API_KEY", "")

CUADERNOS = [
    ("cuaderno_1_aforo",      "34c35f1c-d8ea-8184-9929-e4f2c6b4eae6", "Archivos"),
    ("cuaderno_2_legal",      "34c35f1c-d8ea-81be-aa7d-c1b908c8c070", "Archivos"),
    ("cuaderno_3_regimenes",  "34c35f1c-d8ea-8159-afd7-ef8e02fea8de", "Archivos"),
    ("cuaderno_5_origen",     "34c35f1c-d8ea-8141-8bfa-faf8b1b05a86", "Archivos"),
    ("cuaderno_7_valoracion", "34c35f1c-d8ea-8112-acc8-c001b43f933e", "Archivos"),
]


def _notion_get(path: str) -> dict:
    req = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _download(url: str, dest: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def main():
    if not TOKEN:
        print("ERROR: NOTION_API_KEY no configurada.")
        raise SystemExit(1)

    os.makedirs(DEST, exist_ok=True)
    total_ok = total_skip = total_err = 0

    for nombre, page_id, prop_name in CUADERNOS:
        print(f"\n{'='*55}")
        print(f"  {nombre.upper()}")
        print(f"{'='*55}")

        try:
            page = _notion_get(f"/pages/{page_id}")
        except Exception as e:
            print(f"  ERROR al obtener pagina: {e}")
            continue

        files_prop = page.get("properties", {}).get(prop_name, {})
        files = files_prop.get("files", [])

        if not files:
            print(f"  Sin archivos en propiedad '{prop_name}'")
            continue

        for item in files:
            fname = item.get("name", "archivo")
            ext = os.path.splitext(fname)[1].lower()

            if ext != ".pdf":
                print(f"  SKIP {ext.upper() or '?'}: {fname}")
                total_skip += 1
                continue

            ftype = item.get("type", "")
            if ftype == "file":
                url = item.get("file", {}).get("url", "")
            elif ftype == "external":
                url = item.get("external", {}).get("url", "")
            else:
                url = ""

            if not url:
                print(f"  SKIP (sin URL): {fname}")
                total_skip += 1
                continue

            dest_path = os.path.join(DEST, fname)
            if os.path.exists(dest_path):
                size_kb = os.path.getsize(dest_path) // 1024
                print(f"  YA EXISTE ({size_kb} KB): {fname}")
                total_skip += 1
                continue

            try:
                print(f"  Descargando: {fname}...", end=" ", flush=True)
                nbytes = _download(url, dest_path)
                print(f"OK ({nbytes // 1024} KB)")
                total_ok += 1
            except urllib.error.HTTPError as e:
                print(f"HTTP {e.code}")
                total_err += 1
            except Exception as e:
                print(f"ERROR: {e}")
                total_err += 1

    print(f"\n{'='*55}")
    print(f"  RESULTADO: {total_ok} descargados | {total_skip} saltados | {total_err} errores")
    print(f"{'='*55}")
    print("\nNOTA: Cuaderno 6 (VUCERD) solo tiene link Google Drive.")
    print("      Descargar manualmente desde: https://drive.google.com/drive/folders/15jTAhN30EmgjSzl5RAHjKzdxQ-ZUfDIf")


if __name__ == "__main__":
    main()
