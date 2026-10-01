#!/bin/sh
# Restrict Docker-published web ports to the IPv4 LAN. Docker evaluates this
# chain before its own forwarding rules, avoiding the usual UFW bypass.
set -eu

iptables_cmd=/usr/sbin/iptables
filter_chain=HOMELAB-INGRESS

"${iptables_cmd}" -w -N "${filter_chain}" 2>/dev/null || true
"${iptables_cmd}" -w -F "${filter_chain}"

if ! "${iptables_cmd}" -w -C DOCKER-USER -j "${filter_chain}" 2>/dev/null; then
  "${iptables_cmd}" -w -I DOCKER-USER 1 -j "${filter_chain}"
fi

"${iptables_cmd}" -w -A "${filter_chain}" \
  -i eth0 -s 192.168.0.0/24 -p tcp -m multiport --dports 80,443 -j RETURN
"${iptables_cmd}" -w -A "${filter_chain}" \
  -i eth0 -p tcp -m multiport --dports 80,443 -j DROP
"${iptables_cmd}" -w -A "${filter_chain}" -j RETURN
