#!/usr/bin/env bash
# Muestra el HTML real de SIREVUCE (búsqueda y detalle) para ajustar el lector.
set -u
B="https://sirevuce.aduanas.gob.do"
UA="Mozilla/5.0 (biblioteca-dga; consulta SIREVUCE)"

mostrar() {
  echo; echo "===== $1 ====="
  curl -s -m 30 -A "$UA" -D - "$2" -o /tmp/pagina.html | head -15
  echo "--- tamaño: $(wc -c < /tmp/pagina.html) bytes; formularios y enlaces:"
  grep -o -i -E '<form[^>]*>|<input[^>]*>|<select[^>]*>|<option[^>]*>[^<]{0,40}|href="[^"]*"' /tmp/pagina.html | head -60
  echo "--- cuerpo (sin scripts ni estilos):"
  sed -e 's/<script[^>]*>.*<\/script>//g' -e 's/<style[^>]*>.*<\/style>//g' /tmp/pagina.html | tr -s ' \n' | head -c 30000
  echo
}

mostrar "Descripción: pantalla" "$B/Home/Report?TagIdSelect2=pantalla&Trades=1"
mostrar "Código por inputArancel" "$B/Home/Report?inputArancel=90229010&Trades=1"
mostrar "Detalle 7268 (9022.90.10)" "$B/Home/Details/7268?Trades=1"
exit 0
