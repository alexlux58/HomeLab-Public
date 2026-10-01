# Secret-bearing source excluded from the monorepo import

The historical OpenBao repository contained secret-scanner findings in these
paths:

- `ansible/inventory/group_vars/all.yml`
- `openbao/secret-hierarchy.json`

Their complete history was deliberately excluded from this private monorepo
import. The untouched source repository is retained at
`C:\Users\labuser\Documents\Home-Lab-Phase1-Source-Archive\homelab-openbao`
for attended recovery and rotation work.

Do not copy either file into this repository. Recreate the required
operator-managed values through the approved secret workflow in Phase 3, then
record the rotation and validation evidence in the relevant runbook.
