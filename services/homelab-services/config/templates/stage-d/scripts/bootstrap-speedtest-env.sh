#!/bin/sh
# Run manually as root. Writes the required Laravel APP_KEY directly to the
# external root-only environment file and never prints the key.
set -eu

target_file=/etc/homelab/secret-store/speedtest-tracker.env

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

if [ -e "${target_file}" ]; then
  echo "Refusing to replace existing ${target_file}." >&2
  exit 2
fi

install -d -m 0750 -o root -g root /etc/homelab/secret-store
temporary_file=$(mktemp /etc/homelab/secret-store/.speedtest-tracker.env.XXXXXX)
trap 'test ! -e "${temporary_file}" || rm -f -- "${temporary_file}"' EXIT HUP INT TERM
umask 077

{
  printf 'APP_KEY=base64:'
  openssl rand -base64 32 | tr -d '\n'
  printf '\n'
  printf '%s\n' \
    'PUID=1000' \
    'PGID=1000' \
    'TZ=America/Los_Angeles' \
    'APP_TIMEZONE=America/Los_Angeles' \
    'DISPLAY_TIMEZONE=America/Los_Angeles' \
    'DB_CONNECTION=sqlite' \
    'APP_URL=https://speed.lab.example.com' \
    'ASSET_URL=https://speed.lab.example.com' \
    'SPEEDTEST_SCHEDULE=0 */6 * * *' \
    'MAIL_MAILER=smtp' \
    'MAIL_HOST=smtp.smtp.com' \
    'MAIL_PORT=587' \
    'MAIL_SCHEME=null' \
    'MAIL_USERNAME=alerts@example.com' \
    'MAIL_FROM_ADDRESS=alerts@example.com' \
    'MAIL_FROM_NAME="Home Lab Speedtest"'
} > "${temporary_file}"

chown root:root "${temporary_file}"
chmod 0600 "${temporary_file}"
mv -n -- "${temporary_file}" "${target_file}"
test -e "${target_file}"
trap - EXIT HUP INT TERM

echo "Created ${target_file} with mode 0600; key value was not printed."
echo "Add MAIL_PASSWORD locally with sudoedit before enabling mail notifications."
