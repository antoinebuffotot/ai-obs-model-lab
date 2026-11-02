# Environnement de formation à l'IA (lab-environment-for-ai-training)

[English version](README.md)

Ce script permet de déployer rapidement plusieurs VM Ubuntu avec Docker sur une souscription Azure, pour un atelier / une formation autour de l'IA générative et de son observabilité. Chaque participant dispose de sa propre VM avec :

- un modèle léger **qwen2.5:7b** servi par Ollama (CPU uniquement) ;
- une **interface web de chat** (port 80) avec réponses en streaming, citations cliquables, débit en jetons/s et un panneau de réglages (température, top K, top P, nombre de passages RAG, message système) ;
- des **services RAG** : ChromaDB (base vectorielle), embeddings `nomic-embed-text`, API FastAPI (indexation, recherche, chat) ;
- une **application d'agent IA** (page `/agent.html`) qui utilise le même modèle, appelle des outils et affiche chaque étape ;
- un **VS Code dans le navigateur** (port 8080) avec un chat sur le modèle local, dtctl, Node.js et dt-evals ;
- en option, **OpenLLMetry** (SDK Traceloop) qui envoie vers Dynatrace, via OTLP, les traces et les métriques du chat et de l'agent, pour AI Observability.

Projet inspiré de [lab-environment-for-dynatrace-training](https://github.com/JLLormeau/lab-environment-for-dynatrace-training) : mêmes principes (Azure Cloud Shell, menu interactif, une VM par utilisateur répartie sur 4 régions, script de suppression généré).

```
                       VM Azure Standard_B12ms (Ubuntu 22.04, 12 vCPU / 48 Go)
 navigateur ──80──►  ┌───────────────────────────────────────────────────────────────┐
            ──8080─► │ vscode (code-server)                                          │
                     │ web (nginx) ──► rag-api   (FastAPI, chat RAG) ──► chroma      │
                     │      └────────► agent-api (FastAPI, agent IA) ──► (vecteurs)  │
                     │                      │                                        │
                     │                      └──────────────► ollama                  │
                     │                                       qwen2.5:7b              │
                     │                                       nomic-embed-text        │
                     └──────────────────────────┬────────────────────────────────────┘
                                                │ OpenLLMetry (optionnel) : OTLP/HTTPS
                                                ▼
                                       Dynatrace  /api/v2/otlp
```

La documentation détaillée est dans [ARCHITECTURE.fr.md](ARCHITECTURE.fr.md) (architecture, technologies, flux, observabilité, sécurité) et dans [stack/exercices/README.fr.md](stack/exercices/README.fr.md) (catalogue des exercices avec objectifs, actions et résultats attendus). Les fichiers Markdown existent en anglais (`*.md`, version par défaut) et en français (`*.fr.md`).

Ouvrez votre souscription Azure, <https://portal.azure.com/>, puis le Cloud Shell (Bash).

# Déployer l'environnement de formation

Dans le Cloud Shell, remplacez `<votre-compte>` par le compte GitHub qui héberge ce dépôt :

```
cd;if [ -d "./lab-environment-for-ai-training" ];then rm -rf ./lab-environment-for-ai-training;fi
git clone https://github.com/<votre-compte>/lab-environment-for-ai-training.git
cd lab-environment-for-ai-training;chmod +x ./*.sh
./azure-cli-deploy-vm-for-training-ai.sh
```

## Étape 1 - 20 environnements maximum

```
CONFIGURATION :

0) config env : training name =aitraining
1) config env : password =DummyP@ssword00
2) config env : value first env =00
3) config env : nbr total env =3
4) add env : OpenLLMetry enabled (traces sent to Dynatrace) =N
5) start env : VM started after installation =N
A) apply and deploy the VM - (Ctrl/c to quit)
```

| Option | Rôle |
|---|---|
| 0 | Nom de la formation : préfixe des VM, des groupes de ressources et du DNS (`[a-z]{5}[a-z0-9]+`, ne commence pas par `azure`) |
| 1 | Mot de passe commun (12 caractères minimum, minuscule, majuscule, chiffre, `@` ou `&`), aussi utilisé pour VS Code web |
| 2 | Numéro de la première VM (de 00 à 19) |
| 3 | Nombre de VM à créer (20 maximum au total) |
| 4 | Active OpenLLMetry : le script demande ensuite le tenant et le token Dynatrace, puis la clé du LLM juge (facultative) |
| 5 | `Y` : les VM restent démarrées. `N` : elles sont arrêtées (désallouées) une fois installées |

Les valeurs saisies sont mémorisées dans `.lab-config` (ignoré par git) pour le prochain lancement.

Les environnements sont déployés **en parallèle** (un journal par VM dans `logs/<horodatage>/`). L'installation d'une VM comprend Docker, la construction des images et le téléchargement des modèles : comptez une quinzaine de minutes, selon le débit de téléchargement.

Les VM sont réparties comme dans le projet d'origine, 5 par région :

| VM | Région |
|---|---|
| 00 à 04 | francecentral |
| 05 à 09 | westeurope |
| 10 à 14 | northeurope |
| 15 à 19 | uksouth |

> **Quotas** : une `Standard_B12ms` consomme 12 vCPU. Cinq VM dans une région représentent 60 vCPU, à la fois sur le quota régional (*Total Regional vCPUs*) et sur celui de la famille *Standard BS Family*. Le script affiche ces quotas au démarrage et avertit si la taille n'est pas disponible dans une région. Les régions se changent dans `env.sh`.

## Étape 2 - OpenLLMetry (option 4 = Y)

```
PARAMETER (OpenLLMetry -> Dynatrace) :

0) Tenant (without https://) =abc12345.live.dynatrace.com
1) Token (scope : openTelemetryTrace.ingest) =dt0c01.XXXXX***
2) LLM judge for dt-evals (optional) : provider =openai (openai | anthropic | gemini)
3) LLM judge for dt-evals (optional) : shared API key =sk-pro***
A) apply and deploy the VM - (Ctrl/c to quit)
```

Créez un token d'API Dynatrace pour l'ingestion OpenTelemetry. Selon la [documentation Dynatrace d'OpenLLMetry](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/openllmetry), un token classique a besoin des scopes `openTelemetryTrace.ingest`, `metrics.ingest` et `logs.ingest` (un token plateforme, des scopes `openpipeline:traces:ingest`, `openpipeline:metrics:ingest` et `openpipeline:logs:ingest`). Le token est saisi sans écho et ne sert qu'à renseigner le fichier `.env` des conteneurs sur chaque VM.

Les entrées 2 et 3 sont facultatives : elles définissent le **LLM juge partagé** utilisé par dt-evals (voir `stack/evals/README.fr.md`). La clé est exposée aux participants dans le terminal de leur VS Code web : utilisez une clé à budget limité et révoquez-la après la formation.

Quand l'option est active, l'application suit la configuration documentée par Dynatrace (`Traceloop.init` vers l'endpoint OTLP du tenant, métriques en temporalité `delta`) :

- **l'activité** : pour le chat, `rag.chat` (workflow) avec `rag.retrieve` et `rag.generate` (tâches) ; pour l'agent, `agent.run`, des `agent.step`, un span par outil et, avec un accès Dynatrace, `ask_dynatrace` puis `dynatrace_agent` ;
- **l'appel au modèle** : produit par l'instrumentation Ollama d'OpenLLMetry, avec le modèle, les réglages (température, top K, top P), les jetons d'entrée et de sortie et le mode streaming ;
- **le prompt exporté** : la question de l'utilisateur, le message système et la réponse. L'historique de la conversation et les passages RAG sont envoyés au modèle mais retirés de la trace avant l'export (callback de post-traitement du SDK). Pour garder les passages RAG, par exemple pour l'évaluation par dt-evals : `sudo stack/scripts/set-rag-context.sh on`.

Seule l'instrumentation Ollama est active (ChromaDB et HTTP sont exclus). Les services Dynatrace s'appellent `ai-lab-rag-api-<numéro de la VM>` (chat) et `ai-lab-agent-api-<numéro de la VM>` (agent), avec l'attribut `host.name` portant le FQDN de la VM.

Les traces contiennent le texte des questions et des réponses : n'activez l'option qu'avec un tenant où ces contenus peuvent être stockés. Pour ne plus tracer aucun texte de prompt ni de réponse, mettez `OPENLLMETRY_TRACE_CONTENT=false` dans `stack/.env`.

## Applications et outils de la formation

### Agent IA (page `/agent.html`)

Une seconde page, avec la même interface (langues, réglages, onglet Observability), propose une **application agentique** qui utilise le même modèle local que le chat. L'agent décide seul d'appeler des outils (`search_documents`, `list_documents`, `calculator`, `get_current_time`), lit les résultats et recommence jusqu'à pouvoir répondre (nombre d'étapes limité). Chaque étape et chaque appel d'outil s'affichent.

- Service Docker `agent-api` (même image que `rag-api`, code dans `stack/rag-api/app/agent.py` et `agent_main.py`), joint via nginx sur `/agent/api/`.
- OpenLLMetry suit `OPENLLMETRY_ENABLED` par défaut ; pour l'activer ou le désactiver sur l'agent seul : `sudo stack/scripts/set-agent-openllmetry.sh on <tenant> <token>` / `off`.
- Traces : `agent.run` (@agent) > `agent.step` (@task) > appel LLM Ollama, plus un span par outil (@tool).

### Sous-agent Dynatrace, MCP, dtctl et skills

- **Sous-agent Dynatrace** : quand un accès Dynatrace existe (serveur MCP déclaré ou dtctl configuré), l'agent principal ne reçoit qu'un outil, `ask_dynatrace`. Il délègue à un sous-agent spécialisé (instruction et contexte propres, seuls les outils Dynatrace) qui interroge la plateforme et renvoie un court résumé. L'activité du sous-agent s'affiche dans la carte de l'outil. Traces : `agent.run` > `ask_dynatrace` (@tool) > `dynatrace_agent` (@agent) > étapes LLM et un span par appel d'outil. `MCP_SUBAGENT=false` donne les outils directement à l'agent principal ; `DT_AGENT_MAX_STEPS` limite les étapes du sous-agent (4 par défaut).
- **Outils MCP (exercice participants)** : l'agent lit le fichier `mcp.json` que les participants créent eux-mêmes dans le VS Code web (dossier `/workspace/mcp` = `stack/mcp`, voir `stack/mcp/README.fr.md` et `mcp.json.example`) pour se connecter à un serveur MCP distant, par exemple le serveur MCP Dynatrace. Rechargement automatique, aucun redémarrage.
- **dtctl et skills (exercices participants)** : le sous-agent peut aussi utiliser `dtctl` (CLI Dynatrace, en lecture seule : liste de commandes autorisées, pas de `config`/`apply`/`delete`…) que les participants configurent dans le terminal du VS Code web (`stack/mcp/README.fr.md`), et des *skills* Dynatrace (`SKILL.md` de <https://github.com/Dynatrace/dynatrace-for-ai>) qu'ils copient dans `stack/skills/` (`stack/skills/README.fr.md`). L'agent voit la liste courte des skills et lit une skill avec `read_skill` à la demande. L'état (dtctl, skills) s'affiche dans l'onglet Outils de la page agent.

### Évaluation des réponses avec dt-evals (exercice participants)

Les participants jugent les réponses du modèle avec [dt-evals](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/llm-judge-evaluation) (LLM-as-a-judge sur les traces) depuis le terminal du VS Code web (Node et dt-evals sont dans l'image ; dossier `stack/evals/`, voir `stack/evals/README.fr.md`). Le juge est un modèle externe : le formateur fournit **une clé partagée** (étape 2 du déploiement : fournisseur `openai|anthropic|gemini` et clé, exposée dans le terminal sous le nom de variable du fournisseur). `stack/scripts/generate-eval-traffic.sh` produit des réponses variées (dont hors documents) et `stack/scripts/set-rag-context.sh on|off` garde les passages RAG dans les traces (nécessaire pour juger la fidélité aux sources).

## Réglages du chat

L'onglet **Paramètres** de l'interface web règle, pour la question suivante :

| Réglage | Plage | Défaut | Effet |
|---|---|---|---|
| Température | 0 à 2 | 0,3 | Basse : réponses stables. Haute : réponses plus variées |
| Top K | 1 à 100 | 40 | Nombre de jetons candidats examinés à chaque étape |
| Top P | 0 à 1 | 0,9 | Probabilité cumulée maximale des candidats conservés |
| Passages de documents | 1 à 8 | 3 | Nombre de passages RAG ajoutés au prompt |
| Message système | texte libre | message de l'atelier, dans la langue choisie | Rôle et ton du modèle. Le texte par défaut suit la langue de l'interface tant qu'il n'est pas modifié |

Les réglages sont mémorisés dans le navigateur, et le bouton « Rétablir les valeurs par défaut » les remet à zéro. Le débit et les réglages utilisés s'affichent sous chaque réponse, ce qui permet de comparer. La conversation est conservée quand on passe de la page Chat à la page Agent et inversement.

**Activer ou désactiver OpenLLMetry après coup**, en SSH sur la VM :

```
cd /opt/ai-lab/stack
sudo scripts/set-openllmetry.sh on <tenant> <token>
sudo scripts/set-openllmetry.sh off
```

**Choisir le type de télémétrie** (OpenLLMetry par défaut, ou OpenInference via un OpenTelemetry Collector ; il faut un token classique `dt0c01`) :

```
sudo scripts/set-telemetry-type.sh openinference
sudo scripts/set-telemetry-type.sh openllmetry
```

## Liste des environnements créés

```
ENVIRONMENT : Linux
#User;SSH host;Chat URL;Password
user00;aitraining00.francecentral.cloudapp.azure.com;http://aitraining00.francecentral.cloudapp.azure.com/;DummyP@ssword00
user01;aitraining01.francecentral.cloudapp.azure.com;http://aitraining01.francecentral.cloudapp.azure.com/;DummyP@ssword00
user02;aitraining02.francecentral.cloudapp.azure.com;http://aitraining02.francecentral.cloudapp.azure.com/;DummyP@ssword00
```

## Accès - exemple pour user00 avec le nom de formation `aitraining`

| Service | Accès |
|---|---|
| Chat web | `http://aitraining00.francecentral.cloudapp.azure.com/` |
| Agent IA | `http://aitraining00.francecentral.cloudapp.azure.com/agent.html` |
| VS Code web | `http://aitraining00.francecentral.cloudapp.azure.com:8080/` (mot de passe de la VM) |
| SSH | `ssh user00@aitraining00.francecentral.cloudapp.azure.com` |
| API du chat (via nginx) | `http://aitraining00.francecentral.cloudapp.azure.com/api/health` |
| API de l'agent (via nginx) | `http://aitraining00.francecentral.cloudapp.azure.com/agent/api/health` |

Seuls les ports 22, 80 et 8080 (VS Code web, protégé par le mot de passe de la VM) sont ouverts. Ollama et ChromaDB ne sont joignables que depuis le réseau Docker de la VM : pour les interroger directement (par exemple `curl` sur l'API Ollama), publiez leur port dans `stack/docker-compose.yml` sur `127.0.0.1` et passez par un tunnel SSH.

Si l'option 5 vaut `N`, démarrez les VM depuis le portail Azure avant la formation. La pile redémarre toute seule (`restart: unless-stopped`) ; la première réponse est plus lente car le modèle est rechargé en mémoire.

## Sur la VM

```
cd /opt/ai-lab/stack
docker compose ps                    # état des services
docker compose logs -f rag-api       # journaux de l'API du chat (agent-api pour l'agent)
curl localhost/api/health            # modèles prêts, documents indexés, OpenLLMetry actif ou non
curl localhost/agent/api/health      # idem pour l'agent, avec dtctl, skills et serveurs MCP
scripts/generate-traffic.sh 10       # 10 questions pour produire des traces
sudo tail -f /var/log/ai-lab-setup.log   # journal de l'installation
```

## API du chat (RAG)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/health` | État des modèles, de l'indexation, d'OpenLLMetry et nom du service |
| GET | `/api/settings` | Réglages par défaut du chat et messages système par défaut (par langue) |
| POST | `/api/chat` | Question, historique et réglages (`temperature`, `top_k`, `top_p`, `passages`, `system_prompt`), réponse en streaming SSE (`sources`, `token`, `done`, `error`) |
| POST | `/api/search` | Recherche vectorielle seule, sans génération (champs `query`, `passages`) |
| GET / DELETE | `/api/documents` | Liste et suppression des documents indexés |
| POST | `/api/upload` | Ajout d'un document (.txt, .md, .pdf, 5 Mo maximum) |
| POST | `/api/ingest` | Réindexation des documents d'exemple (`stack/docs/`) |
| GET | `/api/observability/code` | Code de configuration d'OpenLLMetry (onglet Observability) |

L'API de l'agent (`/agent/api/…`) expose `health`, `settings`, `tools`, `observability/code` et `chat` (streaming SSE : `step`, `token`, `tool_call`, `tool_result`, `warning`, `done`, `error`).

Exemple :

```
curl -sN localhost/api/chat -H 'Content-Type: application/json' \
     -d '{"message":"C'"'"'est quoi OpenLLMetry ?","use_rag":true}'
```

Pour changer le contenu de base de l'atelier, ajoutez des fichiers `.md`, `.txt` ou `.pdf` dans `stack/docs/` avant le déploiement : ils sont indexés au premier démarrage de chaque VM (sur une VM existante, utilisez « Réindexer les exemples »). Seuls les fichiers anglais (`*.md`) sont indexés par défaut ; les `*.fr.md` ne le sont que si `DOCS_LANG=fr` (ils remplacent alors les versions anglaises).

## Performances et coûts

- Le modèle tourne **sans GPU** : attendez-vous à quelques jetons par seconde. L'interface affiche le débit réel de chaque réponse, ce qui sert aussi de support pédagogique.
- La première question après un démarrage est plus longue (chargement du modèle en mémoire). Un agent enchaîne plusieurs appels au modèle : une tâche à plusieurs outils peut prendre plusieurs minutes.
- Une `Standard_B12ms` est une VM coûteuse : arrêtez-les (option 5 = `N`, ou depuis le portail) entre deux sessions et supprimez-les en fin de formation.
- Pour changer de modèle, modifiez `LLM_MODEL` dans `env.sh` (par exemple un autre modèle de la bibliothèque Ollama). Les messages système par défaut sont dans `stack/rag-api/app/rag.py` (chat) et `agent.py` (agent).

## Dernière étape - Supprimer les groupes de ressources

À la fin, utilisez le script généré dans le répertoire du projet pour nettoyer la souscription :

```
./delete_resourcegroup_aitraining_<horodatage>.sh
```

Il supprime les groupes de ressources créés (`az group delete --no-wait`) et contient en commentaire la liste des comptes.

## Structure du dépôt

```
azure-cli-deploy-vm-for-training-ai.sh   script principal et menu
azuredeploy-ubuntu22.json                template ARM (VM, IP publique statique + DNS, NSG 22/80/8080)
vm-setup.sh                              installation sur la VM (Docker, pile IA), exécuté via az vm run-command
env.sh                                   taille de VM, régions, modèles, valeurs par défaut
ARCHITECTURE.md  README.md               documentation (anglais : *.md, français : *.fr.md)
stack/
  docker-compose.yml                     ollama, ollama-init, chroma, rag-api, agent-api, web, vscode
  nginx.conf                             reverse proxy (streaming SSE)
  web/                                   index.html (chat), agent.html (agent), common.css, common.js
  rag-api/                               image Python partagée : chat RAG, agent, MCP, dtctl, skills, OpenLLMetry
  vscode/                                code-server (Continue, dtctl, Node.js, dt-evals)
  docs/                                  documents d'exemple indexés au démarrage (seuls les fichiers anglais *.md sont indexés par défaut, voir DOCS_LANG)
  mcp/  skills/  evals/                  espaces de travail des exercices participants
  exercices/                             catalogue des exercices
  scripts/                               scripts OpenLLMetry (chat, agent), contexte RAG, génération de trafic
```

Le dossier `stack/` est embarqué dans le script envoyé à chaque VM : le dépôt peut donc être privé et vos modifications locales sont prises en compte au déploiement suivant.

## Dépannage

| Symptôme | Piste |
|---|---|
| `QuotaExceeded` / `SkuNotAvailable` | Quota vCPU insuffisant ou `Standard_B12ms` indisponible dans la région : changez les régions dans `env.sh` ou demandez une augmentation de quota |
| Environnement `FAILED` ou `setup not confirmed` | Lisez `logs/<horodatage>/<env>.log`, puis `/var/log/ai-lab-setup.log` sur la VM (la VM est laissée démarrée dans ce cas) |
| Le chat affiche « le modèle se télécharge » | Le téléchargement n'est pas fini : `docker compose logs ollama-init` |
| Pas de traces dans Dynatrace | `curl localhost/api/health` doit renvoyer `"openllmetry":true` ; sinon vérifiez tenant et token (`docker compose logs rag-api`) |
| La page agent affiche « Service injoignable » ou `502` | `agent-api` n'est pas démarré : `docker compose up -d agent-api web`, puis `docker compose logs agent-api` |
| L'agent n'utilise pas les outils MCP | `curl localhost/agent/api/health` : lisez l'état de chaque serveur dans `mcp` (401 : token ; 403 : droits `mcp-gateway:*` ; sinon réseau) ; limitez les outils avec `"tools"` dans `mcp.json` |
| Réponses de l'agent coupées | Fenêtre de contexte pleine : alerte orange dans la page ; augmentez `AGENT_NUM_CTX` ou réduisez les outils |
| Pastille dtctl rouge sur la page agent | dtctl n'est pas dans l'image du service `agent-api` (installer dtctl dans le terminal VS Code ne change que le conteneur VS Code). Reconstruisez : `docker compose build --no-cache agent-api vscode && docker compose up -d`, puis cherchez `dtctl ... installed` ou `WARNING` dans la sortie de construction ; vérifiez avec `docker compose exec agent-api dtctl --help`. Orange = installé mais `dtctl-config` absent |
| L'agent ne remonte qu'une partie d'une liste (par exemple 1 problème sur 4) | Regardez la carte de l'outil dans la page : si le résultat contient tous les éléments, c'est le modèle qui résume mal (demandez la liste complète, utilisez moins d'outils MCP) ; s'il se termine par `result truncated`, le résultat dépasse `TOOL_RESULT_CHARS` (6000 par défaut) : augmentez-le dans `stack/.env` (et `AGENT_NUM_CTX`), ou posez une question plus ciblée |
