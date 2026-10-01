# Terraform/OpenTofu integration

Use OpenBao for runtime retrieval only after the cluster exists. The OpenBao VM
bootstrap token must have an independent escrow path. Pass the PVE token as a
process environment variable and unset it immediately after planning/applying.

Provider credentials can still appear in crash dumps or third-party provider
logs. `sensitive=true` is redaction, not encryption. Protect state and plan files
independently, keep `TF_LOG` disabled during authenticated runs, and never commit
state. This repository does not configure OpenBao with a Terraform Vault/OpenBao
provider because compatibility has not been proven.
