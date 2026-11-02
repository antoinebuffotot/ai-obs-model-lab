# Catalogue des exercices

[English version](README.md)

Six blocs, du plus simple au plus avancé. Chaque exercice indique l'objectif, les actions du participant et le résultat attendu,
dans l'application web et/ou dans Dynatrace. Les guides détaillés des exercices D (MCP, dtctl, skills) et E (dt-evals) sont dans
`/workspace/mcp/README.fr.md`, `/workspace/skills/README.fr.md` et `/workspace/evals/README.fr.md`.

**Prérequis communs.** OpenLLMetry est actif sur la VM pour les blocs B à E. Les accès Dynatrace (token d'ingestion, tokens
plateforme) sont fournis ou créés par les participants selon l'exercice. Dans le terminal du VS Code web, le chat est joignable
sur `http://web`.

**Déroulé conseillé (une journée).** Matin : A (45 min), B1 à B4 (60 min), C (45 min). Après-midi : D1 à D3 ou D4 (60 à 90 min),
E1 à E4 (60 min), puis B5, D6 ou F pour les plus rapides.

---

## Bloc A. Découvrir le RAG et le modèle (sans Dynatrace)

### A1. RAG avec et sans documents
- **Objectif** : comprendre ce que le RAG apporte.
- **Actions** : poser la même question avec « Chercher dans les documents » coché, puis décoché.
- **Résultat** : *Web* : avec RAG, la réponse cite des passages numérotés (`[1]`) et affiche « Passages utilisés » avec un score de
  pertinence ; sans RAG, aucune source et des réponses plus générales.

### A2. Ajouter son propre document
- **Objectif** : voir l'indexation en action.
- **Actions** : onglet Documents, « Ajouter un document » (`.txt`, `.md`, `.pdf`), poser une question sur son contenu ; le retirer
  et reposer la question.
- **Résultat** : *Web* : le nombre de passages indexés s'affiche, la réponse cite le nouveau document, puis ne le cite plus après retrait.

### A3. Paramètres de génération
- **Objectif** : comprendre température, top K et top P.
- **Actions** : onglet Paramètres, poser 3 fois la même question avec des valeurs très différentes.
- **Résultat** : *Web* : réponses plus stables ou plus variées ; la ligne de réglages sous chaque réponse permet de comparer.

### A4. Message système
- **Objectif** : orienter le comportement du modèle.
- **Actions** : modifier le message système (« réponds en une phrase », changer le ton), changer la langue de l'interface,
  rétablir les valeurs par défaut.
- **Résultat** : *Web* : style de réponse modifié. Le texte par défaut passe dans la langue choisie tant qu'il n'a pas été édité ;
  un texte modifié est conservé.

### A5. Nombre de passages et pertinence
- **Objectif** : mesurer le compromis entre contexte et latence.
- **Actions** : faire varier « Passages de documents » de 1 à 8 ; cliquer sur les `[n]` pour ouvrir les passages.
- **Résultat** : *Web* : plus de contexte mais une réponse plus lente avec 8 passages ; chaque citation ouvre et surligne son passage.

### A6. Limites d'un modèle local sur CPU
- **Objectif** : situer les performances d'un petit modèle sans GPU.
- **Actions** : poser une question hors documents, lire le débit affiché.
- **Résultat** : *Web* : jetons par seconde et temps total ; le modèle indique que la réponse ne vient pas des documents.

### A7. Multilingue
- **Objectif** : vérifier que le modèle suit la langue de la question.
- **Actions** : choisir l'une des 5 langues, poser une question dans une autre langue, passer de la page Chat à la page Agent.
- **Résultat** : *Web* : réponse dans la langue de la question ; la conversation est retrouvée en revenant sur la page.

---

## Bloc B. Observabilité avec OpenLLMetry

### B1. Activer OpenLLMetry
- **Objectif** : brancher l'application sur Dynatrace.
- **Actions** : en SSH, `sudo scripts/set-openllmetry.sh on <tenant> <token>`, puis poser une question.
- **Résultat** : *Web* : pastille « OpenLLMetry : actif ». *Dynatrace* : un service `ai-lab-rag-api-NN` (NN = numéro de la VM).
  L'onglet Observability de la page web montre le code de configuration.

### B2. Lire une trace du chat
- **Objectif** : suivre les étapes d'une question.
- **Actions** : ouvrir la trace d'une question dans Distributed Tracing ou AI Observability.
- **Résultat** : *Dynatrace* : `rag.chat` contient `rag.retrieve` (avec l'appel d'embedding) et `rag.generate` (avec l'appel au modèle).
  Le span du modèle porte le nom du modèle, la température, le top K, les jetons et le mode streaming.

### B3. Ce que la trace montre du prompt
- **Objectif** : discuter de la confidentialité des prompts.
- **Actions** : lire les entrées du span du modèle et comparer avec ce que le modèle a réellement reçu.
- **Résultat** : *Dynatrace* : la question, le message système et la réponse sont visibles ; ni l'historique ni les passages RAG.
  Le nombre de jetons d'entrée est plus grand que le prompt visible : à expliquer.

### B4. Impact des réglages sur la trace
- **Objectif** : relier réglages, durée et jetons.
- **Actions** : changer température, top K et nombre de passages, poser des questions, comparer les spans.
- **Résultat** : *Dynatrace* : les attributs de requête changent et la durée de `rag.generate` varie avec le nombre de jetons.

### B5. Mesurer en DQL
- **Objectif** : exploiter les traces comme des données.
- **Actions** : générer du trafic (`scripts/generate-traffic.sh 10`), écrire des requêtes DQL sur les spans de son service (latence par
  étape, jetons par minute) et les épingler dans un dashboard.
- **Résultat** : *Dynatrace* : un dashboard personnel avec latence, jetons et volume.

### B6. Provoquer et diagnostiquer une panne *(à vérifier sur un vrai tenant)*
- **Objectif** : reconnaître une défaillance dans la télémétrie.
- **Actions** : en SSH, `docker compose stop ollama`, poser une question, puis `docker compose start ollama`.
- **Résultat** : *Web* : message d'erreur ou « Service injoignable ». *Dynatrace* : un span en erreur, avec l'exception probablement visible.

---

## Bloc C. Agent IA (page `/agent.html`)

### C1. Première tâche d'agent
- **Objectif** : voir une boucle d'outils.
- **Actions** : tâche « Calcule (1250 * 1.2) + 340, puis donne la date et l'heure actuelles ».
- **Résultat** : *Web* : chaque étape, les appels à `calculator` et `get_current_time` avec leurs résultats, puis la réponse finale.

### C2. Agent et documents
- **Objectif** : comparer un agent et un chat RAG.
- **Actions** : tâche « Quels documents sont disponibles, et que dit celui sur OpenLLMetry ? », puis la même question dans le chat.
- **Résultat** : *Web* : l'agent appelle `list_documents` puis `search_documents`, là où le chat fait une seule recherche.

### C3. Activer OpenLLMetry sur l'agent et lire sa trace
- **Objectif** : observer un agent.
- **Actions** : `sudo scripts/set-agent-openllmetry.sh on <tenant> <token>`, lancer C1 et C2, ouvrir les traces.
- **Résultat** : *Dynatrace* : un service `ai-lab-agent-api-NN` avec `agent.run`, des `agent.step` (un appel au modèle chacun) et un
  span par outil. Il y a plus d'appels au modèle que pour le chat.

### C4. Régler l'agent
- **Objectif** : comprendre les garde-fous.
- **Actions** : réduire « Étapes maximum » à 1 ou 2, changer l'instruction de l'agent, modifier la température.
- **Résultat** : *Web* : à la dernière étape l'agent doit répondre sans outil. Une alerte orange apparaît si la fenêtre de contexte est
  presque pleine ou si la réponse est coupée.

---

## Bloc D. Outils externes : MCP, sous-agent, dtctl, skills

### D1. Connecter un serveur MCP Dynatrace
- **Objectif** : ajouter des outils à un agent par configuration.
- **Actions** : créer un token plateforme avec `mcp-gateway:servers:invoke` et `read`, créer `mcp.json` depuis l'exemple dans
  `/workspace/mcp`, ouvrir l'onglet Outils.
- **Résultat** : *Web* : l'état de chaque serveur MCP et les outils découverts ; une erreur 401 ou 403 s'explique dans l'onglet.

### D2. Interroger Dynatrace via le sous-agent
- **Objectif** : voir un agent qui en appelle un autre.
- **Actions** : tâche « Quels problèmes sont ouverts ? ».
- **Résultat** : *Web* : une carte `ask_dynatrace` contient l'activité du sous-agent (ses étapes et ses appels MCP). *Dynatrace* :
  `agent.run` > `ask_dynatrace` > `dynatrace_agent` > spans des outils MCP.

### D3. Limiter les outils MCP
- **Objectif** : réduire le contexte et améliorer le choix des outils.
- **Actions** : ajouter `"tools": [...]` dans `mcp.json`, comparer avant et après.
- **Résultat** : *Web* : moins d'outils, moins d'alertes de contexte, de meilleurs choix.

### D4. Configurer dtctl
- **Objectif** : donner une ligne de commande à l'agent.
- **Actions** : dans le terminal, `dtctl config set-context … --safety-level readonly`, `set-credentials …`, `dtctl doctor`, puis une
  question sur son environnement.
- **Résultat** : *Web* : pastille dtctl verte et outil listé. *Dynatrace* : un span d'outil `dtctl` sous le sous-agent. Les commandes
  qui modifient quoi que ce soit sont refusées. *(à vérifier : sélection du contexte courant de dtctl)*

### D5. Donner des skills à l'agent
- **Objectif** : apporter de la connaissance sans alourdir le contexte.
- **Actions** : cloner `dynatrace-for-ai`, copier 2 ou 3 skills dans `/workspace/skills`, poser une question qui demande du DQL, retirer
  les skills et comparer.
- **Résultat** : *Web* : ligne « Skills : N ». *Dynatrace* : un span `read_skill` suivi d'étapes différentes ; les requêtes sont en
  général meilleures avec la skill.

### D6. Comparer MCP, dtctl et skills
- **Objectif** : choisir le bon mode d'accès.
- **Actions** : poser la même question avec chacun seul (retirer `mcp.json`, `dtctl-config` ou les skills), puis avec les trois.
- **Résultat** : *Dynatrace* : comparer durée, nombre d'étapes et exactitude des réponses entre les configurations.

### D7. Sous-agent ou agent direct *(avancé, accès SSH)*
- **Objectif** : mesurer l'intérêt du sous-agent.
- **Actions** : mettre `MCP_SUBAGENT=false` dans `.env`, recréer `agent-api`, refaire D2.
- **Résultat** : *Dynatrace* : les outils MCP apparaissent directement sous l'agent principal, avec plus de contexte consommé et
  souvent une réponse moins bonne.

---

## Bloc E. Évaluer les réponses avec dt-evals

### E1. Préparer l'évaluation
- **Objectif** : réunir ce qu'il faut pour juger.
- **Actions** : en SSH, `sudo scripts/set-rag-context.sh on` ; créer un token plateforme (lecture des spans, écriture des événements et
  métriques) ; `scripts/generate-eval-traffic.sh 2 http://web`.
- **Résultat** : *Dynatrace* : des traces avec les passages RAG visibles dans le prompt. *Terminal* : `dt-evals doctor` au vert.

### E2. Lancer une évaluation
- **Objectif** : obtenir des notes sur ses propres traces.
- **Actions** : `dt-evals configure` (service `ai-lab-rag-api-NN`), `run --dry-run`, puis `run --since 1h --sample 20`.
- **Résultat** : *Dynatrace* : résultats dans AI Observability > Evaluations et en DQL (`gen_ai.evaluation.result`), avec score,
  explication et lien vers la trace. *(à vérifier : que dt-evals lit les attributs de nos spans)*

### E3. Analyser les notes
- **Objectif** : interpréter un juge.
- **Actions** : identifier les réponses mal notées ; comparer questions hors documents et dans les documents, avec et sans RAG.
- **Résultat** : *Dynatrace* : les questions hors documents sont plus souvent notées en hallucination ; les explications du juge sont à
  lire avec esprit critique.

### E4. Créer un évaluateur personnalisé
- **Objectif** : mesurer un critère propre au projet.
- **Actions** : `dt-evals evaluators add` pour « cite-t-il ses sources entre crochets ? » et « répond-il dans la langue de la question ? »,
  `test`, puis l'ajouter à la configuration.
- **Résultat** : *Dynatrace* : de nouveaux scores dans l'onglet Evaluations pour ces deux critères.

### E5. Comparer deux configurations et contrôler la qualité
- **Objectif** : détecter une dérive de qualité.
- **Actions** : changer la température ou le message système, regénérer du trafic, relancer, comparer ; essayer `--ci` avec des seuils.
- **Résultat** : *Dynatrace* : scores moyens et dérive différents entre les deux séries. *Terminal* : échec quand un score passe sous son seuil.

### E6. Évaluer l'agent *(non testé)*
- **Objectif** : juger un agent, pas seulement un chat.
- **Actions** : refaire E2 avec `ai-lab-agent-api-NN`.
- **Résultat** : *Dynatrace* : notes sur les réponses finales de l'agent, selon la façon dont dt-evals lit les spans de l'agent.

---

## Bloc F. Développer dans VS Code web (`http://<vm>:8080/`)

### F1. Modifier la base de connaissances
- **Objectif** : voir l'effet d'un document sur les réponses.
- **Actions** : éditer un fichier de `/workspace/docs`, cliquer « Réindexer les exemples » dans le web, reposer la question.
- **Résultat** : *Web* : le nouveau contenu apparaît dans les passages cités.

### F2. Utiliser le chat Continue avec le modèle local
- **Objectif** : voir un usage non tracé du même modèle.
- **Actions** : demander à Continue d'expliquer `telemetry.py`.
- **Résultat** : Continue répond avec `qwen2.5:7b`. *Dynatrace* : cet appel n'apparaît pas, ce qui permet de discuter des usages non observés.

### F3. Ajouter un outil à l'agent *(avancé, accès SSH)*
- **Objectif** : comprendre comment un outil devient un span.
- **Actions** : ajouter une fonction décorée `@tool` dans `agent.py` et son schéma, reconstruire (`docker compose up -d --build agent-api`),
  la déclencher avec une tâche.
- **Résultat** : *Web* : le nouvel outil dans l'onglet Outils et ses appels. *Dynatrace* : un nouveau span d'outil.

---

## Points que le formateur doit préparer
- Un tenant avec AI Observability, des tokens d'ingestion (OpenLLMetry) et, pour les blocs D et E, la possibilité pour les participants
  de créer des tokens plateforme (scopes MCP, lecture de données, écriture des événements et métriques pour dt-evals).
- La clé du LLM juge partagée (menu du script de déploiement), avec un plafond de dépense.
- Pour le bloc D : les droits `mcp-gateway:*` des participants.

## Ce qui n'a pas été vérifié de bout en bout
Les blocs D et E ont été testés avec des simulations (faux modèle, faux serveur MCP, faux dtctl), pas avec un vrai tenant : à répéter une
fois avant la formation. Les exercices B6 et E6 ne reposent que sur le comportement attendu.
