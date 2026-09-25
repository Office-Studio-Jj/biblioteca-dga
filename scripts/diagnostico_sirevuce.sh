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
  sed -e 's/<script[^>]*>.*<\/script>//g' -e 's/<style[^>]*>.*<\/style>//g' /tmp/pagina.html | tr -s ' \n' | head -c 6000
  echo
}

mostrar "Inicio" "$B/"
mostrar "Descripción: pantalla" "$B/Home/Report?TagIdSelect2=pantalla&Trades=1"
mostrar "Código por TagIdSelect" "$B/Home/Report?TagIdSelect=90229010&Trades=1"
mostrar "Código por TagIdSelect2" "$B/Home/Report?TagIdSelect2=90229010&Trades=1"
ver=$(curl -s -m 30 -A "$UA" "$B/Home/Report?TagIdSelect2=pantalla&Trades=1" | grep -o -E 'href="[^"]*"' | grep -v -i -E 'Report|onChange|\.css|\.js|#|Language|lang' | head -1 | sed 's/href="//; s/"$//; s/&amp;/\&/g')
echo "Primer enlace de detalle: $ver"
[ -n "$ver" ] && mostrar "Detalle" "$B${ver#"$B"}"
exit 0
