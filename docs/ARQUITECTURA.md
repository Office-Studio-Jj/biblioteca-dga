# Arquitectura biblioteca-dga / app móvil (25-09-2026)

## Principio rector
**Gemini solo informa; Claude, con la biblioteca-dga, decide.** Ningún capítulo, partida, SON, tasa o base legal sale de Gemini. La existencia de un código en la biblioteca solo informa: nunca elige ni sustituye una clasificación.

## Flujo de una consulta de clasificación (Nomenclaturas)

| Paso | Quién | Qué hace | Límite |
|---|---|---|---|
| 1 | Gemini (`sub_agentes/merceologia_gemini.py`) | Ficha merceológica: origen, composición, función, uso, presentación, criterio que prevalece. Se eliminan de la salida los códigos que cuele | 8 s (`MERCEOLOGIA_TIMEOUT_S`), caché de 500 fichas; si tarda, se sigue sin ficha |
| 2 | Biblioteca-dga (`arancel_rd.db`, `partidas_arancel.json`) | Propone capítulos candidatos por coincidencia con el texto de las partidas (RGI 1) y con las descripciones de los SON | ~50 ms |
| 3 | Biblioteca-dga (`sub_agentes/contexto_legal.py`) | Arma el contexto legal: RGI, Notas de Sección y de Capítulo, texto de las partidas, aperturas nacionales (SON de 8 dígitos con DAI/ITBIS/ISC) y base legal | ~10 ms |
| 4 | Claude (`sub_agentes/arbitro_claude.py`, `claude-opus-5`) | Decide capítulo, partida y SON aplicando las RGI en orden (1, luego 2-5, luego 6). La partida debe existir en la biblioteca. Sin Claude, no hay clasificación | 45-50 s |
| 5 | Claude + web oficial | Solo si la biblioteca no contiene el dato: consulta sitios oficiales de instituciones dominicanas (máx. 2 búsquedas y 2 lecturas), cita la URL, y la web nunca contradice a la biblioteca | incluido en el paso 4 |
| 6 | Verificador y Supervisor (Python) | Confirman existencia y tasas en `arancel_rd.db`. Un código inexistente queda **NO DETERMINADA** con las alternativas listadas, sin seleccionar | ms |

Dominios web autorizados (solo Claude): aduanas.gob.do (incluye sirevuce), vucerd.gob.do, dgii.gov.do, hacienda.gob.do, consultoria.gov.do, camaradediputados.gob.do, senadord.gob.do, tc.gob.do, poderjudicial.gob.do, msp.gob.do, agricultura.gob.do, indotel.gob.do, micm.gob.do, cnzfe.gob.do, proindustria.gob.do, ambiente.gob.do, indocal.gob.do, prodominicana.gob.do, mirex.gob.do.

## Cuaderno 6 — VUCERD
- `sub_agentes/consultor_sirevuce.py` consulta en paralelo el portal oficial **SIREVUCE** (sirevuce.aduanas.gob.do) por SON o palabras clave y antepone el resultado: si lleva o no VUCE, formulario, organismo, costo, documentos y certificado fitosanitario.
- Si el portal no responde: **NO VERIFICADO**, nunca "no requiere".
- La app móvil muestra el recuadro "Verificación oficial SIREVUCE (DGA)".
- Endpoints: `/api/sirevuce?q=` (con sesión) y `/health/sirevuce` (código fijo 9022.90.10).

## CLOPAS (Notion)
- Base "📚 Biblioteca online" (`NOTION_DB_CLOPAS`), 13 propiedades, vistas "Biblioteca de Errores" y "Pendientes".
- Registro automático (`sub_agentes/clopas_auto.py`): cada SON verificado en SIREVUCE (sin duplicados), cambios oficiales como **Corrección**, fallas del portal o del lector como **Error** (máximo uno por día).
- Solo datos oficiales; nunca la pregunta ni el usuario (Ley 172-13).

## Fuentes de verdad
- `capa1_sqlite/arancel_rd.db`: 7,616 SON (Arancel 7ma Enmienda, Decreto 36-22), extraídos con pdfplumber (0 % IA).
- `notebooklm_skill/data/fuentes_nomenclatura/partidas_arancel.json`: 1,149 textos de partida (`capa1_sqlite/build_partidas.py`).
- Notas de Sección y de Capítulo: `sub_agentes/lector_notas_arancel.py`.

## Variables de entorno (Railway)
`ANTHROPIC_API_KEY` (obligatoria: Claude decide y redacta), `GEMINI_API_KEY` (opcional: ficha merceológica), `NOTION_API_KEY` y `NOTION_DB_CLOPAS` (CLOPAS), `ARBITRO_CLAUDE_MODEL`, `MERCEOLOGIA_TIMEOUT_S`, `CLOPAS_AUTO=0` para desactivar el registro automático.
