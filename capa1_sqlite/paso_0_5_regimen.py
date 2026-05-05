"""
Paso 0.5 — Verificación de Régimen Aduanero (CEO 05-05-2026 Sección 3.1)
Antes de clasificar, determinar bajo qué régimen se importa la mercancía.
El régimen condiciona exenciones y tasas del Paso 8.5.
"""

REGIMENES_VALIDOS = {
    "importacion_definitiva": {
        "nombre": "Importación definitiva",
        "base_legal": "Ley 168-21 Art. 131",
        "descripcion": "Mercancía destinada a permanecer indefinidamente en territorio aduanero.",
        "aplica_dai": True,
        "aplica_itbis": True,
        "aplica_isc": True,
        "exencion_posible": False,
    },
    "admision_temporal": {
        "nombre": "Admisión temporal",
        "base_legal": "Ley 168-21 Art. 134",
        "descripcion": "Mercancía que ingresa con suspensión total o parcial de tributos por plazo determinado.",
        "aplica_dai": False,
        "aplica_itbis": False,
        "aplica_isc": False,
        "exencion_posible": True,
    },
    "zona_franca": {
        "nombre": "Zona franca",
        "base_legal": "Ley 226-06, Decreto 151-22",
        "descripcion": "Mercancía destinada a zona franca. Exención total mientras permanezca en zona.",
        "aplica_dai": False,
        "aplica_itbis": False,
        "aplica_isc": False,
        "exencion_posible": True,
    },
    "reimportacion": {
        "nombre": "Reimportación",
        "base_legal": "Ley 168-21 Art. 139",
        "descripcion": "Mercancía nacional que retorna. Exenta si no fue modificada en el exterior.",
        "aplica_dai": False,
        "aplica_itbis": False,
        "aplica_isc": False,
        "exencion_posible": True,
    },
    "transito": {
        "nombre": "Tránsito",
        "base_legal": "Ley 168-21 Art. 140",
        "descripcion": "Mercancía que atraviesa territorio sin destino final aquí. Sin tributos.",
        "aplica_dai": False,
        "aplica_itbis": False,
        "aplica_isc": False,
        "exencion_posible": True,
    },
    "drawback": {
        "nombre": "Drawback (reintegro)",
        "base_legal": "Ley 168-21 Art. 145",
        "descripcion": "Devolución de tributos pagados por insumos incorporados en mercancía exportada.",
        "aplica_dai": True,
        "aplica_itbis": True,
        "aplica_isc": True,
        "exencion_posible": False,
    },
    "dr_cafta": {
        "nombre": "DR-CAFTA (preferencial)",
        "base_legal": "Ley 424-06, Res. DGA 357-05",
        "descripcion": "Preferencia arancelaria bajo tratado. DAI reducido o 0% según desgravación.",
        "aplica_dai": True,  # pero reducido
        "aplica_itbis": True,
        "aplica_isc": True,
        "exencion_posible": True,
    },
}


def verificar_regimen(regimen_key: str) -> dict:
    """
    Paso 0.5: Valida el régimen seleccionado y retorna sus implicaciones tributarias.
    No bloquea la clasificación técnica, pero condiciona el Paso 8.5 (cruce decretos).
    """
    if not regimen_key:
        return {
            "estado": "sin_regimen",
            "mensaje": (
                "No se especificó régimen aduanero. Se asume importación definitiva "
                "(Ley 168-21 Art. 131). Todos los tributos aplican."
            ),
            "regimen": REGIMENES_VALIDOS["importacion_definitiva"],
            "regimen_key": "importacion_definitiva",
        }

    regimen_key = regimen_key.strip().lower().replace(" ", "_").replace("-", "_")

    if regimen_key not in REGIMENES_VALIDOS:
        return {
            "estado": "invalido",
            "mensaje": f"Régimen '{regimen_key}' no reconocido. Opciones: {list(REGIMENES_VALIDOS.keys())}",
            "regimen": None,
            "regimen_key": None,
        }

    regimen = REGIMENES_VALIDOS[regimen_key]
    return {
        "estado": "ok",
        "mensaje": f"Régimen: {regimen['nombre']} ({regimen['base_legal']})",
        "regimen": regimen,
        "regimen_key": regimen_key,
    }


def mensaje_regimen_para_usuario() -> str:
    """Texto estandarizado para preguntar régimen al usuario (UI/API)."""
    return (
        "¿Bajo qué régimen aduanero se importa esta mercancía?\n"
        "Opciones:\n"
        "1. Importación definitiva (Art. 131 Ley 168-21)\n"
        "2. Admisión temporal (Art. 134)\n"
        "3. Zona franca (Ley 226-06)\n"
        "4. Reimportación (Art. 139)\n"
        "5. Tránsito (Art. 140)\n"
        "6. Drawback (Art. 145)\n"
        "7. DR-CAFTA (Ley 424-06)\n\n"
        "Si no especifica, se asume importación definitiva."
    )
