#!/usr/bin/env bash
# Instala el servidor por defecto (nginx/catchall.conf) y quita el default_server
# que almacen_fp tenia en el puerto 80.
#
# Los dos cambios van juntos a la fuerza: nginx aborta con "a duplicate default
# server" si ambos bloques lo reclaman, asi que aplicar solo uno deja nginx sin
# poder arrancar. Si `nginx -t` falla se revierte todo y no se recarga nada.
#
# Uso: sudo ./nginx/instalar-catchall.sh
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Ejecutalo con sudo." >&2; exit 1; }

SITE=/etc/nginx/sites-available/almacen_fp
LINK=/etc/nginx/sites-enabled/000-catchall
SRC=/opt/iasantiago-rag/nginx/catchall.conf
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="${SITE}.bak-precatchall-${STAMP}"

[[ -f $SRC  ]] || { echo "Falta $SRC" >&2; exit 1; }
[[ -f $SITE ]] || { echo "Falta $SITE" >&2; exit 1; }
# El certificado del catch-all NO esta en git: nginx/certs/ va en .gitignore,
# que es lo correcto para una clave privada. Pero catchall.conf si esta, asi que
# un checkout limpio se quedaba con un nginx que no arranca por un fichero que
# no existe y cuyo comando de creacion no estaba escrito en ninguna parte. Se
# genera aqui si falta.
#
# No importa que sea autofirmado ni el nombre que lleve: este bloque no responde
# nada (444), asi que lo correcto es justamente que el handshake no valide. Por
# eso CN=invalid y no el nombre de ningun servicio real.
CERTDIR=/opt/iasantiago-rag/nginx/certs
CRT="$CERTDIR/catchall.crt"
KEY="$CERTDIR/catchall.key"

huella() { # huella de la clave publica, para saber si crt y key son pareja
  case $1 in
    *.crt) openssl x509 -in "$1" -noout -pubkey 2>/dev/null | openssl md5 ;;
    *)     openssl pkey -in "$1" -pubout   2>/dev/null | openssl md5 ;;
  esac
}

if [[ ! -f $CRT || ! -f $KEY ]]; then
  echo "== generando el certificado del catch-all (falta) =="
  mkdir -p "$CERTDIR"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout "$KEY" -out "$CRT" -days 3650 -subj '/CN=invalid' 2>/dev/null
  # El script corre como root; devolver la pareja al dueno del repo para que se
  # pueda gestionar sin sudo, igual que el resto de nginx/certs/.
  DUENO=$(stat -c '%U:%G' /opt/iasantiago-rag)
  chown "$DUENO" "$CRT" "$KEY"
  chmod 600 "$KEY"; chmod 644 "$CRT"
  openssl x509 -in "$CRT" -noout -subject -dates | sed 's/^/   /'
else
  echo "== certificado del catch-all ya presente =="
fi

# Una pareja que no case hace que nginx no arranque, con un error poco
# evidente. Mejor detectarlo aqui que en el reload.
[[ $(huella "$CRT") == $(huella "$KEY") ]] || {
  echo "El certificado y la clave de $CERTDIR no son pareja. Borra ambos y vuelve a ejecutar." >&2
  exit 1; }

revertir() {
  echo "!! fallo: revirtiendo" >&2
  [[ -f $BACKUP ]] && cp -p "$BACKUP" "$SITE"
  rm -f "$LINK"
  if nginx -t >/dev/null 2>&1; then
    echo "   configuracion previa restaurada y valida; nginx sigue como estaba." >&2
  else
    echo "   ATENCION: nginx -t sigue fallando tras revertir. Revisa $SITE" >&2
  fi
}
trap revertir ERR

echo "== respaldo de almacen_fp -> $BACKUP =="
cp -p "$SITE" "$BACKUP"

echo "== quitando default_server del puerto 80 de almacen_fp =="
if grep -qE '^\s*listen\s+80\s+default_server\s*;' "$SITE"; then
  sed -i -E 's/^(\s*listen\s+80)\s+default_server\s*;/\1;  # default_server movido a nginx\/catchall.conf/' "$SITE"
  grep -nE '^\s*listen\s+80' "$SITE" | sed 's/^/   /'
else
  echo "   ya no lo tenia; sigo."
fi

echo "== enlazando el servidor por defecto =="
# Symlink al repo, igual que /etc/nginx/nginx.conf, para que no haya dos copias
# que se separen con el tiempo.
ln -sfn "$SRC" "$LINK"
ls -l "$LINK" | sed 's/^/   /'

echo "== nginx -t =="
nginx -t
trap - ERR

echo "== recargando =="
systemctl reload nginx
sleep 1

echo "== comprobacion en caliente =="
printf '   SNI inventado -> cert: '
echo | openssl s_client -connect 127.0.0.1:443 -servername bogus.example 2>/dev/null \
  | openssl x509 -noout -subject 2>/dev/null || echo "(handshake cortado)"
printf '   SNI de la IA  -> cert: '
echo | openssl s_client -connect 127.0.0.1:443 -servername ia.santiagoapostol.net 2>/dev/null \
  | openssl x509 -noout -subject 2>/dev/null
printf '   HTTP Host desconocido -> %s\n' \
  "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 -H 'Host: bogus.example' http://127.0.0.1/ || echo 'conexion cortada (444)')"
printf '   HTTP Host fp (ALLOWED_HOSTS intacto) -> %s\n' \
  "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 -H 'Host: fp.santiagoapostol.net' http://127.0.0.1/)"
echo "== hecho =="
