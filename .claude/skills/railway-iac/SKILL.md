---
name: railway-iac
description: Cambios en la configuración del servicio Railway de biblioteca-dga (.railway/railway.ts, Infrastructure as Code). Úsala antes de tocar railway.ts, cuando el usuario corre railway config plan/apply, o cuando falla la CLI de Railway en Windows.
---

# Railway IaC — biblioteca-dga

Proyecto `invigorating-optimism`, entorno `production`, servicio `biblioteca-dga`. La configuración vive en `.railway/railway.ts`; `railway.toml` se retiró el 01-10-2026.

## Reglas
1. **Siempre `railway config plan` antes de `railway config apply`.** El usuario corre ambos en PowerShell y manda captura.
2. **No aplicar si el plan muestra `destroy > 0`**, `Delete variable`, `source.repo → null` o cambios en `biblioteca-dga-volume`. Corregir railway.ts primero.
3. railway.ts debe declarar siempre:
   - `source: github("Office-Studio-Jj/biblioteca-dga", { branch: "main" })` (sin esto se pierde el auto-deploy).
   - Variables que IaC administra con `preserve()` (hoy `ANTHROPIC_API_KEY`, `NOTION_DB_CLOPAS`). Nunca escribir valores de claves.
   - `volumeMounts: { "/data": volume("biblioteca-dga-volume", { region: "us-west2", sizeMB: 5000 }) }` (usuarios y contraseñas, Ley 172-13).
4. Validar localmente antes de subir: importar el archivo con `node --experimental-strip-types` y el paquete `railway` (versión de package.json) y revisar el JSON generado.
5. El merge a main despliega la app, pero **no** aplica la configuración: eso solo lo hace `railway config apply`.

## Windows (laptop del usuario)
- Requiere Railway CLI ≥ 5.42.1: `npm install -g @railway/cli@latest`.
- Error "This version of railway/iac requires Railway CLI 5.42.1 or newer" con la CLI ya actualizada: el SDK no puede ejecutar `railway.cmd`. En la misma ventana:
  ```
  $env:_ = "$env:APPDATA\npm\node_modules\@railway\cli\bin\railway.exe"
  ```
- "The Railway TypeScript SDK is not installed": `npm install` en la carpeta del repo.
- `git pull` con "Could not resolve host": problema de red del usuario; el plan usará el archivo viejo.

## Después de aplicar
Correr el workflow "Verificar produccion" y actualizar CLOPAS.
