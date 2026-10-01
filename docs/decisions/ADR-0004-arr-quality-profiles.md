# ADR-0004: Recyclarr owns quality profiles and custom formats

Status: accepted, Phase 3 (2026-09-29).

## Decision

Recyclarr (TRaSH Guides) manages Radarr quality definitions, quality profiles
and custom formats. The `devopsarr` providers manage everything else and
**never** declare `radarr_quality_profile`, `radarr_custom_format` or
`radarr_quality_definition`. A test in `services/media/tests/` fails if they do.

## Why

The TRaSH profiles change as release groups change; Recyclarr tracks them with
a small reviewed YAML, where the providers would need hundreds of hand-written
custom-format specifications. Two owners would fight on every run.

## Operation

Recyclarr runs on demand in `media-vm` from Ansible (`arr_stack` role):
`recyclarr sync --preview` by default; the real sync needs
`media_allow_recyclarr_sync` and its confirmation. The Radarr API key comes
from the operator-installed env file, never from Git.
