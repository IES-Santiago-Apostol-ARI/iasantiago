#!/usr/bin/env bash
# Instala la configuracion de fail2ban de este repo en el host. Idempotente.
# Uso: sudo ./fail2ban/instalar.sh
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Ejecutalo con sudo." >&2; exit 1; }
cd "$(dirname "$(readlink -f "$0")")"

if ! command -v fail2ban-client >/dev/null; then
  echo "== instalando fail2ban =="
  apt-get update -qq
  # python3-systemd: la jaula sshd usa backend=systemd y sin el modulo arranca rota.
  apt-get install -y fail2ban python3-systemd
fi

echo "== copiando configuracion =="
install -m 0644 filter.d/nginx-probe.conf /etc/fail2ban/filter.d/nginx-probe.conf
install -m 0644 filter.d/nginx-4xx.conf   /etc/fail2ban/filter.d/nginx-4xx.conf
install -m 0644 jail.local                /etc/fail2ban/jail.local

echo "== validando filtros contra el log real (no se banea nada aun) =="
for jaula in nginx-probe nginx-4xx; do
  echo "--- $jaula ---"
  fail2ban-regex /var/log/nginx/openwebui_access.log \
    "/etc/fail2ban/filter.d/${jaula}.conf" --print-no-missed | tail -20
done

echo
read -rp "Los aciertos de arriba, ¿son solo escaneres? Arrancar fail2ban [s/N]: " ok
[[ ${ok,,} == s ]] || { echo "Abortado; la config queda copiada pero el servicio no se toca."; exit 0; }

systemctl enable --now fail2ban
systemctl reload fail2ban || systemctl restart fail2ban
sleep 3
fail2ban-client status

# Verificacion que falta a proposito en muchas guias: que la jaula este "started"
# no dice nada sobre DE DONDE lee. Con el backend equivocado arranca igual y no
# casa nunca. Aqui se exige que cada jaula de fichero declare su File list.
echo
echo "== comprobando que las jaulas leen ficheros, no el journal =="
fallo=0
for jaula in nginx-probe nginx-4xx recidive; do
  salida=$(fail2ban-client status "$jaula" 2>/dev/null)
  if grep -q 'File list:' <<<"$salida"; then
    printf '   %-12s OK  %s\n' "$jaula" "$(grep 'File list:' <<<"$salida" | sed 's/.*File list:[[:space:]]*//')"
  else
    printf '   %-12s MAL: no lee ficheros (backend equivocado)\n' "$jaula"; fallo=1
  fi
done
if [[ $fallo -eq 1 ]]; then
  echo
  echo "   Revisa 'backend = polling' en [DEFAULT] de jail.local." >&2
  exit 1
fi
echo "== todo correcto =="
