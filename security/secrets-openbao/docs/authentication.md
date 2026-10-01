# Authentication

## Operators

Use OIDC only after a reliable identity provider is selected and its outage
recovery is tested. Until then, keep one tightly controlled operator method and
the documented generate-root break-glass procedure. Root tokens are not normal
login credentials.

## Machines

AppRole is prepared for current non-Kubernetes clients. Roles have one policy,
short token TTLs, bounded SecretID TTLs/uses, and source CIDR restrictions.
OpenBao Agent performs auto-auth and writes a mode-0600 sink under `/run`.
Applications receive a rendered file or `*_FILE` mount, never a token in Compose
or inventory.

The repository reconciles role definitions but does not generate or print RoleID
or SecretID values. The operator creates response-wrapped SecretIDs and installs
them directly on the target host.

## Pilot

Migrate the read-only PVE exporter token first. Its blast radius is smaller than
SMTP, Grafana administrator, DNS, NAS, or provisioning credentials. Validate
agent renewal, file permissions, exporter restart, Prometheus health, rollback,
and token rotation before migrating another secret.
