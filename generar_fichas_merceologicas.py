"""
generar_fichas_merceologicas.py
Genera 5 fichas merceológicas prioritarias para el Clasificador Arancelario DGA.
Productos de alta consulta: accesorios de telefonía y movilidad personal.

Base legal:
- Ley 168-21 Art. 75 (clasificación arancelaria)
- Decreto 755-22 Arts. 62-77 (nomenclatura SON RD)
- Decreto 36-22 (Arancel Nacional, 7ma Enmienda SA)
- SA 7ma Enmienda OMA/WCO 2022

Organización: AMGECO Automatización y Gestión SRL
Analista: José Rodolfo Santana C.
"""

import csv
import os
from datetime import date

# ── Rutas ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR  = os.path.join(BASE_DIR, "csv")
CSV_OUT  = os.path.join(CSV_DIR, "fichas_merceologicas_5_productos.csv")

# ── Constantes compartidas ───────────────────────────────────────────────────
ESTADO       = "Borrador — Requiere validacion aforador (Ley 168-21 Art. 76)"
FUENTE_LEGAL = "Ley 168-21 Art. 75, Decreto 755-22 Arts. 62-77, Decreto 36-22"
HOY          = date.today().isoformat()

# ── 5 Fichas merceológicas ────────────────────────────────────────────────────
FICHAS = [
    {
        "Producto":              "Pantalla para celular (LCD/OLED)",
        "Clasificacion":         "Capítulo 85 — Máquinas, aparatos y material eléctrico",
        "SON_Sugerido":          "8524.91.00",
        "Materia":               "Vidrio, cristal líquido (LCD) o material orgánico emisor de luz (OLED), plástico, metal",
        "Funcion":               "Visualizar imágenes, texto y video en dispositivos de comunicación móvil",
        "Uso":                   "Repuesto/componente para teléfonos inteligentes y tabletas; uso técnico por talleres de reparación",
        "DAI_pct":               3,
        "ITBIS_pct":             18,
        "ISC_pct":               0,
        "RGI_Aplicada":          "RGI 1 — Texto de partida 85.24 (soportes para grabación o reproducción no incorporados a máquinas)",
        "Capitulo_SA":           "85",
        "Seccion_SA":            "XVI — Máquinas y aparatos, material eléctrico y sus partes",
        "Notas_Legales":         "Nota 2 Sección XVI (partes de uso general — excluidas si clasifican propiamente). Nota Explicativa 85.24 OMA.",
        "Permisos":              "INDOTEL (Ley 153-98 — certificación de equipos de telecomunicaciones)",
        "Estado":                ESTADO,
        "Fuente_Legal":          FUENTE_LEGAL,
        "Fecha_Clasificacion":   HOY,
    },
    {
        "Producto":              "Patineta eléctrica (e-scooter)",
        "Clasificacion":         "Capítulo 87 — Vehículos automóviles, tractores, ciclos",
        "SON_Sugerido":          "8711.60.00",
        "Materia":               "Acero, aluminio, plástico de alta resistencia, motor eléctrico, batería de litio",
        "Funcion":               "Transporte individual de personas mediante propulsión eléctrica",
        "Uso":                   "Movilidad urbana personal; uso recreativo o utilitario por personas naturales",
        "DAI_pct":               20,
        "ITBIS_pct":             18,
        "ISC_pct":               0,
        "RGI_Aplicada":          "RGI 1 — Texto de partida 87.11 (motocicletas y velocípedos con motor); nota: 87.11.60 = propulsión eléctrica",
        "Capitulo_SA":           "87",
        "Seccion_SA":            "XVII — Material de transporte",
        "Notas_Legales":         "Nota de Capítulo 87. Nota Explicativa 87.11 OMA (incluye ciclomotores eléctricos).",
        "Permisos":              "DGTT (Ley 63-17 — homologación y registro de vehículos de motor)",
        "Estado":                ESTADO,
        "Fuente_Legal":          FUENTE_LEGAL,
        "Fecha_Clasificacion":   HOY,
    },
    {
        "Producto":              "Cargador USB para celular",
        "Clasificacion":         "Capítulo 85 — Máquinas, aparatos y material eléctrico",
        "SON_Sugerido":          "8504.40.00",
        "Materia":               "Plástico ABS, cobre, ferrita, circuitos electrónicos integrados",
        "Funcion":               "Convertir corriente alterna (CA) en corriente continua (CC) para carga de dispositivos móviles",
        "Uso":                   "Carga de teléfonos inteligentes, tabletas y otros dispositivos portátiles; uso doméstico y comercial",
        "DAI_pct":               3,
        "ITBIS_pct":             18,
        "ISC_pct":               0,
        "RGI_Aplicada":          "RGI 1 — Texto de partida 85.04 (transformadores eléctricos, convertidores estáticos, bobinas de reactancia)",
        "Capitulo_SA":           "85",
        "Seccion_SA":            "XVI — Máquinas y aparatos, material eléctrico y sus partes",
        "Notas_Legales":         "Nota 2 Sección XVI. Nota Explicativa 85.04 OMA (incluye cargadores/adaptadores CA/CC).",
        "Permisos":              "INDOTEL (Ley 153-98 — certificación de equipos conectados a redes de telecomunicaciones)",
        "Estado":                ESTADO,
        "Fuente_Legal":          FUENTE_LEGAL,
        "Fecha_Clasificacion":   HOY,
    },
    {
        "Producto":              "Funda protectora para celular",
        "Clasificacion":         "Capítulo 42 — Manufacturas de cuero, artículos de talabartería",
        "SON_Sugerido":          "4202.99.00",
        "Materia":               "Plástico (TPU/policarbonato), cuero artificial, tela, silicona",
        "Funcion":               "Proteger el teléfono celular de golpes, arañazos y polvo",
        "Uso":                   "Accesorio de protección para teléfonos inteligentes; uso por personas naturales y distribuidores",
        "DAI_pct":               20,
        "ITBIS_pct":             18,
        "ISC_pct":               0,
        "RGI_Aplicada":          "RGI 3a — El texto de 42.02 (bolsos, estuches para aparatos) es más específico que 39.26 (manufacturas plástico)",
        "Capitulo_SA":           "42",
        "Seccion_SA":            "VIII — Pieles, cueros, peletería y manufacturas",
        "Notas_Legales":         "Nota 2(ñ) Capítulo 42 (excluye artículos del Cap. 85). Nota Explicativa 42.02 OMA (incluye estuches para teléfonos).",
        "Permisos":              "Ninguno",
        "Estado":                ESTADO,
        "Fuente_Legal":          FUENTE_LEGAL,
        "Fecha_Clasificacion":   HOY,
    },
    {
        "Producto":              "Audífonos inalámbricos bluetooth",
        "Clasificacion":         "Capítulo 85 — Máquinas, aparatos y material eléctrico",
        "SON_Sugerido":          "8518.30.00",
        "Materia":               "Plástico ABS, cobre, magnetos, circuito transmisor/receptor Bluetooth, batería recargable",
        "Funcion":               "Reproducir sonido por vía inalámbrica mediante tecnología Bluetooth; captar voz (micrófono integrado)",
        "Uso":                   "Escucha de audio, llamadas telefónicas y videoconferencias; uso por personas naturales y empresas",
        "DAI_pct":               3,
        "ITBIS_pct":             18,
        "ISC_pct":               0,
        "RGI_Aplicada":          "RGI 1 — Texto de partida 85.18 (micrófonos y auriculares, incluidos con micrófono incorporado)",
        "Capitulo_SA":           "85",
        "Seccion_SA":            "XVI — Máquinas y aparatos, material eléctrico y sus partes",
        "Notas_Legales":         "Nota 3 Sección XVI (máquinas polivalentes). Nota Explicativa 85.18 OMA (headsets inalámbricos incluidos).",
        "Permisos":              "INDOTEL (Ley 153-98 — equipos que usan espectro radioeléctrico)",
        "Estado":                ESTADO,
        "Fuente_Legal":          FUENTE_LEGAL,
        "Fecha_Clasificacion":   HOY,
    },
]

COLUMNAS = [
    "Producto", "Clasificacion", "SON_Sugerido", "Materia", "Funcion", "Uso",
    "DAI_pct", "ITBIS_pct", "ISC_pct", "RGI_Aplicada", "Capitulo_SA", "Seccion_SA",
    "Notas_Legales", "Permisos", "Estado", "Fuente_Legal", "Fecha_Clasificacion",
]


def generar_fichas() -> str:
    """Escribe las fichas merceológicas en CSV y retorna la ruta."""
    os.makedirs(CSV_DIR, exist_ok=True)

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS)
        writer.writeheader()
        for ficha in FICHAS:
            writer.writerow(ficha)

    return CSV_OUT


if __name__ == "__main__":
    ruta = generar_fichas()
    print(f"Fichas creadas: {len(FICHAS)}")
    print(f"CSV guardado en: {ruta}")
