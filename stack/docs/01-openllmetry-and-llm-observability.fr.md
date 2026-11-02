# OpenLLMetry et observabilité des applications LLM

[English version](01-openllmetry-and-llm-observability.md)

OpenLLMetry est un projet open source (Traceloop) qui ajoute à OpenTelemetry l'instrumentation des applications d'IA générative. Il s'installe avec le SDK Traceloop et produit des traces, des métriques et des logs au format OpenTelemetry (OTLP).

## Ce que le SDK sait faire

Par défaut, le SDK détecte les bibliothèques d'IA présentes dans l'application (clients de modèles, bases vectorielles, frameworks d'orchestration) et transforme chaque appel en span, avec le nom du modèle, le nombre de jetons, la durée et, si on l'autorise, le texte des prompts et des réponses.

## Ce que trace cet atelier

L'atelier utilise la configuration documentée par Dynatrace (Traceloop.init vers l'endpoint OTLP du tenant, temporalité delta), avec l'instrumentation Ollama du SDK et des décorateurs OpenLLMetry pour décrire l'activité de l'application. Les ajouts propres à l'atelier se limitent à un masquage de données avant l'envoi.

- **le chat** (service `ai-lab-rag-api-NN`, NN étant le numéro de la VM) : un workflow `rag.chat` et ses deux étapes, `rag.retrieve` (embedding de la question puis recherche dans ChromaDB) et `rag.generate` (appel au modèle qwen2.5:7b). La durée de chaque span montre où le temps passe ;
- **l'agent** (service `ai-lab-agent-api-NN`) : un span `agent.run`, une série de spans `agent.step` (un appel au modèle chacun), un span par outil appelé (`calculator`, `search_documents`, `dtctl`, `read_skill`...) et, avec un serveur MCP ou dtctl, `ask_dynatrace` puis `dynatrace_agent` pour le sous-agent Dynatrace ;
- **l'appel au modèle** : produit par l'instrumentation Ollama d'OpenLLMetry. Le span porte le nom du modèle, les réglages de la requête (température, top K, top P), le nombre de jetons d'entrée, de sortie et le total, et le mode streaming.

## Ce que le prompt exporté contient

Le span de l'appel au modèle montre la **question de l'utilisateur**, le **message système** et la **réponse** du modèle. L'**historique de la conversation** et les **passages de documents du RAG** sont envoyés au modèle mais retirés du span avant l'export, par un callback de post-traitement du SDK (span_postprocess_callback). Le nombre de jetons d'entrée les compte quand même : il est donc plus grand que le prompt visible dans la trace.

Pour garder les passages RAG dans les traces (par exemple pour juger la fidélité des réponses avec dt-evals), un administrateur lance `sudo scripts/set-rag-context.sh on` sur la VM. L'historique n'est jamais exporté.

## Dans cet atelier

L'application est écrite en Python (FastAPI). Quand l'option OpenLLMetry est activée au déploiement (ou avec `scripts/set-openllmetry.sh` pour le chat et `scripts/set-agent-openllmetry.sh` pour l'agent), le SDK Traceloop est initialisé au démarrage et envoie les traces et les métriques vers l'endpoint OTLP du tenant Dynatrace. Quand l'option est désactivée, l'application fonctionne de la même façon mais n'émet aucune télémétrie.

Changer la température, le top K, le top P ou le message système dans l'interface modifie les réglages visibles dans la trace de la question suivante. Dans Dynatrace, les traces apparaissent dans les traces distribuées et dans AI Observability, et l'outil dt-evals permet de faire noter les réponses par un LLM juge.
