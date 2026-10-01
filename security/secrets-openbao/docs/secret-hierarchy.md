# Secret hierarchy and migration

The machine-readable namespace is `openbao/secret-hierarchy.json`. KV v2 keeps
versions, but version history is not a substitute for rotating exposed values.

For every secret:

1. list consumers and current recovery owner;
2. document rollback and current rotation;
3. create the narrow policy and AppRole;
4. deploy Agent and protected render target;
5. validate the application with a non-production/test credential where possible;
6. rotate the real credential at its source;
7. write only the rotated value to OpenBao;
8. switch one consumer and restart only that service;
9. verify health and telemetry;
10. remove the former plaintext copy and search repository/history/artifacts by
    filename and key name;
11. revoke the old credential and record the date.

Do not migrate browser passwords first. macOS Keychain remains an independent
break-glass path. Do not migrate the Synology backup transport key or age
decryption identity into OpenBao; either is needed when OpenBao is unavailable.
