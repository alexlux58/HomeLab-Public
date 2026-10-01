# Acceptance criteria

The migration is complete only when every box below is ticked, with the named
evidence present. "It seemed to work" is not evidence.

| # | criterion | evidence | how to check |
|---|---|---|---|
| 1 | Existing SSH key access validated on all three hosts | play output of `00-validate-ssh.yml` | `make validate-ssh` — hostname, version and fingerprint match `../../inventory/hosts.yml` |
| 2 | Read-only discovery succeeded without changing anything | `artifacts/discovery.json`, `discovery.md` | every task in `01-discover.yml` is `changed_when: false`; the collector only reads |
| 3 | Synology Volume 2 explicitly rejected | `artifacts/storage-capacity.json` | `nas_forbidden_path_prefixes` includes `/volume2`; stage 1 aborts on any mount source under it |
| 4 | The two `.11` guests each have two verified backup generations | `artifacts/backup-verification.json` | `verdict: pass` and `counts.equal: true` → **4** verified guest-generations |
| 5 | Host configuration and snippets preserved | `host-configs/pve1/latest/`, `host-configs/pve2/latest/` | `/etc/network/interfaces`, `/etc/pve/storage.cfg`, `/var/lib/vz/snippets` present; no key material |
| 6 | Rebuild-later workloads are documented before their disks are lost | `docs/rebuild-catalog.md` | all five `.12` and three `.13` guests plus requested websites are listed with an evidence boundary |
| 7 | `.11` upgraded without losing its VMs | `artifacts/upgrade-diff-pve1.md` | `verdict: pass`, zero regressions; `qm list` shows 290 and 297 |
| 8 | `.11` created the cluster and kept every guest | `artifacts/cluster-create-diff.md` | `pvecm status` quorate; guest set identical before and after |
| 9 | `.13` joined with no guests | `pvecm nodes` | the `pve_join` precheck refuses a non-empty node; `.13` had 0 configs |
| 10 | `.12` was never destroyed without exact approval | `artifacts/destroy-pve2-proposal.md` | all seven gates PASS; `allow_destroy_pve2` **and** the exact string were required |
| 11 | `.12` joined after its clean installation | `pvecm status` | `Total votes: 3`, `Quorate: Yes` |
| 12 | `.12` and `.13` joined empty | `artifacts/migration-report.md` | no guest configs on either node; no restore plan is executed |
| 13 | Three healthy nodes with quorum | `artifacts/migration-report.md` | three members, corosync rings connected, every storage active |
| 14 | No credentials or private keys in Git | CI `secrets` job | gitleaks + a committed-file check; `.gitignore` excludes key material; `tests/test_repo_safety.py` scans for password variables |
| 15 | No backup deleted or pruned | CI `gates` job | `--prune-backups keep-all=1`; `test_no_archive_is_ever_deleted` fails the build on any deletion of `*.vma*` / `*.tar.zst` / anything under `dump/` |

## Verifying the whole set

```bash
make lint test                                   # criteria 15, 16 and the gate model
make validate                                    # criteria 11, 12, 13
jq '.verdict, .counts' artifacts/backup-verification.json     # 4
jq '.verdict' artifacts/upgrade-diff-pve1.json              # 7
jq '.verdict' artifacts/cluster-create-diff.json              # 8
jq '.coverage' artifacts/backup-verification.json             # 4
```

## Safety properties asserted by the test-suite

`pytest -q` proves, offline, that:

* every playbook uses `serial: 1` and `any_errors_fatal: true`;
* no aggregate "run everything" playbook or make target exists;
* every task that destroys data carries **both** the `never` and `destructive`
  tags, so it needs an explicit `--tags all,destructive` opt-in;
* every `allow_*` flag defaults to `false` and is paired with an exact
  confirmation string that defaults to `""`, and both are actually checked by a
  playbook or role;
* `ignore_errors: true`, `rm -rf`, `pvecm expected`, `StrictHostKeyChecking=no`
  and plaintext password variables appear nowhere in executable code;
* the SSH key filename is defined exactly once, as `ssh_key_name`;
* backup pruning is impossible (`keep-all=1`, and no archive deletion anywhere);
* HA is not enabled and the capacity margin is at least 30%.

## Out of scope — deliberately

These are **not** acceptance criteria for this migration, and pretending
otherwise would be misleading:

* **High availability.** Not enabled; there is no shared guest storage.
* **Live migration between nodes.** Requires shared or replicated storage.
* **Off-site backups.** One NAS, one volume, one building.
* **Application-level consistency.** A crash-consistent image of a database is
  not a database backup. Take `pg_dump` / `etcdctl snapshot` inside the guests.
* **A backup of `.12` or `.13` guests.** They are rebuild-later by design.
