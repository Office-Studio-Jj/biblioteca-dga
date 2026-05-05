# Biblioteca DGA - Instrucciones del Proyecto

## Toolkit Integrado Disponible
- **Humanizer**: Aplicar siempre a texto generado (eliminar patrones IA)
- **UI UX Pro Max**: Usar para mejoras de interfaz y diseño
- **Superpowers**: Framework de desarrollo estructurado
- **Everything Claude Code**: 314 extensiones de productividad
- **markdownify-mcp**: Conversion de PDFs/web a Markdown

## Reglas del Proyecto
1. SDK: Usar `google-genai>=1.0.0` con `thinking_budget=0`
2. Cache Arancel: 7,616 codigos en `arancel_cache.json` - verificacion cache-first
3. Codigos RD: EXACTAMENTE 8 digitos (XXXX.XX.XX), NUNCA 10
4. Deploy: Push a main = auto-deploy en Railway
5. Fuentes PDF: Extraer con pdfplumber (0% IA)
6. Tests: Verificar consulta real en produccion despues de cada deploy
7. Passwords: bcrypt rounds=12, rehash perezoso de legacy SHA-256
8. Gravamen: tipo Decimal, nunca float
9. Seguridad datos: cumplir Ley 172-13 (datos personales) y Ley 168-21 Art. 10 (confidencialidad aduanera)

## Arquitectura (Opción B CEO 03-MAY-2026)
- Capa 1: SQLite (arancel_rd.db, 7,616 SON) — verdad exacta DAI/ITBIS/ISC
- Capa 2: Notion (3 BDs activas + 4 pendientes) — conocimiento estructurado
- Capa 3: Gemini pre-filtro (Cap. 2 dígitos) + Claude API árbitro legal (SON final)
- Flujo docs: RECIBIDO → CLASIFICADO → EN PROCESAMIENTO (Notion) → CURADO → PUBLICADO
- NotebookLM eliminado como paso intermedio

## Marco Legal Corregido (Informes CEO 04/05-05-2026)
- Ley 5-23 = Comercio Marítimo (NO "Derecho Marítimo")
- Ley 200-04 = Libre Acceso Info Pública (NO Gobierno Electrónico, NO aplica a app)
- Ley 126-02 = base legal real de VUCERD y trámites digitales
- Ley 14-93 = arancel originario, superada por Ley 168-21 Cap. III en clasificación
- Ley 146-00 = DAI vigente (Reform Arancelaria)
- Ley 172-13 = protección datos personales
- **Ley 226-06** = Régimen Nacional Zonas Francas (CEO 05-05-2026 — omisión grave corregida)
- **Ley 392-07** = Competitividad e Innovación Industrial (CEO 05-05-2026 — omisión grave corregida)
- **Decreto 36-22** = Arancel Nacional 7ma Enmienda (CEO 05-05-2026 — faltaba en tabla formal)
- **Decreto 151-22** = Reglamento Zona Franca
- Resoluciones DGA clasificación anticipada (Art. 75 Ley 168-21)
- Eliminar: Ley 200-04 y Ley 10-07 del marco normativo de la app

## Correcciones CEO 05-05-2026 (Informe Two-Brain)
- "100% precisión" → "100% cumplimiento del protocolo legal"
- Paso 0.5: verificar régimen aduanero ANTES de clasificar (`capa1_sqlite/paso_0_5_regimen.py`)
- tabla_decretos: creada en SQLite con regla prelación + changelog (`capa1_sqlite/build_tabla_decretos.py`)
- Schema ficha merceológica: definido en `notion_service/schema_ficha_merceologica.json`
- Versionamiento JSON guardián: protocolo en `notebooklm_skill/data/fuentes_nomenclatura/PROTOCOLO_VERSIONAMIENTO_JSON.md`
- Manual contingencia: `docs/MANUAL_CONTINGENCIA.md`
- Auditoría trimestral: `docs/AUDITORIA_TRIMESTRAL_DECRETOS.md`
- Alcance geográfico: solo RD, rechazo otras nomenclaturas (`docs/ALCANCE_GEOGRAFICO.md`)
- Regla prelación: especialidad > temporalidad > escalar humano (`capa1_sqlite/consultar_decretos.py`)

## BDs Notion Pendientes
- BD-Valoración (Ley 168-21 Cap. VI, Acuerdo OMC Art. VII)
- BD-Regímenes (Ley 168-21 Cap. V, Ley 8-90)
- BD-VUCERD (Ley 126-02, Ley 168-21 Arts. 15-17)
- BD-Origen (Ley 424-06, Res. 357-05)

## Schema Fichas Merceológicas — Campos Faltantes
Campos actuales: Producto, Clasificación, SON Sugerido, Materia, Función, Uso
Campos por agregar: DAI%, ITBIS%, RGI Aplicable, Capítulo SA, Sección SA, Notas Legales, Base Legal, Estado, Fecha clasificación
