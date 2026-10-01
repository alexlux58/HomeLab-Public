# Homelab services

Declarative Docker Compose configuration for VM 300 `homelab-services`.

- Persistent state: `/srv/homelab/<service>`
- Application-aware backup staging: `/srv/homelab-backups/staging`
- Runtime environment files: `/etc/homelab/secret-store`, root-only and outside Git
- Shared reverse-proxy network: `homelab_proxy`
- Public container ports: only Nginx Proxy Manager on `192.168.0.30:80/443`
- NPM administration: run `ssh -N npm-admin`, then open
  `http://127.0.0.1:8181`; the live service remains bound to `127.0.0.1:81`
- `proxy.lab.example.com` is not an administration route; without an explicit
  proxy-host entry it displays NPM's normal fallback page

Do not add secrets, private keys, generated databases, container state, or
backup archives to this repository. Image changes require an updated reviewed
digest in `images.lock.json`; there is no automatic major-version updater.

NetKnife's homelab web image must include the reviewed
`frontend/.env.production` file because Vite consumes its `VITE_*` settings at
build time. The staged `.dockerignore` excludes all other environment files but
explicitly allows that public build configuration. Its nginx configuration
serves SPA routes with `Cache-Control: no-store` and immutable hashed assets so
browser deployments cannot mix old HTML with a new asset graph.

## Speedtest Tracker mail

The example and bootstrap script configure authenticated STARTTLS delivery
through the dedicated the SMTP provider mailbox `alerts@example.com`. The mailbox
password is deliberately absent from Git. Add `MAIL_PASSWORD` directly to
`/etc/homelab/secret-store/speedtest-tracker.env` with `sudoedit`, retain mode 0600,
and then recreate only the Speedtest Tracker Compose project. `ASSET_URL` is
also pinned to the public HTTPS origin so notification assets do not generate
mixed-content requests behind Nginx Proxy Manager.

the SMTP provider delivery was activated and tested on 2026-08-24 using STARTTLS on
port 587. A controlled Laravel mail dispatch succeeded and the container stayed
healthy with zero restarts. The runtime password remains outside Git.
