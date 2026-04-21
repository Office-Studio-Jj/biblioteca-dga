"""
GENERADOR DE INFORME PDF COMPARATIVO
Produce un PDF descargable con el analisis comparativo de dos partidas arancelarias.
Usa fpdf2 (ligero, sin dependencias externas complejas).
"""
from datetime import datetime


def generar_informe_pdf(query: str,
                        codigo_a: str, desc_a: str, gravamen_a: str,
                        codigo_b: str, desc_b: str, gravamen_b: str,
                        analisis: dict) -> bytes:
    """
    Genera un PDF con el informe comparativo.
    Returns: bytes del PDF listo para descarga.
    """
    from fpdf import FPDF

    AZUL_DGA  = (10, 25, 60)
    DORADO    = (180, 140, 0)
    BLANCO    = (255, 255, 255)
    GRIS_CLARO = (240, 243, 248)
    GRIS_TEXTO = (80, 90, 110)
    VERDE     = (22, 120, 60)
    ROJO      = (170, 30, 30)

    veredicto      = analisis.get("veredicto", "B")
    codigo_correcto = analisis.get("codigo_correcto", codigo_b)
    pasos          = analisis.get("pasos", [])
    referencias    = analisis.get("referencias", [])
    conclusion     = analisis.get("conclusion", "")

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # ── Encabezado ──────────────────────────────────────────────────────────
    pdf.set_fill_color(*AZUL_DGA)
    pdf.rect(0, 0, 210, 38, 'F')

    pdf.set_text_color(*DORADO)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_xy(15, 7)
    pdf.cell(0, 8, "REPUBLICA DOMINICANA — DIRECCION GENERAL DE ADUANAS", ln=True)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*BLANCO)
    pdf.set_x(15)
    pdf.cell(0, 5, "Biblioteca Digital DGA — Informe de Clasificacion Arancelaria Comparativa", ln=True)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_x(15)
    pdf.cell(0, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  Arancel 7ma Enmienda — Sistema Armonizado", ln=True)

    pdf.set_y(42)

    # ── Consulta original ───────────────────────────────────────────────────
    pdf.set_fill_color(*GRIS_CLARO)
    pdf.set_text_color(*AZUL_DGA)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "  CONSULTA ORIGINAL", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GRIS_TEXTO)
    pdf.set_x(15)
    pdf.multi_cell(0, 5, _safe(query), align="L")
    pdf.ln(4)

    # ── Tabla comparativa de codigos ────────────────────────────────────────
    pdf.set_fill_color(*AZUL_DGA)
    pdf.set_text_color(*DORADO)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "  CODIGOS EN COMPARACION", ln=True, fill=True)
    pdf.ln(2)

    col = 88
    _codigo_box(pdf, codigo_a, desc_a, gravamen_a, "CODIGO A — Recomendado por Biblioteca-Consultor", veredicto == "A", col, AZUL_DGA, DORADO, VERDE, ROJO)
    pdf.set_xy(15 + col + 4, pdf.get_y() - _box_height(desc_a))
    _codigo_box(pdf, codigo_b, desc_b, gravamen_b, "CODIGO B — Seleccionado por Usuario", veredicto == "B", col, AZUL_DGA, DORADO, VERDE, ROJO)
    pdf.ln(4)

    # ── Analisis paso a paso ────────────────────────────────────────────────
    pdf.set_fill_color(*AZUL_DGA)
    pdf.set_text_color(*DORADO)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "  ANALISIS COMPARATIVO PASO A PASO", ln=True, fill=True)
    pdf.ln(2)

    for idx, paso in enumerate(pasos, 1):
        if pdf.get_y() > 250:
            pdf.add_page()

        pdf.set_fill_color(220, 228, 245)
        pdf.set_text_color(*AZUL_DGA)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(0, 6, f"  Paso {idx}: {_safe(paso.get('titulo',''))}", ln=True, fill=True)

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GRIS_TEXTO)
        pdf.set_x(18)
        pdf.multi_cell(177, 4.5, _safe(paso.get("contenido", "")), align="J")
        pdf.ln(2)

    # ── Conclusion ──────────────────────────────────────────────────────────
    if pdf.get_y() > 240:
        pdf.add_page()

    color_conclusion = VERDE if veredicto in ("A", "B") else DORADO
    pdf.set_fill_color(*color_conclusion)
    pdf.set_text_color(*BLANCO)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, f"  CONCLUSION: CODIGO CORRECTO — {codigo_correcto}", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GRIS_TEXTO)
    pdf.set_x(15)
    pdf.multi_cell(0, 4.5, _safe(conclusion), align="J")
    pdf.ln(3)

    # ── Referencias ─────────────────────────────────────────────────────────
    if referencias:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*AZUL_DGA)
        pdf.cell(0, 5, "Referencias aplicadas:", ln=True)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GRIS_TEXTO)
        for ref in referencias:
            pdf.set_x(20)
            pdf.cell(0, 4.5, f"• {_safe(ref)}", ln=True)
        pdf.ln(3)

    # ── Pie de pagina ────────────────────────────────────────────────────────
    pdf.set_y(-22)
    pdf.set_fill_color(*AZUL_DGA)
    pdf.rect(0, pdf.get_y(), 210, 22, 'F')
    pdf.set_text_color(*GRIS_CLARO)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_x(15)
    pdf.cell(0, 5, "Informe generado automaticamente por Biblioteca Digital DGA — Solo para referencia tecnica. "
                   "La clasificacion arancelaria definitiva corresponde al Declarante.", ln=True)
    pdf.set_x(15)
    pdf.cell(0, 5, f"biblioteca-dga-production.up.railway.app  |  {datetime.now().strftime('%d/%m/%Y')}", ln=True)

    return bytes(pdf.output())


def _safe(texto: str) -> str:
    if not texto:
        return ""
    return (texto.replace("\u2019", "'").replace("\u201c", '"')
                 .replace("\u201d", '"').replace("\u2014", "-")
                 .replace("\u2013", "-").replace("\u00e1", "a")
                 .replace("\u00e9", "e").replace("\u00ed", "i")
                 .replace("\u00f3", "o").replace("\u00fa", "u")
                 .replace("\u00c1", "A").replace("\u00c9", "E")
                 .replace("\u00cd", "I").replace("\u00d3", "O")
                 .replace("\u00da", "U").replace("\u00f1", "n")
                 .replace("\u00d1", "N").replace("\u00fc", "u"))


def _box_height(desc: str) -> float:
    lines = max(1, len(desc or "") // 40)
    return 28 + lines * 4.5


def _codigo_box(pdf, codigo, desc, gravamen, label, es_correcto, ancho,
                AZUL_DGA, DORADO, VERDE, ROJO):
    x = pdf.get_x()
    y = pdf.get_y()

    borde_color = VERDE if es_correcto else (180, 180, 180)
    pdf.set_draw_color(*borde_color)
    pdf.set_line_width(0.6 if es_correcto else 0.2)

    pdf.set_fill_color(235, 240, 255)
    pdf.rect(x, y, ancho, 28, 'DF')

    pdf.set_xy(x + 2, y + 2)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*AZUL_DGA)
    pdf.cell(ancho - 4, 4, _safe(label), ln=True)

    pdf.set_xy(x + 2, y + 7)
    pdf.set_font("Helvetica", "B", 11)
    color_codigo = VERDE if es_correcto else ROJO
    pdf.set_text_color(*color_codigo)
    pdf.cell(ancho - 4, 6, codigo, ln=True)

    pdf.set_xy(x + 2, y + 14)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(60, 70, 90)
    desc_corta = (_safe(desc or "")[:90] + "...") if len(desc or "") > 90 else _safe(desc or "Sin descripcion")
    pdf.multi_cell(ancho - 4, 3.5, desc_corta)

    pdf.set_xy(x + 2, y + 22)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*AZUL_DGA)
    pdf.cell(ancho - 4, 4, f"Gravamen NMF: {gravamen}%")

    if es_correcto:
        pdf.set_xy(x + ancho - 22, y + 2)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*VERDE)
        pdf.cell(20, 4, "CORRECTO", align="R")

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.set_xy(x + ancho + 4, y)
