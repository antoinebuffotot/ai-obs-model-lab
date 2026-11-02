# Exercice : donner des skills Dynatrace à l'agent

[English version](README.md)

Une *skill* est un dossier avec un fichier `SKILL.md` (nom, description, instructions) et, parfois, un sous-dossier
`references/`. Les skills de Dynatrace sont publiées dans https://github.com/Dynatrace/dynatrace-for-ai
(dossier `skills/`, une skill par dossier : `dt-dql-essentials`, `dt-obs-logs`, `dt-obs-problems`...).

L'agent (sous-agent Dynatrace) lit **les skills de ce dossier** (`/workspace/skills`) :
- dans son instruction il ne voit que la liste courte (nom + description) ;
- il lit une skill complète avec l'outil `read_skill` quand il en a besoin (avant d'écrire une requête DQL, par exemple).

## À faire

1. Dans le terminal du VS Code web (`http://<vm>:8080/`) :
   ```bash
   cd /tmp && git clone --depth 1 https://github.com/Dynatrace/dynatrace-for-ai
   ls dynatrace-for-ai/skills
   ```
2. **Choisissez** 2 ou 3 skills utiles pour vos questions et copiez-les ici :
   ```bash
   cp -r /tmp/dynatrace-for-ai/skills/dt-dql-essentials /workspace/skills/
   cp -r /tmp/dynatrace-for-ai/skills/dt-obs-logs /workspace/skills/
   ```
   Trop de skills alourdit l'instruction de l'agent : le contexte du modèle est limité.
3. Ouvrez la page de l'agent, onglet **Outils** : la ligne « Skills » indique celles qui sont vues
   (rechargement automatique, aucun redémarrage).
4. Posez une question qui demande une requête DQL, puis comparez avec et sans skill (retirez le dossier) :
   la trace OpenLLMetry montre l'appel `read_skill` et son effet sur les étapes suivantes.

Une skill est tronquée à `SKILL_MAX_CHARS` caractères (6000 par défaut) ; les fichiers de `references/` se lisent
à part. Les skills Dynatrace sont sous licence Apache-2.0 : gardez leur mention de licence si vous les redistribuez.
