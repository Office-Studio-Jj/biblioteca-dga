---
name: cargar-fuente-legal
description: Carga una norma oficial de República Dominicana (ley, decreto, reglamento, resolución DGII/DGA) a la biblioteca-dga. Úsala cuando el usuario sube o pide integrar un PDF legal a Notion: extrae con pdfplumber, coteja con el Arancel (Capa 1), publica en el cuaderno correcto y registra en CLOPAS.
---

# Cargar una fuente legal oficial

Solo fuentes oficiales de RD. Nunca redactar ni inventar artículos: se transcriben o se citan con su número.

## 1. Obtener el PDF
1. Primero la biblioteca del usuario: Google Drive (`search_files` por título o `fullText`).
   - PDF grande: `download_file_content` → el resultado queda en un archivo JSON; decodificar `content` (base64) con Python.
   - Archivo subido al chat: `/root/.claude/uploads/...`.
2. Los portales `dgii.gov.do`, `aduanas.gob.do` y `consultoria.gob.do` pueden estar bloqueados por la red del entorno. Si lo están, pedir al usuario que suba el PDF a Drive. No usar copias de terceros como fuente.

## 2. Extraer (0% IA)
```python
import pdfplumber
with pdfplumber.open(ruta) as pdf:
    texto = "\n".join((p.extract_text() or "") + f"\n[[pag {i+1}]]" for i, p in enumerate(pdf.pages))
```
- Listar artículos con regex `ART[IÍ]CULO\s*\d+` y leer completos los que aplican a importación y liquidación.
- Tablas: `page.extract_tables()`.
- Anotar el número de la norma, su fecha, la Gaceta Oficial, las modificaciones y las derogaciones (`deroga`).

## 3. Cotejar
- Códigos arancelarios: compararlos con `capa1_sqlite/arancel_rd.db` (`codigos.son`). Un código que existe solo informa; uno que no existe → "requiere correlación del aforador". La app nunca elige la partida (Ley 168-21 Art. 76).
- Tasas: solo con `capa1_sqlite/tasas.py` (`tasas_son`).
- Vigencia: si la norma remite a una ley derogada (p. ej. Ley 3489 → Ley 168-21 Art. 435), anotarlo.
- Fechas de vigencia (resoluciones trimestrales): advertir si ya vencieron.

## 4. Publicar en Notion
- Cuadernos = filas de la BD "📚 Biblioteca online" (`collection://028b7767-c309-47ba-aaeb-2bd89a1c22eb`):
  1 Aforo · 2 Legal y Procedimientos · 3 Regímenes · 4 Nomenclaturas SA · 5 Normas y Origen · 6 VUCERD · 7 Valoración · 8 ISC (Título IV Ley 11-92).
- Agregar una sección nueva (`insert_content`) o una página hija. Formato: fuente única al inicio, tabla con las columnas Tema / Artículo / Qué dispone, y una sección de pendientes.

## 5. Registrar en CLOPAS
- Un registro `Tipo=Creación` con la descripción y lo cargado.
- Un registro `Tipo=Error` por cada discrepancia encontrada (p. ej. app vs norma) o fuente faltante.
- Si la norma vence o se indexa periódicamente: crear el evento en Google Calendar y un registro `[AGENDA]` (Tags=Agenda, ¿Fue realizado?=Pendiente, Próxima agenda, Evento Calendar).
