# Restricción de Alcance Geográfico

**Orden CEO 05-05-2026 — Sección 3.4**

---

## Declaración Formal

Este sistema clasifica mercancías **EXCLUSIVAMENTE** conforme al Arancel de Aduanas de la República Dominicana (8 dígitos SON).

**NO es compatible con:**
- Nomenclaturas de otros países
- NALADISA (ALADI)
- Nomenclatura Andina (NANDINA)
- CAUCA/RECAUCA centroamericano
- Arancel Externo Común del MERCOSUR
- Combined Nomenclature (CN) de la Unión Europea
- Harmonized Tariff Schedule (HTS) de Estados Unidos
- Cualquier otra nomenclatura nacional o regional

---

## Mensaje de Rechazo Estandarizado

Cuando se detecte solicitud de clasificación bajo otra nomenclatura:

> "Este sistema opera exclusivamente bajo la nomenclatura arancelaria de la República Dominicana conforme a la Ley 14-93 y el Decreto 36-22. No clasifica bajo nomenclaturas de otros países o acuerdos regionales."

---

## Detección

El sistema rechaza automáticamente cuando:
- Código tiene más de 8 dígitos (10 dígitos = otra nomenclatura)
- Usuario menciona explícitamente otro país
- Formato no coincide con `XXXX.XX.XX` o `XXXX.XX.XX.XX`
- Se solicita clasificación bajo NALADISA, NANDINA, HTS, CN, etc.

---

## Alcance Positivo

El sistema SÍ cubre:
- 7,616 códigos SON del Arancel Nacional (Decreto 36-22, 7ma Enmienda SA)
- 21 Secciones, 97 Capítulos, 1,224 Partidas del SA
- Preferencias DR-CAFTA (Ley 424-06) — aplicadas SOBRE la clasificación RD
- Zonas Francas (Ley 226-06) — modifican tributos post-clasificación
- Todos los regímenes de Ley 168-21 Arts. 118-180

---

**Base legal:** Ley 14-93 (Arancel originario), Decreto 36-22 (7ma Enmienda), Ley 168-21 Cap. III (clasificación).
