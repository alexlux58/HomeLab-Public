# Lessons learned against the live lab

Verified against the live hosts. Do not re-derive these. Moved verbatim from the
root `CLAUDE.md` in Phase 2 (2026-09-29).

## Environment facts learned the hard way

Verified against the live hosts. Do not re-derive these.

- **A metric can be written and still never exist.** `backup.sh` writes
  `homelab_observability_backup_last_success_timestamp_seconds` into
  `/var/lib/node_exporter/textfile/` as mode **0600 root:root**. The
  node_exporter container runs as **`nobody`** and cannot read it, so
  `node_textfile_scrape_error = 1` and Prometheus has **no such series**.
  Discovered 2026-09-19. Consequence: any alert written against that metric is
  **vacuous** — it evaluates against nothing and can never fire, which looks
  identical to "healthy". Whenever you add an alert, first confirm its input
  series actually returns data, and alert on
  `node_textfile_scrape_error > 0` so the collector cannot fail silently again.
- **A backup can fail for days while monitoring is perfectly healthy.** VM 310's
  application backup failed six consecutive nights, 2026-09-11 → 09-16, with
  `curl: (7) Failed to connect to 192.168.0.31 port 9090`. Prometheus had
  **continuous data with no gap over 10 minutes** throughout, so the stack was
  not down and the "stack was down" explanation is wrong. **Root cause remains
  unresolved.** This is the second unexplained multi-day backup gap, after
  2026-08-28 → 09-05. `systemctl --failed` is useless retrospectively: later
  successful runs clear the failed state.
- **`qm set <vmid> --nameserver ...` on a STOPPED cloud-init guest regenerates
  the cloud-init drive, and on the next boot cloud-init re-runs and REGENERATES
  THE GUEST'S SSH HOST KEYS.** This happened on 2026-09-06 to VMs 320 `bao-1`
  and 321 `bao-2`: their pinned `known_hosts` fingerprints were invalidated by a
  routine nameserver correction. Guests that were **running** when the same
  change was applied (322, 330) kept their keys, because cloud-init never
  re-ran. Before changing cloud-init settings on a stopped guest, expect a host
  key change and plan to re-verify the fingerprint out of band.
- **A guest's SSH host key can be verified out of band through the hypervisor**
  with `qm guest exec <vmid> -- /usr/bin/ssh-keygen -lf
  /etc/ssh/ssh_host_ed25519_key.pub`. This does not traverse the network SSH
  path, so it is a valid independent channel for confirming that a changed key
  is the guest's own key and not an interception. It is the same method used to
  verify VM 300 in Stage C3. It still does **not** authorise auto-accepting the
  key — the operator updates the pin.
- **`pvesm status|list --output-format json` does not exist** on PVE 8.2 or 9.1.
  Use `pvesh get /nodes/<node>/storage …` instead.
- **`pvesm status` column 6 is Available**, not `$5-$6`.
- **`/etc/pve/qemu-server`, `lxc` and `local` are symlinks** into
  `/etc/pve/nodes/<node>/`. `tar` needs `-h` or the guest configs come out empty
  while the play still reports success.
- **A regex backreference inside a folded (`>-`) or literal (`|-`) YAML scalar is
  passed through verbatim** by Ansible — `regex_search(..., '\1')` yields the
  string `\1`. Plain and double-quoted scalars are fine. This silently broke the
  pve8to9 failure counter, which then evaluated to 0 and would have approved a
  failed upgrade. A test now guards it.
- **`mount.nfs` rejects `vers=` and `nfsvers=` together.** The version is
  negotiated by the probe mount, not hardcoded.
- **`ansible.builtin.unarchive` requires GNU tar**, absent on a stock macOS
  controller. Use `tar -xzf` directly.
- **`community.general.yaml` stdout callback was removed** in v12; use the
  built-in `default` callback with `result_format = yaml`.
- **Proxmox CLI tools have no `--help`.** Use `pvesh usage <api-path> -v`.
- **Ansible's `never` tag**: `--tags all,destructive` runs everything *including*
  never-tagged destructive tasks. Verified.
- The backup role must create `/root/.pve-migration/manifests` before the first
  archive. The first live Stage 3 run exposed this omission after writing and
  hashing EVENG; the archive was kept and the role now creates the directory.
- Bash `PIPESTATUS` cannot be read in the parent after wrapping a pipeline in
  command substitution. The first archive-verification run exposed this. The
  verifier now runs the pipeline in the current shell and captures both statuses.
- `gathering=smart` can reuse a cached `ansible_date_time` in evidence. Gathering
  is now explicit, and backup timestamps come from the archive file's own mtime.
- Ansible's key/value `-e` parser splits multi-word values even when the shell
  delivered them as one argument. Approval examples now use `EXTRA_JSON` so exact
  confirmation phrases are passed as structured JSON.
- Role defaults are scoped to the play that invokes the role. The first full
  Stage 4b run verified all four archives but its localhost adjudication could
  not see `backup_verify_generations`; the variable now lives in `group_vars/all`.

## Working style that has paid off here

Measure before asserting. Two plausible root-cause hypotheses (snapshots, then
disk failure) were both wrong and were only caught by running commands against
the live systems. Prefer a read-only command over an inference, and say plainly
when a previous claim turns out to be wrong.

`du` on the NAS is close to useless — ARM CPU, millions of files, scans run for
hours. Prefer DSM's own reporting, `btrfs` tooling, or per-child parallel scans.
