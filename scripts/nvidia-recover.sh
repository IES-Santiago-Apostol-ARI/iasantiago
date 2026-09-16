#!/bin/sh
# Origen: scripts/nvidia-recover.sh en el repo. Se despliega copiado a
# /usr/local/bin por scripts/install-nvidia-fault-handling.sh -- no lo
# edites en /usr/local/bin, se pierde en el siguiente despliegue.
#
# Recover RTX 5090 (0000:02:00.0) from stuck GSP / WPR2-locked state
# without a full reboot. See dmesg for "unexpected WPR2 already up".
#
# Only faults the driver considers resettable are handled here. When the
# driver reports the GPU lost from the bus (Xid 79) or asks for a node reboot
# (Xid 154, recovery action 0x2), a function-level reset cannot help: the
# module unload then hangs against a device that no longer answers. On
# 2026-09-16 that left rmmod spinning at 100% of a core with the modules
# half-unloaded and the display dead -- a plain reboot would have been
# cheaper. So in that case we refuse to run.
#
# Exit codes -- nvidia-monitor.sh branches on them, keep the two in sync:
#   0  GPU is healthy again
#   1  generic failure; retrying may help
#   2  a process still holds /dev/nvidia*; the modules must not be touched
#   3  driver asked for a node reboot; recovery is impossible
#   4  GPU is not on the PCI bus at all
#   5  a module unload hung; module state is unknown, reboot needed
set -e

GPU=0000:02:00.0
GPU_XID=$(echo "$GPU" | sed 's/\.[0-9]*$//')   # 0000:02:00, as Xid lines print it
RMMOD_TIMEOUT=30
REBOOT_MARKER=/run/nvidia-recover.reboot-required

# Test sysfs, not lspci: `lspci -s` exits 0 for a device that is gone, and a
# GPU vanishing from the bus is the very symptom we need to catch.
if [ ! -e "/sys/bus/pci/devices/$GPU" ]; then
    echo "GPU $GPU is not on the PCI bus; only a power cycle brings it back" >&2
    exit 4
fi

# Xid 79 means the card stopped answering on PCIe; Xid 154 action 0x2 is the
# driver saying a node reboot is required. Neither survives an FLR. The
# marker file keeps us refusing once dmesg has rolled over. Note the pattern
# deliberately does not match action 0x1 (GPU Reset Required), which is the
# recoverable GSP timeout this script was written for.
if [ -f "$REBOOT_MARKER" ] || dmesg 2>/dev/null | grep -qE \
    "Xid \($GPU_XID\): 79|Xid \(PCI:$GPU_XID\): 79|GPU has fallen off the bus|recovery action changed from .* to 0x2"
then
    date '+%F %T' > "$REBOOT_MARKER" 2>/dev/null || true
    echo "Driver reports the GPU lost from the bus / node reboot required." >&2
    echo "Refusing to unload the modules: rmmod would hang. Reboot the machine." >&2
    exit 3
fi

# nvidia-persistenced holds /dev/nvidia* even with no compute job running,
# which blocks the rmmod sweep below. Stop it first and restart it on exit
# (any path) so persistence mode resumes once the modules are back.
PERSISTENCED_WAS_ACTIVE=0
if systemctl is-active --quiet nvidia-persistenced; then
    PERSISTENCED_WAS_ACTIVE=1
    trap 'if [ "$PERSISTENCED_WAS_ACTIVE" = 1 ]; then systemctl start nvidia-persistenced >/dev/null 2>&1 || true; fi' EXIT
    systemctl stop nvidia-persistenced
fi

if fuser /dev/nvidia* >/dev/null 2>&1; then
    echo "Something is using /dev/nvidia*. Stop it first:" >&2
    fuser -v /dev/nvidia* >&2
    exit 2
fi

# The timeout bounds this script, not the rmmod: a thread spinning in the
# kernel cannot be signalled away. What it buys is the chance to report the
# hang instead of wedging the caller -- and to stop before the PCI reset and
# the modprobes below make the mess worse.
unload() {
    _mod=$1
    grep -q "^$_mod " /proc/modules || return 0
    _rc=0
    timeout "$RMMOD_TIMEOUT" rmmod "$_mod" 2>/dev/null || _rc=$?
    if [ "$_rc" -eq 124 ]; then
        echo "rmmod $_mod still running after ${RMMOD_TIMEOUT}s; module state is now unknown" >&2
        return 124
    fi
    # As before, a module that refuses to unload for any other reason is tolerated.
    return 0
}

for mod in nvidia_uvm nvidia_drm nvidia_modeset nvidia; do
    if ! unload "$mod"; then
        date '+%F %T' > "$REBOOT_MARKER" 2>/dev/null || true
        exit 5
    fi
done

echo 1 > "/sys/bus/pci/devices/$GPU/reset"

modprobe nvidia
modprobe nvidia_modeset
modprobe nvidia_uvm
modprobe nvidia_drm

# Reloading the modules resets the board to its default power limit, so
# re-apply the cap before anything starts using the card again.
systemctl start --no-block nvidia-power-limit.service >/dev/null 2>&1 || true

nvidia-smi
