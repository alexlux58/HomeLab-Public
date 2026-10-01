# Ansible integration

The controller authenticates with a narrow AppRole and short-lived token. A
bootstrap SecretID is installed outside Git and response-wrapped where possible.
Tasks retrieving or rendering values use `no_log: true`; artifacts contain only
paths, ownership, checksums of non-secret config, and pass/fail evidence.

CI runs syntax/lint and Python tests without OpenBao connectivity or credentials.
Do not add a lookup plugin until OpenBao compatibility is verified; the provided
standard-library API tool avoids assuming HashiCorp Vault provider compatibility.
