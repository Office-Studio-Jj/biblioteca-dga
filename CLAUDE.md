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

## Marco Legal Corregido (Informe CEO 04-05-2026)
- Ley 5-23 = Comercio Marítimo (NO "Derecho Marítimo")
- Ley 200-04 = Libre Acceso Info Pública (NO Gobierno Electrónico, NO aplica a app)
- Ley 126-02 = base legal real de VUCERD y trámites digitales
- Ley 14-93 = arancel originario, superada por Ley 168-21 Cap. III en clasificación
- Agregar: Ley 146-00 (DAI vigente), Ley 172-13 (protección datos)
- Eliminar: Ley 200-04 y Ley 10-07 del marco normativo de la app

## BDs Notion Pendientes
- BD-Valoración (Ley 168-21 Cap. VI, Acuerdo OMC Art. VII)
- BD-Regímenes (Ley 168-21 Cap. V, Ley 8-90)
- BD-VUCERD (Ley 126-02, Ley 168-21 Arts. 15-17)
- BD-Origen (Ley 424-06, Res. 357-05)

## Schema Fichas Merceológicas — Campos Faltantes
Campos actuales: Producto, Clasificación, SON Sugerido, Materia, Función, Uso
Campos por agregar: DAI%, ITBIS%, RGI Aplicable, Capítulo SA, Sección SA, Notas Legales, Base Legal, Estado, Fecha clasificación
