#!/usr/bin/env bash
#
# Read-only LAN inventory collector. Runs ON a Proxmox host and prints JSON.
#
# Sweeps the subnet with ICMP to populate the neighbour table, then reads that
# table and probes a fixed list of ports with a hard 1s timeout each. It reads
# only; it changes nothing on any device it touches.
#
# Usage: lan-scan.sh [SUBNET_PREFIX] [BRIDGE]
#   e.g. lan-scan.sh 192.168.4 vmbr0

set -o errexit
set -o nounset
set -o pipefail

SUBNET="${1:-192.168.4}"
BRIDGE="${2:-vmbr0}"
# 2258 is the Synology's relocated DSM Terminal SSH port; without it the scan
# reports the NAS as having no SSH at all.
PORTS="22 80 443 8006 5000 5001 8080 8443 3000 9090 8000 9100 6443 2258"

for i in $(seq 1 254); do
    ping -c1 -W1 "$SUBNET.$i" >/dev/null 2>&1 &
done
wait
sleep 2

self_ip=$(ip -4 -o addr show dev "$BRIDGE" | awk '{print $4}' | cut -d/ -f1)
self_mac=$(cat "/sys/class/net/$BRIDGE/address")

printf '['
first=1
neighbours=$(ip -4 neigh show dev "$BRIDGE" \
    | grep -viE 'failed|incomplete' \
    | awk '{print $1}' \
    | sort -t. -k4 -n)

for ip in $neighbours $self_ip; do
    if [ "$ip" = "$self_ip" ]; then
        mac="$self_mac"
    else
        mac=$(ip -4 neigh show "$ip" dev "$BRIDGE" 2>/dev/null | awk '{print $3}')
    fi
    rdns=$(getent hosts "$ip" 2>/dev/null | awk '{print $2}')
    open=""
    for p in $PORTS; do
        if timeout 1 bash -c "echo > /dev/tcp/$ip/$p" >/dev/null 2>&1; then
            [ -n "$open" ] && open="$open,"
            open="$open$p"
        fi
    done
    [ "$first" -eq 0 ] && printf ','
    printf '{"ip":"%s","mac":"%s","rdns":"%s","open_ports":[%s]}' \
        "$ip" "$(echo "$mac" | tr '[:lower:]' '[:upper:]')" "$rdns" "$open"
    first=0
done
printf ']\n'
