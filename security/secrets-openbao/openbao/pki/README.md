# PKI boundary

`scripts/pki_bootstrap.py` creates the bootstrap offline root and node TLS
certificates outside Git. After OpenBao is initialized, enable `pki_int`,
generate an intermediate CSR inside OpenBao, sign only that CSR with the offline
root, import the signed intermediate, then return the root key to offline
custody. The automation never uploads the offline root key into OpenBao.
