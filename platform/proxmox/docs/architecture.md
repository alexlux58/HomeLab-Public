# Architecture and data flow

## The environment as it is today

| host | IP | hostname | PVE | role in this migration |
|---|---|---|---|---|
| seed | 192.168.0.11 | `pve1` | 8.2.2 | Preserve VMID 290. Upgrade in place to PVE 9, then create the cluster. Never clean-installed. (VMID 297 was also preserved through the migration; the operator confirmed it obsolete and destroyed it on 2026-09-19. Its archives are retained.) |
| member | 192.168.0.12 | `pve2` | 8.2.2 | Catalog old workloads, clean-install, and join empty. Rebuild desired software later. |
| member | 192.168.0.13 | `pve3` | 9.2.2 | Clean-installed and empty; join after the seed upgrade. |
| backup | 192.168.0.20 | Synology DSM | — | NFS backup target on **Volume 1 / Storage Pool 2 only**. |

Guests that must survive:

```text
pve1   290 EVENG
```

Guests deliberately replaced by later clean rebuilds: `pve2` 100
Ansbile-Puppet, 101 lab-k3s, 102 UbuntuServer2, 9000 ubuntu-jammy-ci, 9100
metasploitable2; and `pve` 100 NIXOS, 101 Kali, 102 ProxmoxDatacenterManager.
See [rebuild-catalog.md](rebuild-catalog.md).

## Why this order

The migration is sequenced around a single rule: **never touch the seed until
both generations of the two required guests have verified.** The other eight
guest disks are explicitly outside the retention scope.

```text
       ┌─────────────────────────────────────────────────────────────┐
       │ 0  read-only discovery of all three hosts                   │
       │ 1  prove the NAS is reachable, writable, on Volume 1        │
       │ 2  capture host config that vzdump does NOT contain         │
       │ 3  backup generation 1 (live snapshot)                      │
       │ 4  backup generation 2 (guests cleanly stopped) + verify    │
       └───────────────────────────┬─────────────────────────────────┘
                                   │  archives exist and are verified
       ┌───────────────────────────▼─────────────────────────────────┐
       │ 5  catalog + wipe .13 -> PVE 9.2, empty                    │
       └───────────────────────────┬─────────────────────────────────┘
                                   │  proof that the archives restore on PVE 9
       ┌───────────────────────────▼─────────────────────────────────┐
       │ 6  upgrade .11 in place 8.2 -> 8.4 -> 9.2                  │
       │ 7  pvecm create homelab on .11   (guests preserved)        │
       │ 8  .13 joins empty                                         │
       └───────────────────────────┬─────────────────────────────────┘
                                   │  a healthy two-node cluster exists
       ┌───────────────────────────▼─────────────────────────────────┐
       │ 9  ONLY NOW: catalog + rebuild .12, join it empty          │
       │ 10 validate the finished three-node cluster                 │
       └─────────────────────────────────────────────────────────────┘
```

`.13` is rebuilt first because no guest on it must survive. It becomes the first
empty PVE 9.2 member, while `.11` remains the only source of retained guest data.

## Data flow

```text
 pve1 (.11) ──vzdump, two generations──► NFS 192.168.0.20:/volume1/proxmox-cluster-backups
                                             (Proxmox storage id: synology-backup)

 pve2 (.12) ──configuration + rebuild notes──► controller only
 pve3 (.13) ──configuration + rebuild notes──► controller only

 controller (macOS)
   ├─ SSH publickey only  ──►  all three hosts
   ├─ artifacts/          ◄──  discovery, manifests, plans, reports
   └─ host-configs/       ◄──  sanitized /etc/network, /etc/pve, snippets
```

The controller never holds guest data. It holds *decisions*: what was found, what
was verified, what is planned, and what actually happened.

## What a vzdump archive does not contain

This is the reason stage 2 exists as a separate stage:

| lives in the archive | lives only on the host |
|---|---|
| guest disks (`backup=1` only) | `/etc/network/interfaces` — bridges, bonds, VLANs |
| the guest's `.conf` | `/var/lib/vz/snippets` — hook scripts, cloud-init snippets |
| EFI vars / TPM state disks | `/etc/pve/storage.cfg` — storage definitions |
| snapshots (metadata) | `/etc/modprobe.d`, `/etc/modules`, GRUB cmdline (VFIO, IOMMU) |
| | firewall rules under `/etc/pve/firewall` |
| | the physical PCI/USB devices any passthrough guest expects |

A perfect archive restored onto a host without the matching bridge simply does not
start. Both halves are captured for `.11`; `.12`'s capture is retained as a
rebuild reference, not as a promise that its old guests can be restored.

## Why Ansible and Python, and why not Terraform

**Ansible** is the right tool here because this migration is a *sequence of
imperative, gated, one-shot operations against machines that already exist*:
`pve8to9`, `apt dist-upgrade`, `pvecm create`, `vzdump`, `vma verify`,
`qmrestore`. Ansible gives ordered execution, `serial: 1`, per-task assertions,
`any_errors_fatal`, tags that can withhold a dangerous task, and — crucially —
the ability to stop and hand control back to a human mid-run.

**Python** does the thinking: normalising a messy inventory, detecting every VMID
and MAC collision (not just the one we know about), computing capacity with a
pessimistic compression assumption, adjudicating whether the verified archive
count equals the protected guest count, and diffing pre/post state. That logic is
worth unit-testing, and it is unit-tested — `pytest` runs it offline against
fixtures, with no host in sight.

**Terraform is the wrong tool for this migration**, for reasons that are about
its model, not its quality:

1. **Terraform reconciles declared state; migration is a procedure.** "Upgrade
   from 8.2 to 8.4 to 9.2, run a checklist between each step, stop on a warning"
   is not expressible as a desired end state.
2. **`terraform apply` computes a plan and executes it.** A plan that says
   `~ update in-place` next to a VM holding production data is exactly the
   unattended destructive command this project is built to prevent.
3. **Importing existing guests into state is a trap.** Once VMID 287 is in a
   state file, a drifted attribute or a provider upgrade can propose replacing
   it. These VMs must be untouchable, so they must never be in state at all.
4. **Terraform cannot install an operating system from an ISO**, cannot wipe a
   physical node, and has no notion of Corosync membership — `pvecm create` and
   `pvecm add` are cluster-filesystem operations, not API resources.
5. **Backup verification is not a resource.** "Stream 400 GiB through
   `vma verify` and refuse to continue on a non-zero pipeline status" has no
   declarative expression.

Terraform *is* appropriate **after** the migration, for provisioning *new* VMs
from a template on the finished cluster. `terraform/` is deliberately not part of
this repository's execution path; see the README for the recommended shape if you
want it later.

## Why HA is not enabled

Proxmox HA restarts a guest on a surviving node when a node fails. That only works
if the surviving node can *see the guest's disk*. In this cluster every guest disk
lives on node-local LVM-thin. Enabling HA would give you fencing (nodes rebooting
themselves) with no ability to actually restart anything.

Clustering here buys: one UI and API, one user/permission/firewall configuration,
cold migration between nodes, and cluster-wide backup jobs. It does not buy
failover. See the migration report for the explicit table.

## References

* Proxmox VE 8 to 9 upgrade — <https://pve.proxmox.com/wiki/Upgrade_from_8_to_9>
* Cluster Manager — <https://pve.proxmox.com/wiki/Cluster_Manager>
* Backup and restore (vzdump) — <https://pve.proxmox.com/pve-docs/chapter-vzdump.html>
* NFS storage — <https://pve.proxmox.com/wiki/Storage:_NFS>
* Package repositories — <https://pve.proxmox.com/wiki/Package_Repositories>
* Roadmap / current release — <https://pve.proxmox.com/wiki/Roadmap>
* Proxmox VE 9.2 announcement — <https://proxmox.com/en/about/company-details/press-releases/proxmox-virtual-environment-9-2>
