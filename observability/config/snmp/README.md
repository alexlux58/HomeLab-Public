# SNMP configuration boundary

`snmp.yml` is deliberately absent from Git because SNMPv3 authentication and
privacy material live inside it. Use `generator.yml.example` only as input to the
official SNMP Exporter generator, then install the generated file as:

```text
/etc/observability/secret-store/snmp.yml  root:root  0600
```

Enable SNMPv3 in DSM with a dedicated read-only monitoring user. Do not enable
SNMPv1/v2c and do not place the passphrases in Ansible inventory or shell history.
