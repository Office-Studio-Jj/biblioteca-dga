# Revisión de tasas del Arancel (Capa 1) — 01-10-2026

Fuente única: **Arancel 7ma Enmienda (Decreto 36-22)**. Las tasas se leen por posición de columna
(`capa1_sqlite/extraer_tasas_pdf.py` → `tasas_arancel_pdf.json`, pdfplumber, 0% IA) y
`build_arancel_db.py` las carga en `arancel_rd.db` en cada despliegue.

## Qué se corrigió

| Problema | Efecto | Ejemplo |
|---|---|---|
| El texto del cache termina en "GRAV. EX.ITBIS" (`40 0`) y se tomaba el último número como DAI | 331 SON con DAI 0 o errado | Carne bovina 0201.10.00: 40% en el PDF, 0% en la base |
| Filas de varias líneas: la tasa quedaba corrida a la fila de abajo | DAI de la fila vecina | 8524.99.11: 0% en el PDF, 20% en la base |
| 103 SON del PDF no estaban en la base | "Código inexistente" | 8524.91.11 a .17 y 8524.92.11 (pantallas), 2309.90.xx, 3306.xx, 3827.xx |
| ITBIS por regla de capítulo, no por la columna EX. ITBIS | 902 SON con ITBIS distinto al Arancel | Cordero 0204.10.00: el Arancel no lo exime (18%); la regla lo daba EXENTO |
| `correcciones_manuales.json` no se aplicaba en la construcción (se buscaba el SON en el nivel superior del JSON) | La corrección humana de 8543.70.00 no regía | Ahora `fuente = manual` |

Comprobado contra la imagen del PDF: págs. 37-38, 67, 537-538 (`tests/test_tasas_arancel.py`).
La lectura por columna coincide con la lectura del texto en 7490 de 7525 SON comparables; las 35
diferencias son números de la descripción ("Capítulo 87", "Brix") que el texto confunde con la tasa.

ITBIS: la columna **EX. ITBIS** marcada (`0`) se carga como EXENTO; vacía, 18% (Ley 253-12).
Las exenciones que dependan del uso (p. ej. Ley 150-97, uso agropecuario) se acreditan aparte.

## Pendiente de revisión humana (11 SON)

La columna GRAV. no se pudo leer con certeza: se mantiene el valor anterior de la base y no se
modifica sin verificación (regla de prelación: escalar a humano).

| SON | Pág. PDF | Lectura | En la base (DAI / ITBIS) |
|---|---|---|---|
| 0806.20.00 | 75 | sin tasa | 20 / EXENTO |
| 0810.90.11 | 75 | sin tasa | 0 / EXENTO |
| 1504.10.29 | 96 | sin tasa | vacío / 18 |
| 1504.20.90 | 96 | sin tasa | 0 / 18 |
| 1504.30.90 | 96 | sin tasa | 0 / 18 |
| 3301.90.90 | 209 | "00" | 0 / 18 |
| 3404.90.90 | 631 | "27" (no es tasa oficial) | 8 / 18 |
| 3914.00.00 | 245 | sin tasa | 0 / 18 |
| 5606.00.00 | 338 | sin tasa | 0 / 18 |
| 5609.00.00 | 339 | sin tasa | 20 / 18 |
| 7323.94.90 | 441 | sin tasa | no está en la base |

## Otros hallazgos (no corregidos en este cambio)

- `sinonimos_arancelarios` (semilla en `build_arancel_db.py`) lleva "pantalla celular" a
  **8517.79.00**, mientras el contexto legal de Claude aplica la **partida 85.24** para módulos de
  visualización de pantalla plana (Nota 7 del Cap. 85). Es una decisión de clasificación: requiere
  validación del responsable legal antes de cambiar la semilla.
- `orquestador_consulta_v2._son_exacto_db` consulta columnas `dai_pct`, `itbis_pct`, `isc_pct`,
  `permisos`, `notas_legales` que `build_arancel_db.py` no crea; en producción esa lectura falla y
  el flujo sigue por `pipeline_3_capas`.
- Algunas descripciones del cache arrastran texto repetido ("-En -En canales…"); no afecta tasas.
