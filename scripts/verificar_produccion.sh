#!/usr/bin/env bash
# Verifica produccion tras un despliegue: espera a que exista /health/sirevuce (codigo nuevo)
# y reporta el estado de Gemini, SIREVUCE y la arquitectura de clasificacion.
set -u
BASE="${BASE_URL:-https://biblioteca-dga-production.up.railway.app}"
fallos=0

echo "== Esperando el despliegue nuevo en $BASE =="
for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 30 "$BASE/health/sirevuce")
  if [ "$code" != "404" ] && [ "$code" != "000" ] && [ "$code" != "502" ]; then
    echo "Despliegue nuevo activo (HTTP $code) tras $((i * 15)) s"; break
  fi
  echo "  intento $i: HTTP $code"; sleep 15
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

chequear "Gemini (merceologia)" "$BASE/health/gemini" 60
chequear "SIREVUCE (Cuaderno 6)" "$BASE/health/sirevuce" 90
chequear "Arquitectura (dron agricola)" "$BASE/health/arquitectura" 180

echo
echo "Endpoints con falla: $fallos"
exit $fallos
