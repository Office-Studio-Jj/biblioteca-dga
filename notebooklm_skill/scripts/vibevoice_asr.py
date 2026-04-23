#!/usr/bin/env python3
"""
vibevoice_asr.py — Transcripcion estructurada + videos virales con VibeVoice-ASR
==================================================================================

Modelo: microsoft/VibeVoice-ASR (MIT, 2026-01)
Features: speaker diarization + timestamping + transcripcion en una sola pasada.
Duracion maxima: 60 min de audio continuo.

Integracion:
  - Primaria: HuggingFace Inference API (VIBEVOICE_HF_TOKEN)
  - Secundaria: transformers local (si GPU disponible)

Uso standalone:
  python vibevoice_asr.py --input podcast.mp3 --out transcripcion.json
  python vibevoice_asr.py --input video.mp4 --highlights
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Optional

_HF_API_URL = "https://api-inference.huggingface.co/models/microsoft/VibeVoice-ASR"


def _tiene_transformers_local() -> bool:
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def transcribir_via_hf_api(audio_path: str, token: str,
                            language: Optional[str] = None,
                            vocabulary: Optional[list[str]] = None,
                            timeout: int = 600) -> dict:
    """Llama a HuggingFace Inference API con el modelo VibeVoice-ASR.

    Returns:
        dict con keys: ok, segments, full_text, duration, model, error
    """
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as e:
        return {"ok": False, "error": f"No se pudo leer {audio_path}: {e}"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "audio/wav",  # HF autodetecta formato igual
    }
    if language:
        headers["X-Language"] = language
    if vocabulary:
        headers["X-Vocabulary"] = ",".join(vocabulary)

    req = urllib.request.Request(_HF_API_URL, data=audio_bytes,
                                   headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        # Formato esperado: {"text": "...", "chunks": [{"timestamp": [s,e], "text": "...", "speaker": "..."}]}
        segments = []
        for ch in data.get("chunks", []):
            ts = ch.get("timestamp", [0, 0])
            segments.append({
                "speaker": ch.get("speaker", "SPEAKER_00"),
                "start": ts[0],
                "end": ts[1],
                "text": ch.get("text", "").strip(),
            })
        return {
            "ok": True,
            "segments": segments,
            "full_text": data.get("text", ""),
            "duration": segments[-1]["end"] if segments else 0,
            "model": "microsoft/VibeVoice-ASR (HF Inference API)",
        }
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HF API HTTP {e.code}: {e.reason}",
                "detalle": e.read().decode("utf-8", errors="ignore")[:500]}
    except Exception as e:
        return {"ok": False, "error": f"HF API error: {e}"}


def transcribir_via_transformers_local(audio_path: str,
                                         language: Optional[str] = None) -> dict:
    """Usa transformers local (requiere GPU recomendado, CPU funciona pero lento)."""
    try:
        from transformers import pipeline
    except ImportError:
        return {"ok": False, "error": "transformers no instalado. pip install transformers torch accelerate"}
    try:
        t0 = time.time()
        asr = pipeline("automatic-speech-recognition",
                       model="microsoft/VibeVoice-ASR",
                       chunk_length_s=30,
                       return_timestamps="word")
        result = asr(audio_path, generate_kwargs={"language": language} if language else None)
        chunks = result.get("chunks", [])
        segments = []
        for ch in chunks:
            ts = ch.get("timestamp", (0, 0))
            segments.append({
                "speaker": ch.get("speaker", "SPEAKER_00"),
                "start": ts[0] if ts else 0,
                "end": ts[1] if ts and len(ts) > 1 else 0,
                "text": ch.get("text", "").strip(),
            })
        return {
            "ok": True,
            "segments": segments,
            "full_text": result.get("text", ""),
            "duration": segments[-1]["end"] if segments else 0,
            "model": "microsoft/VibeVoice-ASR (transformers local)",
            "tiempo_inferencia": round(time.time() - t0, 1),
        }
    except Exception as e:
        return {"ok": False, "error": f"Transformers error: {e}"}


def transcribir(audio_path: str, language: str = "es",
                 vocabulary: Optional[list[str]] = None) -> dict:
    """Orquestador: intenta HF API, luego transformers local, luego falla con mensaje claro."""
    token = os.environ.get("VIBEVOICE_HF_TOKEN") or os.environ.get("HF_TOKEN")
    if token:
        print(f"[VIBEVOICE] Usando HuggingFace Inference API ({audio_path})")
        r = transcribir_via_hf_api(audio_path, token, language=language, vocabulary=vocabulary)
        if r.get("ok"):
            return r
        print(f"[VIBEVOICE] HF API fallo: {r.get('error')}. Intentando local...")

    if _tiene_transformers_local():
        print(f"[VIBEVOICE] Usando transformers local ({audio_path})")
        return transcribir_via_transformers_local(audio_path, language=language)

    return {
        "ok": False,
        "error": (
            "VibeVoice-ASR no esta configurado. "
            "Opciones: (1) Export VIBEVOICE_HF_TOKEN=<hf_token>. "
            "(2) pip install transformers torch accelerate."
        ),
        "setup_instructions": {
            "opcion_1_api": "https://huggingface.co/settings/tokens (crear token de acceso)",
            "opcion_2_local": "pip install transformers torch accelerate sentencepiece",
            "modelo": "microsoft/VibeVoice-ASR (~3GB, MIT License)",
        }
    }


def exportar_srt(segments: list[dict], out_path: str) -> str:
    """Exporta segmentos a formato SRT para usar en editores de video."""
    def _fmt(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            speaker = seg.get("speaker", "")
            prefix = f"[{speaker}] " if speaker and speaker != "SPEAKER_00" else ""
            f.write(f"{i}\n")
            f.write(f"{_fmt(seg['start'])} --> {_fmt(seg['end'])}\n")
            f.write(f"{prefix}{seg['text']}\n\n")
    return out_path


_KEYWORDS_DGA = {
    "arancel", "partida", "subpartida", "codigo", "gravamen", "isc",
    "itbis", "dga", "dgii", "aduana", "importacion", "exportacion",
    "clasificacion", "merceologia", "tributario", "nomenclatura",
    "certificado", "ley", "decreto", "norma",
}


def extraer_highlights(segments: list[dict], max_highlights: int = 5,
                         min_duracion: float = 15, max_duracion: float = 45) -> list[dict]:
    """Selecciona los mejores candidatos para clips virales.

    Score = densidad de keywords DGA + longitud adecuada + pregunta/enfasis.
    """
    highlights = []
    ventana = []
    ventana_inicio = 0

    for seg in segments:
        ventana.append(seg)
        duracion_ventana = seg["end"] - ventana_inicio
        if duracion_ventana < min_duracion:
            continue
        # Sliding window
        while ventana and (seg["end"] - ventana[0]["start"]) > max_duracion:
            ventana.pop(0)
            ventana_inicio = ventana[0]["start"] if ventana else seg["end"]
        if not ventana:
            continue

        texto_ventana = " ".join(v["text"] for v in ventana).lower()
        palabras = texto_ventana.split()
        if not palabras:
            continue
        score_tecnico = sum(1 for k in _KEYWORDS_DGA if k in texto_ventana)
        score_preg = texto_ventana.count("?") * 2
        score_enfasis = sum(1 for p in ["importante", "clave", "atencion", "obligatorio"] if p in texto_ventana)
        score_total = score_tecnico + score_preg + score_enfasis

        if score_total >= 2:
            highlights.append({
                "start": round(ventana[0]["start"], 2),
                "end": round(seg["end"], 2),
                "duracion": round(seg["end"] - ventana[0]["start"], 2),
                "texto": " ".join(v["text"] for v in ventana),
                "score": score_total,
                "titulo_sugerido": _generar_titulo(texto_ventana, score_tecnico),
                "hashtags": ["#AduanasRD", "#DGA", "#ComercioExterior",
                             "#LogisticaPuertos", "#Arancel"],
            })
    highlights.sort(key=lambda h: h["score"], reverse=True)
    # Dedupe por solapamiento temporal
    seleccionados = []
    for h in highlights:
        if not any(abs(h["start"] - s["start"]) < 10 for s in seleccionados):
            seleccionados.append(h)
        if len(seleccionados) >= max_highlights:
            break
    return seleccionados


def _generar_titulo(texto: str, score: int) -> str:
    texto_lower = texto.lower()
    if "isc" in texto_lower:
        return "ISC en aduanas RD — lo que tienes que saber"
    if "gravamen" in texto_lower:
        return "Como se calcula el gravamen arancelario"
    if "clasificacion" in texto_lower or "partida" in texto_lower:
        return "Clave para clasificar tu mercancia"
    if "ley" in texto_lower or "decreto" in texto_lower:
        return "Lo que dice la ley sobre este tramite"
    return "Dato aduanal que debes conocer"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="VibeVoice-ASR: transcripcion + highlights")
    p.add_argument("--input", required=True, help="Archivo de audio o video")
    p.add_argument("--out", default=None, help="Ruta JSON de salida")
    p.add_argument("--srt", default=None, help="Ruta SRT de salida")
    p.add_argument("--highlights", action="store_true", help="Imprimir highlights")
    p.add_argument("--language", default="es")
    p.add_argument("--vocab", default="", help="Palabras de dominio (comma-sep)")
    args = p.parse_args()

    vocab = [v.strip() for v in args.vocab.split(",") if v.strip()] or None
    r = transcribir(args.input, language=args.language, vocabulary=vocab)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"[VIBEVOICE] JSON -> {args.out}")
    else:
        print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])

    if r.get("ok") and args.srt:
        exportar_srt(r["segments"], args.srt)
        print(f"[VIBEVOICE] SRT -> {args.srt}")

    if r.get("ok") and args.highlights:
        hs = extraer_highlights(r["segments"])
        print(f"[VIBEVOICE] Highlights ({len(hs)}):")
        for h in hs:
            print(f"  [{h['start']}-{h['end']}s] {h['titulo_sugerido']} (score={h['score']})")

    sys.exit(0 if r.get("ok") else 1)
