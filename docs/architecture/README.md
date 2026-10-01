# Architecture

An index, not a second copy. Each diagram has exactly one source, a Mermaid file
under [`docs/walkthrough/diagrams/`](../walkthrough/diagrams/), rendered to SVG
with the shared [`mermaid-config.json`](../walkthrough/diagrams/mermaid-config.json)
by `make docs-diagrams`. The walkthrough explains each one in context.

## Diagrams

| # | Shows | Source | Rendered |
| --- | --- | --- | --- |
| 01 | Physical hosts, addresses and the flat /22 network | [`01-physical-network.mmd`](../walkthrough/diagrams/01-physical-network.mmd) | [`01-physical-network.svg`](../walkthrough/diagrams/01-physical-network.svg) |
| 02 | Logical components and how they depend on each other | [`02-logical-components.mmd`](../walkthrough/diagrams/02-logical-components.mmd) | [`02-logical-components.svg`](../walkthrough/diagrams/02-logical-components.svg) |
| 03 | Which directory is responsible for which part of the lab | [`03-repo-responsibility.mmd`](../walkthrough/diagrams/03-repo-responsibility.mmd) | [`03-repo-responsibility.svg`](../walkthrough/diagrams/03-repo-responsibility.svg) |
| 04 | inventory/lab.yml and the consumers checked against it | [`04-single-source-of-truth.mmd`](../walkthrough/diagrams/04-single-source-of-truth.mmd) | [`04-single-source-of-truth.svg`](../walkthrough/diagrams/04-single-source-of-truth.svg) |
| 05 | How one gated stage runs, from the operator's command to the verify step | [`05-gated-stage.mmd`](../walkthrough/diagrams/05-gated-stage.mmd) | [`05-gated-stage.svg`](../walkthrough/diagrams/05-gated-stage.svg) |
| 06 | Rungs L0 to L8, from bare metal to validated onboot | [`06-rebuild-ladder.mmd`](../walkthrough/diagrams/06-rebuild-ladder.mmd) | [`06-rebuild-ladder.svg`](../walkthrough/diagrams/06-rebuild-ladder.svg) |
| 07 | Import-first roots adopt live guests; the rebuild-only root creates them after a loss | [`07-tofu-import-vs-create.mmd`](../walkthrough/diagrams/07-tofu-import-vs-create.mmd) | [`07-tofu-import-vs-create.svg`](../walkthrough/diagrams/07-tofu-import-vs-create.svg) |
| 08 | A browser request to a private site: DNS, TLS at NPM, then the backend | [`08-vm300-request-path.mmd`](../walkthrough/diagrams/08-vm300-request-path.mmd) | [`08-vm300-request-path.svg`](../walkthrough/diagrams/08-vm300-request-path.svg) |
| 09 | Media request flow: Radarr and Prowlarr in the guest, qBittorrent and Plex on Windows, library on the NAS | [`09-media-flow.mmd`](../walkthrough/diagrams/09-media-flow.mmd) | [`09-media-flow.svg`](../walkthrough/diagrams/09-media-flow.svg) |
| 10 | Metrics, logs and alerts: scrape and push paths into VM 310, alerts out by email | [`10-observability-flow.mmd`](../walkthrough/diagrams/10-observability-flow.mmd) | [`10-observability-flow.svg`](../walkthrough/diagrams/10-observability-flow.svg) |
| 11 | OpenBao voters, the Keepalived VIP and the HAProxy front end | [`11-openbao-topology.mmd`](../walkthrough/diagrams/11-openbao-topology.mmd) | [`11-openbao-topology.svg`](../walkthrough/diagrams/11-openbao-topology.svg) |
| 12 | The attended initialization ceremony: automation stops before init | [`12-openbao-init-ceremony.mmd`](../walkthrough/diagrams/12-openbao-init-ceremony.mmd) | [`12-openbao-init-ceremony.svg`](../walkthrough/diagrams/12-openbao-init-ceremony.svg) |
| 13 | After initialization: an OpenBao Agent renders a secret to a file for the PVE exporter | [`13-openbao-approle.mmd`](../walkthrough/diagrams/13-openbao-approle.mmd) | [`13-openbao-approle.svg`](../walkthrough/diagrams/13-openbao-approle.svg) |
| 14 | Backup flow to the NAS and the isolated restore path | [`14-backup-restore.mmd`](../walkthrough/diagrams/14-backup-restore.mmd) | [`14-backup-restore.svg`](../walkthrough/diagrams/14-backup-restore.svg) |
| 15 | GitHub checks end at review; the operator runs gated local stages | [`15-cicd-pipeline.mmd`](../walkthrough/diagrams/15-cicd-pipeline.mmd) | [`15-cicd-pipeline.svg`](../walkthrough/diagrams/15-cicd-pipeline.svg) |
| 16 | From private source to the sanitised public copy and this PDF | [`16-publish-pipeline.mmd`](../walkthrough/diagrams/16-publish-pipeline.mmd) | [`16-publish-pipeline.svg`](../walkthrough/diagrams/16-publish-pipeline.svg) |
| 17 | How an agent change moves from task to commit under the guardrails | [`17-agent-workflow.mmd`](../walkthrough/diagrams/17-agent-workflow.mmd) | [`17-agent-workflow.svg`](../walkthrough/diagrams/17-agent-workflow.svg) |

## Component architecture documents

| Component | Document |
| --- | --- |
| Proxmox cluster | [`platform/proxmox/docs/architecture.md`](../../platform/proxmox/docs/architecture.md) |
| Observability | [`observability/docs/architecture.md`](../../observability/docs/architecture.md) |
| OpenBao | [`security/secrets-openbao/docs/architecture.md`](../../security/secrets-openbao/docs/architecture.md) |
| NAS storage health | [`platform/nas/docs/synology-storage-health.md`](../../platform/nas/docs/synology-storage-health.md) |
| Media | [`services/media/README.md`](../../services/media/README.md) |
| Music Library | [`services/music-library/README.md`](../../services/music-library/README.md) |

Design decisions are recorded as ADRs in [`../decisions/`](../decisions/).
