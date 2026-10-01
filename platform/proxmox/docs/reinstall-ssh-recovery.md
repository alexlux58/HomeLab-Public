# SSH recovery after a node is reinstalled or joins the cluster

An SSH host key changes in exactly two situations in this migration:

1. a node is **clean-installed** (`.13` in stage 5, `.12` in stage 9);
2. a node **joins the cluster** — `pvecm add` replaces the node's SSH host keys
   with cluster-signed ones.

In both cases the change is expected. **It is still never accepted
automatically.** `ansible.cfg` keeps `host_key_checking = True`, no playbook sets
`StrictHostKeyChecking=no`, and `roles/ssh_validation` compares the live
fingerprint against `expected_host_fingerprint` in `../../inventory/hosts.yml` and
fails loudly on a mismatch.

## Fingerprints recorded at the latest verified console check

These were read at each host's own console. They are public data.

| host | IP | fingerprint at time of writing |
|---|---|---|
| `pve1` | 192.168.0.11 | `SHA256:EXAMPLE_FINGERPRINT_REDACTED` |
| `pve2` | 192.168.0.12 | `SHA256:EXAMPLE_FINGERPRINT_REDACTED` |
| `pve3` | 192.168.0.13 | `SHA256:EXAMPLE_FINGERPRINT_REDACTED` |

`.11` should keep its fingerprint through the in-place upgrade, and lose it when
it becomes a cluster node. `.12` and `.13` will change at least twice.

## The recovery procedure

### 1. Read the new fingerprint at the console — not over SSH

Physical console, IPMI/iKVM, or the Proxmox web shell. The point of this step is
to obtain the fingerprint over a channel the network cannot tamper with, so
reading it over the SSH session you are trying to validate defeats it.

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Write down the `SHA256:...` value.

### 2. Compare it by hand

Compare the value from the console with the value your SSH client is about to
show you. Character by character — a truncated glance at the first six characters
is not a comparison.

### 3. Remove only the stale entries

```bash
ssh-keygen -R 192.168.0.13
ssh-keygen -R pve3
```

`ssh-keygen -R` removes only the entries for the names you give it. Do **not**
delete `~/.ssh/known_hosts`: that would throw away the verified keys of every
other host you trust.

### 4. Connect once interactively and accept the verified key

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/proxmox_cluster_ed25519 root@192.168.0.13
```

SSH prints the fingerprint and asks whether to continue. **Only type `yes` if it
matches what you read at the console.** If it does not match, stop: either you are
talking to the wrong machine, or something is between you and it.

### 5. Reinstall the existing public key

A clean install wipes `/root/.ssh/authorized_keys`. Put the **existing** key back —
no new key is ever generated for this project.

```bash
ssh root@192.168.0.13 \
  'umask 077; mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; \
   cat >> /root/.ssh/authorized_keys; \
   sort -u -o /root/.ssh/authorized_keys /root/.ssh/authorized_keys; \
   chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys' \
  < ~/.ssh/proxmox_cluster_ed25519.pub
```

This prompts once for the node's root password — a password you type yourself,
into your own terminal. It is never stored, never passed to Ansible, and never
appears in this repository.

### 6. Update the recorded fingerprint

Edit `../../inventory/hosts.yml` and set `expected_host_fingerprint` for that host to
the value you verified. This is what makes the *next* unexpected change detectable.

### 7. Prove key authentication works

```bash
ssh pve3 'hostname; pveversion'
ansible -i ../../inventory/hosts.yml pve -m ansible.builtin.ping
make validate-ssh
```

`ansible.cfg` sets `BatchMode=yes` and `PreferredAuthentications=publickey`, so if
key auth is not working these fail immediately rather than silently falling back
to a password prompt.

### 8. Only then continue the migration

Every stage that follows a reinstall requires you to assert this was done:

```bash
-e pve3_fingerprint_verified=true      # stage 5, 8
-e pve2_fingerprint_verified=true      # stage 9
```

## Recommended `~/.ssh/config`

```sshconfig
Host pve1
    HostName 192.168.0.11
    User root
    IdentityFile ~/.ssh/proxmox_cluster_ed25519
    IdentitiesOnly yes

Host pve2
    HostName 192.168.0.12
    User root
    IdentityFile ~/.ssh/proxmox_cluster_ed25519
    IdentitiesOnly yes

Host pve3
    HostName 192.168.0.13
    User root
    IdentityFile ~/.ssh/proxmox_cluster_ed25519
    IdentitiesOnly yes
```

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config ~/.ssh/proxmox_cluster_ed25519
chmod 644 ~/.ssh/proxmox_cluster_ed25519.pub
```

## If the key file is named something else

Change **one** variable:

```yaml
# inventory/group_vars/all.yml
ssh_key_name: my_other_key_name
```

`ssh_private_key_file`, `ssh_public_key_file` and the inventory's
`ansible_ssh_private_key_file` all derive from it. A unit test
(`tests/test_inventory_schema.py::test_key_filename_is_defined_exactly_once`)
fails if anyone hardcodes the filename anywhere else.

## What must never happen

* Never run `ssh -o StrictHostKeyChecking=no`.
* Never set `host_key_checking = False` in `ansible.cfg`.
* Never `rm ~/.ssh/known_hosts` to "fix" a warning.
* Never accept a changed fingerprint you have not read at the console.
* Never automate the ISO reinstall through the SSH session that is about to be
  destroyed by it.
