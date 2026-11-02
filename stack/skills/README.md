# Exercise: give Dynatrace skills to the agent

[Version française](README.fr.md)

A *skill* is a folder with a `SKILL.md` file (name, description, instructions) and, sometimes, a `references/`
subfolder. The Dynatrace skills are published in https://github.com/Dynatrace/dynatrace-for-ai
(`skills/` folder, one skill per folder: `dt-dql-essentials`, `dt-obs-logs`, `dt-obs-problems`...).

The agent (Dynatrace sub-agent) reads **the skills in this folder** (`/workspace/skills`):
- in its instruction it only sees the short list (name + description);
- it reads a full skill with the `read_skill` tool when it needs it (before writing a DQL query, for example).

## To do

1. In the web VS Code terminal (`http://<vm>:8080/`):
   ```bash
   cd /tmp && git clone --depth 1 https://github.com/Dynatrace/dynatrace-for-ai
   ls dynatrace-for-ai/skills
   ```
2. **Choose** 2 or 3 skills useful for your questions and copy them here:
   ```bash
   cp -r /tmp/dynatrace-for-ai/skills/dt-dql-essentials /workspace/skills/
   cp -r /tmp/dynatrace-for-ai/skills/dt-obs-logs /workspace/skills/
   ```
   Too many skills make the agent's instruction heavier: the model's context is limited.
3. Open the agent page, **Tools** tab: the "Skills" line shows which ones are seen
   (automatic reload, no restart).
4. Ask a question that requires a DQL query, then compare with and without a skill (remove the folder):
   the OpenLLMetry trace shows the `read_skill` call and its effect on the following steps.

A skill is truncated to `SKILL_MAX_CHARS` characters (6000 by default); the files in `references/` are read
separately. Dynatrace skills are licensed under Apache-2.0: keep their license notice if you redistribute them.
