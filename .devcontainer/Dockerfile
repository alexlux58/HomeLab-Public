# Pinned Home Lab toolchain. Offline checks, docs build and pre-commit run here.
# Components still build their own venvs from their own pins (`make setup`).
# Bump a version here and in docs/runbooks/windows-wsl2-setup.md together.
FROM python:3.12-slim

ARG OPENTOFU_VERSION=1.12.6
ARG NODE_VERSION=24.21.0
ARG PANDOC_VERSION=3.12
# SHA-256 of pandoc-${PANDOC_VERSION}-linux-amd64.tar.gz; ci.yml pins the same value.
ARG PANDOC_SHA256=67d7d011fed8c8543306022b985b9b2499ab9b74818df91d8727c7e9ebc5ba06
ARG GITLEAKS_VERSION=8.30.1
ARG MERMAID_CLI_VERSION=12.0.0
ARG ANSIBLE_CORE_VERSION=2.19.4
ARG ANSIBLE_LINT_VERSION=25.12.2
ARG YAMLLINT_VERSION=1.37.1
ARG PRE_COMMIT_VERSION=4.3.0
ARG RUFF_VERSION=0.12.11
ARG PYTEST_VERSION=8.4.2
ARG WEASYPRINT_VERSION=70.0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Base tools, WeasyPrint's Pango stack, Chromium's libraries for mermaid-cli,
# and poppler-utils (pdftotext) so the publisher can scan inside PDFs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git jq make openssh-client perl poppler-utils shellcheck unzip xz-utils \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
      libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
      libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2t64 libgl1 libegl1 \
 && rm -r /var/lib/apt/lists/*

# OpenTofu, verified against the release's SHA256SUMS.
RUN cd /tmp \
 && curl -fsSLO "https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_linux_amd64.zip" \
 && curl -fsSLO "https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_SHA256SUMS" \
 && sha256sum --check --ignore-missing "tofu_${OPENTOFU_VERSION}_SHA256SUMS" \
 && unzip -q "tofu_${OPENTOFU_VERSION}_linux_amd64.zip" tofu -d /usr/local/bin \
 && rm "tofu_${OPENTOFU_VERSION}_linux_amd64.zip" "tofu_${OPENTOFU_VERSION}_SHA256SUMS"

# gitleaks, verified against the release checksums.
RUN cd /tmp \
 && curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
 && curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt" \
 && sha256sum --check --ignore-missing "gitleaks_${GITLEAKS_VERSION}_checksums.txt" \
 && tar -xzf "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" -C /usr/local/bin gitleaks \
 && rm "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" "gitleaks_${GITLEAKS_VERSION}_checksums.txt"

# Pandoc, verified against the pinned SHA-256.
RUN curl -fsSLo /tmp/pandoc.tar.gz "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-linux-amd64.tar.gz" \
 && echo "${PANDOC_SHA256}  /tmp/pandoc.tar.gz" | sha256sum --check - \
 && tar -xzf /tmp/pandoc.tar.gz -C /usr/local --strip-components=1 \
 && rm /tmp/pandoc.tar.gz

# Node.js LTS and mermaid-cli. Puppeteer fetches its pinned Chromium into a
# shared cache (not root's home) so the non-root user can launch it. Chrome's
# sandbox needs user namespaces that Docker's default profile denies, so the
# docs build passes /etc/puppeteer-config.json (`mmdc -p`).
ENV PUPPETEER_CACHE_DIR=/opt/puppeteer
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1 \
 && npm install -g "@mermaid-js/mermaid-cli@${MERMAID_CLI_VERSION}" \
 && npm cache clean --force \
 && chmod -R a+rX /opt/puppeteer \
 && printf '{"args":["--no-sandbox"]}\n' > /etc/puppeteer-config.json

# Shared Python tools for pre-commit and the docs build.
RUN python -m pip install --no-cache-dir \
      "ansible-core==${ANSIBLE_CORE_VERSION}" \
      "ansible-lint==${ANSIBLE_LINT_VERSION}" \
      "yamllint==${YAMLLINT_VERSION}" \
      "pre-commit==${PRE_COMMIT_VERSION}" \
      "ruff==${RUFF_VERSION}" \
      "pytest==${PYTEST_VERSION}" \
      "weasyprint==${WEASYPRINT_VERSION}"

RUN useradd --create-home --shell /bin/bash dev
USER dev
