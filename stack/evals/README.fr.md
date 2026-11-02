# Exercice : juger les réponses du modèle avec dt-evals

[English version](README.md)

[dt-evals](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/llm-judge-evaluation)
lit les spans GenAI de votre service dans Dynatrace (ceux d'OpenLLMetry), demande à un **LLM juge** de les noter
(fidélité aux sources, pertinence, hallucination, toxicité...) et écrit les notes dans Dynatrace, avec le lien vers
la trace. Les résultats s'affichent dans **AI Observability > Evaluations** (fonction en Preview).

Le juge n'est **pas** le modèle local : c'est un modèle externe (OpenAI par défaut) avec une **clé partagée fournie par le
formateur**. Elle est déjà disponible dans le terminal du VS Code web. Elle est partagée et limitée en budget : gardez un
échantillon petit (`--sample`) et ne la copiez pas ailleurs. Le contenu des traces évaluées part chez le fournisseur du juge
(dt-evals masque d'abord les e-mails, téléphones, cartes bancaires, numéros de sécurité sociale).

## 0. Préparer (une fois)

1. **OpenLLMetry doit être actif** sur votre VM (déployé avec l'option, ou `sudo stack/scripts/set-openllmetry.sh on <tenant> <token>`).
2. **Garder les passages RAG dans les traces.** Par défaut, ils sont retirés des traces. Pour juger la *fidélité* aux documents,
   le juge doit les voir (en SSH sur la VM) :
   ```bash
   sudo /opt/ai-lab/stack/scripts/set-rag-context.sh on
   ```
   (`off` pour revenir au comportement par défaut). L'historique de conversation n'est jamais exporté.
3. **Créer un token plateforme** (Account Management > My platform tokens) avec ces scopes :
   `storage:spans:read`, `storage:buckets:read`, `storage:bizevents:read`, `storage:logs:read`,
   `storage:events:write`, `storage:metrics:write`. Les deux scopes `write` servent à écrire les résultats d'évaluation.

## 1. Générer des réponses à juger

Dans le terminal du VS Code web (`http://<vm>:8080/`) :
```bash
/workspace/scripts/generate-eval-traffic.sh 2 http://web
```
Le script envoie un mélange de questions : couvertes par les documents, **hors documents** (pour provoquer des hallucinations),
en d'autres langues, avec et sans RAG. Attendez une minute que les traces arrivent dans Dynatrace.

## 2. Configurer dt-evals

```bash
cd /workspace/evals
export DT_API_TOKEN="dt0s16...."          # le token créé à l'étape 0 (ou : dt-evals doctor)
curl -s http://web/api/health | grep -o '"service":"[^"]*"'    # le nom de votre service, ex. ai-lab-rag-api-03
dt-evals doctor
dt-evals configure                         # URL (DT_ENV_URL est déjà calculée), fournisseur du juge, service à évaluer
dt-evals validate
```
`dt-eval.yaml.example` montre la forme du fichier `.dt-eval.yaml` ; l'assistant `configure` reste la référence.
Le service à évaluer est celui de **votre VM** (`ai-lab-rag-api-NN` pour le chat, `ai-lab-agent-api-NN` pour l'agent).

## 3. Lancer l'évaluation

```bash
dt-evals run --since 1h --sample 20 --dry-run     # ce qui serait évalué, sans appeler le juge
dt-evals run --since 1h --sample 20
dt-evals runs list
```
Si `--dry-run` ne trouve aucun span ou aucun contenu, les champs ne correspondent pas : voir `scope.spanFields` dans la doc
(correspondance entre vos attributs et les champs `gen_ai.*` attendus).

## 4. Lire les résultats

- **AI Observability > Evaluations** : taux de réussite, scores moyens, distributions, dérive. Cliquez un résultat pour ouvrir la trace.
- En DQL :
  ```
  fetch bizevents
  | filter event.type == "gen_ai.evaluation.result"
  | sort timestamp desc
  | limit 20
  ```
Questions à se poser : quelles réponses sont mal notées ? Les questions hors documents donnent-elles de l'hallucination ?
Avec RAG et sans RAG, quel écart de fidélité ? L'explication du juge est-elle juste ?

## 5. Créer un évaluateur personnalisé

`dt-evals evaluators add` crée un évaluateur LLM-juge à partir d'un critère. Deux idées qui reflètent le message système du chat :
- **Citations** : « La réponse cite-t-elle les documents utilisés entre crochets, par exemple [1], quand des passages sont fournis ? »
- **Langue** : « La réponse est-elle rédigée dans la même langue que la question ? »

Vérifiez-le avec `dt-evals evaluators show <nom>` et `dt-evals evaluators test <nom>`, puis ajoutez son nom à la liste
`metrics.enabled` de `.dt-eval.yaml` et relancez `dt-evals run`.

## 6. Comparer (pour aller plus loin)

Changez la température ou le message système dans l'interface, regénérez du trafic (étape 1), relancez l'évaluation et comparez
les scores (la *dérive* compare les scores récents à ceux des 7 derniers jours). `dt-evals run --ci` retourne une erreur si
un score passe sous son seuil : c'est la brique pour un contrôle qualité automatique.

## À savoir
- dt-evals n'a pas de planificateur intégré : lancez-le à la main, ou depuis votre propre CI.
- Un petit modèle juge parfois mal : lisez l'explication de la note avant de la croire.
- Le tableau Evaluations est en Preview et peut changer.
