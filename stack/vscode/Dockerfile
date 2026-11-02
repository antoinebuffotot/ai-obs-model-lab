# code-server (VS Code in the browser) + the Continue extension (AI chat) wired to the local Ollama model
FROM codercom/code-server:latest
USER root
RUN code-server --install-extension Continue.continue
# git (to fetch Dynatrace skills) and dtctl (Dynatrace CLI, configured by the participants in the terminal).
# A pinned dtctl release is downloaded and verified; if that fails the image still builds (see the build output).
ARG DTCTL_VERSION=0.45.0
COPY install-dtctl.sh /tmp/install-dtctl.sh
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates     && rm -rf /var/lib/apt/lists/*     && sh /tmp/install-dtctl.sh "$DTCTL_VERSION"     && rm -f /tmp/install-dtctl.sh
# Node.js 20 and dt-evals (LLM-as-a-judge evaluations of the GenAI traces, run by the participants in the terminal).
# If the download fails the image still builds.
RUN (curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
      && apt-get install -y --no-install-recommends nodejs \
      && npm install -g @dynatrace-oss/dt-evals) \
    || echo "WARNING: Node.js / dt-evals installation failed"; \
    rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /usr/local/bin/vscode-entrypoint.sh
RUN chmod +x /usr/local/bin/vscode-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/vscode-entrypoint.sh"]
