#!/usr/bin/env bash
# Devuelve a almacen_fp el acceso por IP/localhost en el puerto 80.
#
# Al pasar el default_server al catch-all, el bloque de almacen_fp se quedo con
# `server_name _`, que no casa con ningun Host real: solo recibia trafico por ser
# el servidor por defecto. Resultado: Host 172.23.120.210, localhost y 127.0.0.1
# -los tres que estan en ALLOWED_HOSTS de Django- pasaron a recibir 444.
#
# Se le ponen los nombres explicitos, que es tambien lo que quita el aviso
# "conflicting server name _ on 0.0.0.0:80, ignored".
#
# No se anade 192.168.68.105 a proposito: no esta en ALLOWED_HOSTS, asi que
# Django ya respondia 400 a ese Host antes de todo esto.
#
# Uso: sudo ./nginx/arreglar-almacen-servername.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecutalo con sudo." >&2; exit 1; }

SITE=/etc/nginx/sites-available/almacen_fp
BACKUP="${SITE}.bak-servername-$(date +%Y%m%d-%H%M%S)"
NOMBRES='172.23.120.210 127.0.0.1 localhost'

grep -qE '^\s*server_name\s+_\s*;' "$SITE" || {
  echo "No encuentro 'server_name _;' en $SITE; no toco nada." >&2; exit 1; }

revertir() {
  echo "!! fallo: revirtiendo" >&2
  cp -p "$BACKUP" "$SITE"
  nginx -t >/dev/null 2>&1 && echo "   restaurado y valido." >&2 \
    || echo "   ATENCION: nginx -t sigue fallando. Revisa $SITE" >&2
}
trap revertir ERR

cp -p "$SITE" "$BACKUP"
echo "== respaldo -> $BACKUP =="

# Solo la primera aparicion: es la del bloque :80 que era default_server.
sed -i -E "0,/^(\s*)server_name\s+_\s*;/s//\1server_name ${NOMBRES};/" "$SITE"
grep -nE '^\s*(listen|server_name)' "$SITE" | head -6 | sed 's/^/   /'

echo "== nginx -t =="
nginx -t
trap - ERR

echo "== recargando =="
systemctl reload nginx
sleep 1

echo "== comprobacion =="
for h in 172.23.120.210 localhost 127.0.0.1 fp.santiagoapostol.net bogus.example; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 -H "Host: $h" http://127.0.0.1/ 2>/dev/null)
  [[ -z $c || $c == 000 ]] && c="CORTADA (444)"
  printf '   Host: %-24s -> %s\n' "$h" "$c"
done
echo "   (bogus.example DEBE seguir cortado; los demas deben responder)"
