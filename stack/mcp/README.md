# Exercise: connect the agent to a Dynatrace MCP server

[Version française](README.fr.md)

This folder (`/workspace/mcp`) is the default folder of the web VS Code (`http://<vm>:8080/`).
The agent (`http://<vm>/agent.html`) reads the **`mcp.json`** file in this folder: you have to create it.

## 1. Create a platform token in Dynatrace

1. **Access Tokens** > **Generate new token**.
2. Scopes: `mcp-gateway:servers:invoke` and `mcp-gateway:servers:read`, plus the read permissions you want
   (for example `storage:logs:read`, `storage:entities:read`, `storage:metrics:read`, `storage:events:read`,
   `storage:spans:read`, `document:documents:read`, `davis:analyzers:read`, `davis:analyzers:execute`).
3. Copy the token (`dt0s16.…`); it is displayed only once.

Your user must also have these permissions: the token cannot do more than you can.

## 2. Create `mcp.json`

Copy `mcp.json.example` to `mcp.json`, then replace the URL of your environment and the token.
Server URL: `https://<environnement>.apps.dynatrace.com/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp`

- `url`: **remote** MCP server (HTTP). Local servers (stdio) are not supported.
- `headers`: headers sent to the server. `${NOM}` is replaced by the environment variable `NOM`.
- `tools` (optional): list of allowed tools. Recommended: the model chooses better with a few tools, and it avoids the tools that write to Dynatrace.

The file contains a secret: it stays on your VM (ignored by git), do not share it.

## 3. Verify

Open the agent page, **Tools** tab: an "MCP servers" line shows the connection status
(error 401: invalid token; 403: missing permissions, check `mcp-gateway:servers:invoke`).
No restart is needed (automatic reload within a minute).
Then ask a question, for example: "Which problems are open in Dynatrace?".
With OpenLLMetry active, each MCP call appears in the trace as a tool span.

---

# Exercise: give dtctl to the agent

`dtctl` is the Dynatrace command line (https://github.com/Dynatrace/dtctl), installed in the web VS Code and in
the agent image. Once configured, the agent (Dynatrace sub-agent) uses it as a **read-only** tool
(`query`, `get`, `describe`, `logs`, `inventory`, `commands`, `exec copilot nl2dql|dql2nl`).

## 1. Create a read-only platform token
Account Management > **My platform tokens**. To find the minimum permissions for your commands:
`dtctl commands --required-scopes`. For simple queries, `storage:logs:read`, `storage:events:read`,
`storage:metrics:read`, `storage:spans:read`, `storage:entities:read`, `storage:smartscape:read`,
`davis:analyzers:read`, `app-engine:apps:run`, `document:documents:read` are a good starting point.
The `readonly` safety level of dtctl is enforced only on the client side: it is the token that really protects you.

## 2. Configure dtctl (web VS Code terminal)
```bash
dtctl config set-context formation   --environment "https://<environnement>.apps.dynatrace.com"   --token-ref formation-token   --safety-level readonly
dtctl config set-credentials formation-token --token "dt0s16.XXXX.YYYY"
dtctl doctor
```
The configuration is written to `/workspace/mcp/dtctl-config` (variable `DTCTL_CONFIG` already set), the file
that the agent reads. It contains the token: do not share it (ignored by git). If dtctl asks for a current context,
check `dtctl config --help` or set `DTCTL_CONTEXT` in `stack/.env`.

## 3. Verify
Agent page, **Tools** tab: the "dtctl" line must show "ready (read-only)". Then ask a question
about your environment: the trace shows the sub-agent calling `dtctl`, just as it calls the MCP tools.
Commands that modify anything (`apply`, `create`, `edit`, `delete`, `config`, `auth`...) are refused
by the agent.

