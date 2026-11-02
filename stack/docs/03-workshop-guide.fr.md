# Guide de l'atelier : ce qui tourne sur votre VM

[English version](03-workshop-guide.md)

Chaque participant dispose d'une VM Ubuntu 22.04 de taille Standard_B12ms (12 vCPU, 48 Go de mémoire, sans GPU). Tous les services tournent dans des conteneurs Docker, dans le dossier /opt/ai-lab/stack.

## Pages et accès

- `http://<vm>/` : le chat avec recherche dans les documents (RAG)
- `http://<vm>/agent.html` : l'agent IA, qui choisit lui-même ses outils et dont chaque étape est affichée
- `http://<vm>:8080/` : VS Code dans le navigateur (mot de passe de la VM), dossier par défaut /workspace/mcp, avec un chat Continue qui utilise le modèle local

## Services

- `web` : nginx, sert les pages sur le port 80 et relaie les appels /api vers le chat et /agent/api vers l'agent
- `rag-api` : application FastAPI du chat, qui découpe les documents, interroge la base vectorielle, construit le prompt et diffuse la réponse
- `agent-api` : application FastAPI de l'agent (même image que rag-api), avec les outils locaux, le sous-agent Dynatrace, les outils MCP, dtctl et les skills
- `chroma` : base vectorielle ChromaDB, accessible uniquement depuis le réseau Docker
- `ollama` : serveur de modèles, charge qwen2.5:7b pour la génération et nomic-embed-text pour les embeddings
- `ollama-init` : tâche ponctuelle qui télécharge les modèles au premier démarrage
- `vscode` : code-server (VS Code web), avec dtctl, Node.js et dt-evals

## Dossiers de travail (dans VS Code, sous /workspace)

- `mcp` : le fichier mcp.json (serveurs MCP) et la configuration de dtctl que vous créez pour l'agent
- `skills` : les skills Dynatrace (fichiers SKILL.md) que vous choisissez de donner à l'agent
- `evals` : la configuration de dt-evals pour faire noter les réponses du modèle
- `exercices` : le catalogue détaillé des exercices

## Commandes utiles en SSH

- `docker compose ps` dans /opt/ai-lab/stack : état des services
- `docker compose logs -f rag-api` (ou `agent-api`) : journaux de l'application
- `curl localhost/api/health` et `curl localhost/agent/api/health` : état des modèles, de l'indexation, d'OpenLLMetry, de dtctl, des skills et des serveurs MCP
- `sudo scripts/set-openllmetry.sh on <tenant> <token>` : activer OpenLLMetry sur le chat (`off` pour le désactiver)
- `sudo scripts/set-agent-openllmetry.sh on <tenant> <token>` : activer OpenLLMetry sur l'agent
- `sudo scripts/set-rag-context.sh on` : garder les passages RAG dans les traces (nécessaire pour juger la fidélité des réponses)
- `scripts/generate-traffic.sh 10` : envoyer dix questions pour produire des traces
- `scripts/generate-eval-traffic.sh 2` : envoyer un mélange de questions (dont hors documents) à faire juger par dt-evals

## Exercices proposés

Le détail de chaque exercice (objectif, actions, résultats attendus) est dans le dossier `exercices` de VS Code.

- **A. Découvrir le RAG et le modèle** : avec et sans documents, ajouter son document, réglages de génération (température, top K, top P), message système, nombre de passages, limites d'un modèle local, multilingue.
- **B. Observabilité avec OpenLLMetry** : activer OpenLLMetry, lire une trace du chat, comprendre le prompt exporté, mesurer en DQL, diagnostiquer une panne.
- **C. Agent IA** : première tâche d'agent, agent et documents, trace d'un agent, réglages de l'agent.
- **D. Outils externes** : connecter un serveur MCP Dynatrace, interroger Dynatrace via le sous-agent, configurer dtctl, donner des skills à l'agent, comparer les accès.
- **E. Évaluer les réponses avec dt-evals** : préparer, lancer, analyser les notes, créer un évaluateur personnalisé, comparer deux configurations.
- **F. Développer dans VS Code** : modifier la base de connaissances, utiliser le chat Continue, ajouter un outil à l'agent.
