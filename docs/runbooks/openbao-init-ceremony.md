# OpenBao initialization ceremony — Saturday 2026-10-10

D4 approved 2026-09-30. The operator may move the date. One operator owns all
five PGP keys; the threshold is **three of five**. Every `bao operator` command
below is typed by the operator, never run by an agent, CI or automation.
The ceremony takes place outside recorded terminals, agent tools and chat.

## Day before: Friday 2026-10-09

All of these must be true before proceeding:

- A recent **verified vzdump archive of each VM 320, 321 and 322** exists.
  Confirm VMID, timestamp, size, SHA-256 and compressed/VMA integrity using
  the existing [archive verification tooling](../../platform/proxmox/scripts/verify_vma_archives.py).
  Record the verification result, never archive contents. A configured job
  alone is insufficient. Retain NAS originals and every independent copy.
- VMs 320–322 are available with expected resource limits, pinned SSH keys,
  valid TLS, healthy HAProxy/Keepalived and reachable direct API addresses.
  VIP is `192.168.0.40`; direct addresses are `.20`, `.21`, `.22`.
  Resolve `bao.lab.example.com` specifically to the VIP, not VM 300's
  wildcard. The operator performs any needed DNS change separately.
- The read-only `make -C security/secrets-openbao validate-uninitialized`
  succeeds for all three nodes and reports `initialized=false`, `sealed=true`.
  The 2026-09-30 attempt stopped before connecting because the runtime input
  `openbao_ssh_private_key_file` was unset; no fresh validation is claimed.
  Supply approved runtime inventory privately, with strict host-key checking.
- All five public encryption keys are distinct, usable, unexpired and their
  full primary/subkey fingerprints match the offline originals. Practice a
  restore/decrypt test offline for each custody format before the ceremony.
- Password manager and custody locations are available; there is a secure
  operator-only way to transfer encrypted shares. No location contains three
  private keys/shares. No maintenance or rebuild competes with the ceremony.
- CA trust is available to the operator client and the offline root CA key
  has been encrypted and moved to tested offline custody as described below.
- Post-init policy/auth inputs, a replacement administrative access path,
  an age public recipient, off-NAS age identity custody and backup destination
  are prepared. An initialization is not permission to run subsequent gates.

## Offline generation and custody

Use an offline machine with GnuPG and paperkey installed. Generate **one key
at a time**, with its own passphrase entered through GnuPG's prompt and stored
in the password manager. Do not put passphrases in arguments, environment
variables, scripts or shell history. RSA encryption subkeys avoid assumptions
about newer OpenPGP algorithms in the installed OpenBao 2.6.1.

For `N=1`, then repeat separately for 2–5 after distributing and testing the
previous key; substitute an offline storage path:

```bash
N=1
keyhome="/offline/openbao-key-${N}"
mkdir -m 700 "$keyhome"
uid="Home Lab OpenBao share ${N} <openbao-share-${N}@example.invalid>"
gpg --homedir "$keyhome" --quick-generate-key "$uid" rsa3072 cert 0
fingerprint=$(gpg --homedir "$keyhome" --with-colons --fingerprint "$uid" |
  awk -F: '$1 == "fpr" { print $10; exit }')
gpg --homedir "$keyhome" --quick-add-key "$fingerprint" rsa3072 encr 0
gpg --homedir "$keyhome" --armor --export "$fingerprint" > "recipient-${N}.asc"
gpg --homedir "$keyhome" --with-subkey-fingerprint --fingerprint "$fingerprint"
gpg --homedir "$keyhome" --armor --export-secret-keys "$fingerprint" > "share-${N}-private.asc"
gpg --homedir "$keyhome" --export-secret-keys "$fingerprint" > "share-${N}-private.gpg"
paperkey --secret-key "share-${N}-private.gpg" --output "share-${N}-paperkey.txt"
```

Private exports and paperkey output stay **entirely offline and operator-only**.
Paperkey recovery also needs the matching public key. Retain that public key
with each recovery packet. Verify the secret export remains passphrase
protected. After a tested restore and custody transfer, the operator removes
temporary secret exports and that generation keyring before generating the
next key; do not leave all five keys on the generation machine.
See [GnuPG key management](https://www.gnupg.org/documentation/manuals/gnupg/OpenPGP-Key-Management.html).

| Share | Permanent custody |
| --- | --- |
| 1 | Password manager: exported, passphrase-protected private key |
| 2 | Encrypted USB stick in a locked place at home |
| 3 | Paperkey paper copy in a second place at home |
| 4 | Paperkey paper copy off-site with a trusted relative or safe-deposit box |
| 5 | Encrypted file in a personal cloud account from a different provider than the password manager |

The operator retains the corresponding encrypted share with each recovery
packet, with no single place holding three shares. This protects against
losing or stealing any two places. **It does not protect against coercing
the one person who controls every share.** Passphrase custody remains in the
operator's password manager; it is not an additional independent key holder.

Only public `.asc` keys and fingerprints may approach the repo or an agent.
On the operator client, compare the full fingerprints to the offline list:

```bash
for N in 1 2 3 4 5; do
  gpg --show-keys --with-fingerprint --with-subkey-fingerprint "recipient-${N}.asc"
  gpg --dearmor --output "/secure/recipient-${N}.pgp" "recipient-${N}.asc"
done
```

Binary `.pgp` files are public-key runtime inputs kept outside the repo.
Compare all fingerprints visually using a second trusted record; never accept
only a short key ID or the filename. Require the encryption subkey as well.

## Operator commands on ceremony day

Use the verified TLS endpoint and CA certificate; never disable verification.
Ensure the operator shell is not logging/transcribing and is outside chat.

```bash
export BAO_ADDR=https://192.168.0.40:8200
export BAO_CACERT=/secure/openbao-root-ca.pem
bao status
bao operator init -key-shares=5 -key-threshold=3 \
  -pgp-keys=/secure/recipient-1.pgp,/secure/recipient-2.pgp,/secure/recipient-3.pgp,/secure/recipient-4.pgp,/secure/recipient-5.pgp \
  -root-token-pgp-key=/secure/recipient-1.pgp
```

Initialize **once**, on the cluster, after observing uninitialized status.
The five returned shares and initial root token are encrypted. Preserve them
directly in operator-only custody; no tool captures this output. Do not paste
even encrypted shares into Git or chat. Follow the
[OpenBao init command reference](https://openbao.org/docs/commands/operator/init/).

Transfer encrypted outputs to the offline operator machine. For each of three
distinct shares, save its Base64 text in an operator-only offline file, decode
and decrypt it there with the matching key. No cleartext share leaves the
operator's attended process:

```bash
base64 --decode encrypted-share-1.b64 > encrypted-share-1.pgp
gpg --homedir /offline/restored-share-1 --decrypt encrypted-share-1.pgp
```

Repeat for shares 2 and 3 using their own recovered offline keyrings. Enter
each cleartext share through the hidden prompt; never supply it as an argument:

```bash
export BAO_ADDR=https://192.168.0.41:8200
bao operator unseal
bao operator unseal
bao operator unseal
bao status
```

Repeat the three prompts and status check on `.21` and `.22`. Confirm every
voter is unsealed and healthy. Do not reinitialize a follower. Decode/decrypt
the initial root token offline in the same way, then enter it only into an
operator-only shell's hidden prompt when administrative setup requires it:

```bash
read -r -s -p 'Initial root token: ' BAO_TOKEN
printf '\n'
export BAO_TOKEN
```

Once post-init configuration and replacement administrator access are verified,
the **operator** revokes the initial root token and clears the shell variable:

```bash
bao token revoke -self
unset BAO_TOKEN
```

No token or unseal share is ever passed to an agent. Agent-run configuration
uses approved runtime files/credentials through the established secrets
workflow, without exposing their contents in tool output.

## Subsequent local stages, each separately authorized

| Stage | Gate / verification |
| --- | --- |
| `make -C security/secrets-openbao configure-post-init` | `allow_configure_openbao_post_init=true`; `CONFIGURE OPENBAO POST INIT NO SECRET VALUES` |
| `make -C security/secrets-openbao validate-post-init` | Read-only verification of auth, policy and engines; establish and test replacement administrative access before root-token revocation |
| `make -C security/secrets-openbao configure-backup` | `allow_configure_openbao_backup=true`; `CONFIGURE ENCRYPTED OPENBAO RAFT BACKUPS`; age public recipient on hosts, private identity outside both the NAS and OpenBao |
| `make -C security/secrets-openbao configure-monitoring` | `allow_configure_openbao_monitoring=true`; `CONFIGURE OPENBAO MONITORING AND AUDIT SHIPPING` |

The agent prepares each exact `EXTRA_JSON` only after preconditions are true
and the operator supplies that stage's confirmation. None runs today.
Backup acceptance includes an encrypted snapshot and an isolated restore
verification; it never deletes or replaces the only copy.

## Offline root CA custody and boundaries

The operator alone encrypts and moves
`~/.local-credentials/home-lab/openbao/pki/offline-root-key.pem`. On an offline machine,
use a separately retained age public recipient and verify decryption before
removing the online plaintext. For example, typed only by the operator:

```bash
age -r '<offline-custody-age-public-recipient>' \
  -o /offline-custody/offline-root-key.pem.age \
  ~/.local-credentials/home-lab/openbao/pki/offline-root-key.pem
```

Retain tested encrypted copies and the decrypting identity in separate,
off-NAS custody. The agent never reads the PEM, identity, private PGP keys,
passphrases, cleartext/encrypted shares, root token, recovery tokens, real
runtime secret files or application databases. Public CA certificates are
not private CA keys. Update the [rotation/custody checklist](../../security/secrets-openbao/docs/rotation.md)
after the operator confirms custody, not before.

If prerequisites fail, postpone the ceremony. After initialization there is
no casual reset or rollback: stop follow-up stages, preserve the recovery
material, and diagnose with the operator. Never delete Raft data to retry init.
