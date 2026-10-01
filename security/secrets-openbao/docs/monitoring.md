# Monitoring and alerting

Reuse VM 310. Do not deploy a second Prometheus, Loki, Grafana, or Alertmanager.

## Metrics

Prometheus authenticates with the `metrics` policy through an Agent on VM 310
and scrapes each direct node. Required alerts:

- sealed node or no active leader;
- fewer than three Raft peers or Autopilot unhealthy;
- request/audit failures and high latency;
- process restart, memory pressure, disk/audit directory above 80%;
- TLS expiry 30/14/7 days;
- newest encrypted snapshot older than 30 hours;
- snapshot/transfer/inspection failure;
- Agent authentication/renewal failure.

## Audit logs

Alloy reads the local mode-0640 file through the `openbao-audit` group and sends
to VM 310 Loki. Labels are static: `job=openbao-audit`, node, and environment.
Never promote token, accessor, entity, username, path, request, response, or
arbitrary metadata fields to labels. Restrict the Loki/Grafana audit view to the
operator.

The OpenBao audit path is local-first. Loki unavailability must not remove local
audit evidence or block OpenBao. Audit file write failure can block requests and
therefore pages immediately.
