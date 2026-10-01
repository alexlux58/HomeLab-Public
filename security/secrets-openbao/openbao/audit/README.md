# Audit contract

Audit is declared in server configuration, not created through the API. The
active node writes `/var/log/openbao/audit.json` as mode 0640, group
`openbao-audit`. The file is authoritative locally and rotates daily with SIGHUP.
Alloy reads it through group membership and forwards it with only three static
labels: `job`, `node`, and `environment`. No token, accessor, path, entity,
username, request field, or other unbounded value becomes a Loki label.
