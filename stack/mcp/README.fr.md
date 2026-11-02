# Exercice : connecter l'agent à un serveur MCP Dynatrace

[English version](README.md)

Ce dossier (`/workspace/mcp`) est le dossier par défaut du VS Code web (`http://<vm>:8080/`).
L'agent (`http://<vm>/agent.html`) lit le fichier **`mcp.json`** de ce dossier : à vous de le créer.

## 1. Créer un token plateforme dans Dynatrace

1. **Access Tokens** > **Generate new token**.
2. Scopes : `mcp-gateway:servers:invoke` et `mcp-gateway:servers:read`, plus les droits de lecture voulus
   (par exemple `storage:logs:read`, `storage:entities:read`, `storage:metrics:read`, `storage:events:read`,
   `storage:spans:read`, `document:documents:read`, `davis:analyzers:read`, `davis:analyzers:execute`).
3. Copiez le token (`dt0s16.…`), il n'est affiché qu'une fois.

Votre utilisateur doit lui aussi avoir ces permissions : le token ne peut pas faire plus que vous.

## 2. Créer `mcp.json`

Copiez `mcp.json.example` en `mcp.json`, puis remplacez l'URL de votre environnement et le token.
URL du serveur : `https://<environnement>.apps.dynatrace.com/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp`

- `url` : serveur MCP **distant** (HTTP). Les serveurs locaux (stdio) ne sont pas gérés.
- `headers` : en-têtes envoyés au serveur. `${NOM}` est remplacé par la variable d'environnement `NOM`.
- `tools` (facultatif) : liste des outils autorisés. À utiliser : le modèle choisit mieux avec quelques outils, et cela évite les outils qui écrivent dans Dynatrace.

Le fichier contient un secret : il reste sur votre VM (ignoré par git), ne le partagez pas.

## 3. Vérifier

Ouvrez la page de l'agent, onglet **Outils** : une ligne « Serveurs MCP » indique l'état de la connexion
(erreur 401 : token invalide ; 403 : droits manquants, vérifiez `mcp-gateway:servers:invoke`).
Aucun redémarrage n'est nécessaire (rechargement automatique dans la minute).
Puis posez une question, par exemple : « Quels problèmes sont ouverts dans Dynatrace ? ».
Avec OpenLLMetry actif, chaque appel MCP apparaît dans la trace comme un span d'outil.

---

# Exercice : donner dtctl à l'agent

`dtctl` est la ligne de commande de Dynatrace (https://github.com/Dynatrace/dtctl), installée dans le VS Code web et dans
l'image de l'agent. Une fois configurée, l'agent (sous-agent Dynatrace) l'utilise comme outil en **lecture seule**
(`query`, `get`, `describe`, `logs`, `inventory`, `commands`, `exec copilot nl2dql|dql2nl`).

## 1. Créer un token plateforme en lecture seule
Account Management > **My platform tokens**. Pour connaître les droits minimaux de vos commandes :
`dtctl commands --required-scopes`. Pour des requêtes simples, `storage:logs:read`, `storage:events:read`,
`storage:metrics:read`, `storage:spans:read`, `storage:entities:read`, `storage:smartscape:read`,
`davis:analyzers:read`, `app-engine:apps:run`, `document:documents:read` en sont un bon point de départ.
Le niveau de sécurité `readonly` de dtctl n'est appliqué que côté client : c'est le token qui protège vraiment.

## 2. Configurer dtctl (terminal du VS Code web)
```bash
dtctl config set-context formation   --environment "https://<environnement>.apps.dynatrace.com"   --token-ref formation-token   --safety-level readonly
dtctl config set-credentials formation-token --token "dt0s16.XXXX.YYYY"
dtctl doctor
```
La configuration est écrite dans `/workspace/mcp/dtctl-config` (variable `DTCTL_CONFIG` déjà positionnée), le fichier
que lit l'agent. Il contient le token : ne le partagez pas (ignoré par git). Si dtctl demande un contexte courant,
vérifiez `dtctl config --help` ou renseignez `DTCTL_CONTEXT` dans `stack/.env`.

## 3. Vérifier
Page de l'agent, onglet **Outils** : la ligne « dtctl » doit indiquer « prêt (lecture seule) ». Posez ensuite une question
sur votre environnement : la trace montre le sous-agent qui appelle `dtctl`, comme il appelle les outils MCP.
Les commandes qui modifient quoi que ce soit (`apply`, `create`, `edit`, `delete`, `config`, `auth`...) sont refusées
par l'agent.

