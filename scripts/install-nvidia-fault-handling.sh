#!/usr/bin/env bash
# Despliega el manejo de fallos de GPU (post-incidente 2026-09-16, Xid 79).
#
# Reparto copia/enlace, que no es el de despliege.sh por un motivo concreto:
#
#   - Los dos scripts van COPIADOS a /usr/local/bin como root:root 0755. Los
#     lanza /etc/cron.d/nvidia-monitor como root cada minuto; un enlace a un
#     fichero del repo (ari:ari) convertiria cualquier escritura en el repo en
#     ejecucion como root una vez por minuto.
#   - La unit va ENLAZADA, como las demas units en despliege.sh.
#   - Los /etc/default/* se copian del .example y NUNCA se pisan: ahi acaban
#     topics de ntfy o direcciones de correo, que no deben volver al repo.
#
# Idempotente. Ejecutar como root.
set -euo pipefail

BASE=${BASE:-/opt/iasantiago-rag}
STAMP=$(date +%Y%m%d-%H%M%S)

[ "$(id -u)" -eq 0 ] || { echo "ejecutame como root (sudo $0)" >&2; exit 1; }
[ -d "$BASE/scripts" ] || { echo "no encuentro $BASE" >&2; exit 1; }

echo "== copia de seguridad de los scripts actuales"
for f in /usr/local/bin/nvidia-recover.sh /usr/local/bin/nvidia-monitor.sh; do
    if [ -f "$f" ] && ! cmp -s "$f" "$BASE/scripts/$(basename "$f")"; then
        cp -a "$f" "$f.bak-$STAMP"
        echo "   $f.bak-$STAMP"
    fi
done

echo "== scripts -> /usr/local/bin (copia, root:root 0755)"
install -m 0755 -o root -g root "$BASE/scripts/nvidia-recover.sh" /usr/local/bin/nvidia-recover.sh
install -m 0755 -o root -g root "$BASE/scripts/nvidia-monitor.sh" /usr/local/bin/nvidia-monitor.sh

echo "== unit -> /etc/systemd/system (enlace)"
ln -sf "$BASE/systemd/nvidia-power-limit.service" /etc/systemd/system/nvidia-power-limit.service

echo "== /etc/default (copia del .example, sin pisar)"
for n in nvidia-power-limit nvidia-monitor; do
    if [ -f "/etc/default/$n" ]; then
        echo "   /etc/default/$n ya existe, lo dejo"
    else
        install -m 0644 -o root -g root "$BASE/systemd/$n.default.example" "/etc/default/$n"
        echo "   /etc/default/$n"
    fi
done

echo "== units"
systemctl daemon-reload
systemctl enable --now nvidia-power-limit.service
# Ya estaba escrito y con logrotate puesto, solo apagado desde mayo: muestras
# cada 30s de potencia, temperatura y relojes, para que el proximo fallo tenga
# una linea temporal en vez de una conjetura.
systemctl enable --now nvidia-sampler.service

echo
echo "== resultado"
nvidia-smi --query-gpu=power.limit,power.default_limit,power.draw --format=csv
systemctl is-active nvidia-power-limit.service nvidia-sampler.service
echo "muestreo en /var/log/nvidia-monitor/gpu-sample.csv"
