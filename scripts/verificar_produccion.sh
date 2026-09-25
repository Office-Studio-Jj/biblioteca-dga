#!/usr/bin/env bash
# Verifica produccion tras un despliegue: espera a que /health/version muestre el commit
# esperado (EXPECTED_SHA) y reporta el estado de Gemini, SIREVUCE y la arquitectura.
set -u
BASE="${BASE_URL:-https://biblioteca-dga-production.up.railway.app}"
ESPERADO="${EXPECTED_SHA:-}"
fallos=0

echo "== Esperando el commit ${ESPERADO:-(cualquiera)} en $BASE =="
for i in $(seq 1 40); do
  version=$(curl -s -m 30 "$BASE/health/version")
  commit=$(echo "$version" | sed -n 's/.*"commit": *"\([0-9a-f]*\)".*/\1/p')
  if [ -z "$ESPERADO" ] && [ -n "$version" ]; then
    echo "Servicio activo (commit ${commit:-desconocido})"; break
  fi
  if [ -n "$ESPERADO" ] && [ "$commit" = "$ESPERADO" ]; then
    echo "Despliegue del commit $commit activo tras $((i * 15)) s"; break
  fi
  echo "  intento $i: commit desplegado '${commit:-?}'"; sleep 15
  [ "$i" = 40 ] && echo "AVISO: no se vio el commit esperado; se prueba lo que haya desplegado."
done

chequear() {
  local nombre="$1" url="$2" max="$3"
  local t0=$(date +%s)
  local cuerpo code
  cuerpo=$(curl -s -m "$max" -w "\n%{http_code}" "$url")
  code=$(echo "$cuerpo" | tail -1)
  echo
  echo "== $nombre -> HTTP $code en $(( $(date +%s) - t0 )) s =="
  echo "$cuerpo" | sed '$d' | head -c 3000
  echo
  [ "$code" = "200" ] || fallos=$((fallos + 1))
}

chequear "Claude (clave, sin exponerla)" "$BASE/health/claude" 30
chequear "Gemini (merceologia)" "$BASE/health/gemini" 60
chequear "SIREVUCE (Cuaderno 6)" "$BASE/health/sirevuce" 90
chequear "Arquitectura (dron agricola)" "$BASE/health/arquitectura" 180

echo
echo "Endpoints con falla: $fallos"
exit $fallos
