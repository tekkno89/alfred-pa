FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# System deps (redis-tools for redis-cli completion reporting)
RUN apt-get update && apt-get install -y \
    git curl wget gnupg2 ca-certificates build-essential jq redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Python 3 + uv
RUN apt-get update && apt-get install -y \
    python3 python3-venv python3-pip \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# GCP SDK (for Vertex AI auth) — install as root, then available to all users
RUN curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=/opt
ENV PATH="/opt/google-cloud-sdk/bin:$PATH"

# Non-root user
RUN useradd -m -u 1000 coder \
    && mkdir -p /workspace /output /credentials \
    && chown -R coder:coder /workspace /output

COPY --chown=coder:coder entrypoint.sh /entrypoint.sh
COPY --chown=coder:coder block-sensitive-paths.sh /usr/local/bin/block-sensitive-paths.sh
COPY --chown=coder:coder report-completion.py /usr/local/bin/report-completion.py
RUN chmod +x /entrypoint.sh /usr/local/bin/block-sensitive-paths.sh /usr/local/bin/report-completion.py

USER coder
WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
