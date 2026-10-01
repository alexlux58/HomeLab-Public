# Docker Compose integration

Run one native OpenBao Agent on VM 300, outside individual application
containers. Render files beneath `/run/home-lab-secrets/<service>/` with owner
and mode matched to the container. Mount individual files read-only and prefer
`*_FILE` options. If an image supports only environment variables, use a
root-owned generated env file and accept/document its `docker inspect` exposure.

Migrate one service at a time. Recreate only the affected Compose project,
validate HTTPS/health/backup, rotate the old source value, then remove the former
plaintext file. Never restart all nine containers for one secret.
