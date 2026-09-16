#!/bin/bash
# nvidia-monitor.sh
# Origen: scripts/nvidia-monitor.sh en el repo. Se despliega copiado a
# /usr/local/bin por scripts/install-nvidia-fault-handling.sh -- no lo
# edites en /usr/local/bin, se pierde en el siguiente despliegue.
#
# Detects GPU faults via nvidia-smi and recovers by stopping llama-server,
# running nvidia-recover.sh, and restarting the service. Captures a
# diagnostic snapshot for later analysis.
#
# Not every fault is recoverable. When the driver reports the GPU lost from
# the bus (Xid 79) or asks for a node reboot (Xid 154 action 0x2), unloading
# the modules hangs against a dead device. On 2026-09-16 two recover runs
# were refused because nvtop held /dev/nvidia*, this script read the two
# non-zero exits as "try harder", and the third run wedged rmmod at 100% CPU
# with the modules half-unloaded. Hence: ask the verdict before touching
# anything, branch on why a run failed, and treat "blocked" as stop rather
# than as retry.
#
# Run as root via cron.

set -u

SERVICE=llama-server
RECOVER=/usr/local/bin/nvidia-recover.sh
LOG_DIR=/var/log/nvidia-monitor
LOG=$LOG_DIR/monitor.log
LOCK=/run/nvidia-monitor.lock
GPU_XID=0000:02:00
MAX_ATTEMPTS=3

# Optional NVIDIA_MONITOR_NOTIFY_CMD: a command that gets the message on
# stdin (ntfy, a mail command, a webhook -- whatever you wire up).
[ -r /etc/default/nvidia-monitor ] && . /etc/default/nvidia-monitor

mkdir -p "$LOG_DIR"

ts() { date '+%F %T'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" >> "$LOG"; }

# Loud by every channel that needs no extra package installed: the log, the
# journal, any open terminal, and the motd on next login.
notify() {
    log "$*"
    logger -p daemon.alert -t nvidia-monitor "$*" 2>/dev/null || true
    printf 'nvidia-monitor: %s\n' "$*" | wall 2>/dev/null || true
    if [ -n "${NVIDIA_MONITOR_NOTIFY_CMD:-}" ]; then
        printf 'nvidia-monitor: %s\n' "$*" | sh -c "$NVIDIA_MONITOR_NOTIFY_CMD" >> "$LOG" 2>&1 \
            || log "WARN: NVIDIA_MONITOR_NOTIFY_CMD failed"
    fi
}

# /var/run/reboot-required is what Ubuntu's 98-reboot-required motd hook reads.
flag_reboot_required() {
    printf '*** System restart required: NVIDIA driver reported the GPU lost from the bus ***\n' \
        > /var/run/reboot-required 2>/dev/null || true
}

# Same verdict nvidia-recover.sh applies, checked here so we can bail out
# before stopping services or touching the modules.
node_reboot_required() {
    dmesg 2>/dev/null | grep -qE \
        "Xid \($GPU_XID\): 79|Xid \(PCI:$GPU_XID\): 79|GPU has fallen off the bus|recovery action changed from .* to 0x2"
}

# Single-instance lock so cron cannot stack runs while we recover.
exec 9>"$LOCK"
flock -n 9 || exit 0

probe() {
    # 0 = healthy, 1 = faulty
    local out rc
    out=$(timeout 15 nvidia-smi 2>&1)
    rc=$?
    if [ $rc -ne 0 ]; then
        printf '%s\n' "$out"
        return 1
    fi
    if printf '%s' "$out" | grep -q 'ERR!'; then
        printf '%s\n' "$out"
        return 1
    fi
    return 0
}

if out=$(probe); then
    exit 0
fi

log "GPU fault detected. nvidia-smi output:"
printf '%s\n' "$out" >> "$LOG"

# Diagnostic snapshot -- written before we touch anything so the post-mortem
# is not contaminated by the recovery itself.
DIAG=$LOG_DIR/diag-$(date +%Y%m%d-%H%M%S)
mkdir -p "$DIAG"
nvidia-smi                                  > "$DIAG/nvidia-smi.txt"           2>&1 || true
nvidia-smi -q                               > "$DIAG/nvidia-smi-query.txt"     2>&1 || true
dmesg -T | tail -500                        > "$DIAG/dmesg.txt"                2>&1 || true
journalctl -u "$SERVICE" -n 500 --no-pager  > "$DIAG/journal.txt"              2>&1 || true
cp -a /var/log/llama-server                   "$DIAG/llama-server-logs"          2>/dev/null || true
lsmod | grep -i nvidia                      > "$DIAG/lsmod.txt"                2>&1 || true
log "Diagnostic snapshot saved at $DIAG"

# Ask first. Stopping the service and unloading modules is pointless once the
# driver has declared the card lost, and unloading them is actively harmful.
if node_reboot_required; then
    notify "GPU lost from the bus -- the driver requires a node reboot. Nothing was touched; $SERVICE left as it is. Snapshot: $DIAG. Reboot the machine."
    flag_reboot_required
    exit 3
fi

log "Stopping $SERVICE"
systemctl stop "$SERVICE" >> "$LOG" 2>&1 || log "WARN: stop returned non-zero"
sleep 2

# The GSP/WPR2 fault this script was written for often needs more than one
# run, so a generic failure is retried. Every other exit code names a
# specific reason to stop -- escalating past those is what caused the
# 2026-09-16 hang.
attempt=0
rc=0
while [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
    attempt=$((attempt + 1))
    log "nvidia-recover.sh run #$attempt"
    rc=0
    "$RECOVER" >> "$LOG" 2>&1 || rc=$?
    case $rc in
        0)
            log "nvidia-recover.sh run #$attempt exited 0"
            break
            ;;
        2)
            notify "GPU is faulty but a process still holds /dev/nvidia* (see $LOG for which). Modules untouched. Close it, then run $RECOVER by hand."
            exit 2
            ;;
        3)
            notify "GPU lost from the bus -- the driver requires a node reboot. Recovery is impossible. Snapshot: $DIAG. Reboot the machine."
            flag_reboot_required
            exit 3
            ;;
        4)
            notify "GPU has disappeared from the PCI bus entirely. Snapshot: $DIAG. Power-cycle the machine."
            flag_reboot_required
            exit 4
            ;;
        5)
            notify "A module unload hung; the NVIDIA modules are in an unknown state and will not come back. Snapshot: $DIAG. Reboot the machine."
            flag_reboot_required
            exit 5
            ;;
        *)
            log "nvidia-recover.sh run #$attempt exited $rc"
            sleep 2
            ;;
    esac
done

if out=$(probe); then
    log "GPU recovered after $attempt run(s)."
else
    notify "GPU still faulty after $attempt recovery run(s). NOT restarting $SERVICE. Snapshot: $DIAG."
    printf '%s\n' "$out" >> "$LOG"
    exit 1
fi

log "Starting $SERVICE"
systemctl start "$SERVICE" >> "$LOG" 2>&1
log "Recovery complete."
