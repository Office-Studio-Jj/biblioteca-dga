# Biblioteca DGA - Instrucciones del Proyecto

## Toolkit Integrado Disponible
- **Humanizer**: Aplicar siempre a texto generado (eliminar patrones IA)
- **UI UX Pro Max**: Usar para mejoras de interfaz y diseno
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
