# Exercise: judge the model's answers with dt-evals

[Version française](README.fr.md)

[dt-evals](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/llm-judge-evaluation)
reads the GenAI spans of your service in Dynatrace (those from OpenLLMetry), asks an **LLM judge** to score them
(faithfulness to sources, relevance, hallucination, toxicity...) and writes the scores to Dynatrace, with the link to
the trace. The results are displayed in **AI Observability > Evaluations** (Preview feature).

The judge is **not** the local model: it is an external model (OpenAI by default) with a **shared key provided by the
trainer**. It is already available in the VS Code web terminal. It is shared and budget-limited: keep
the sample small (`--sample`) and do not copy it elsewhere. The content of the evaluated traces is sent to the judge's provider
(dt-evals first masks emails, phone numbers, credit cards, social security numbers).

## 0. Prepare (once)

1. **OpenLLMetry must be active** on your VM (deployed with the option, or `sudo stack/scripts/set-openllmetry.sh on <tenant> <token>`).
2. **Keep the RAG passages in the traces.** By default, they are removed from the traces. To judge *faithfulness* to the documents,
   the judge must see them (over SSH on the VM):
   ```bash
   sudo /opt/ai-lab/stack/scripts/set-rag-context.sh on
   ```
   (`off` to return to the default behavior). The conversation history is never exported.
3. **Create a platform token** (Account Management > My platform tokens) with these scopes:
   `storage:spans:read`, `storage:buckets:read`, `storage:bizevents:read`, `storage:logs:read`,
   `storage:events:write`, `storage:metrics:write`. The two `write` scopes are used to write the evaluation results.

## 1. Generate answers to judge

In the VS Code web terminal (`http://<vm>:8080/`):
```bash
/workspace/scripts/generate-eval-traffic.sh 2 http://web
```
The script sends a mix of questions: covered by the documents, **outside the documents** (to provoke hallucinations),
in other languages, with and without RAG. Wait a minute for the traces to arrive in Dynatrace.

## 2. Configure dt-evals

```bash
cd /workspace/evals
export DT_API_TOKEN="dt0s16...."          # the token created in step 0 (or: dt-evals doctor)
curl -s http://web/api/health | grep -o '"service":"[^"]*"'    # the name of your service, e.g. ai-lab-rag-api-03
dt-evals doctor
dt-evals configure                         # URL (DT_ENV_URL is already computed), judge provider, service to evaluate
dt-evals validate
```
`dt-eval.yaml.example` shows the shape of the `.dt-eval.yaml` file; the `configure` wizard remains the reference.
The service to evaluate is the one on **your VM** (`ai-lab-rag-api-NN` for the chat, `ai-lab-agent-api-NN` for the agent).

## 3. Run the evaluation

```bash
dt-evals run --since 1h --sample 20 --dry-run     # what would be evaluated, without calling the judge
dt-evals run --since 1h --sample 20
dt-evals runs list
```
If `--dry-run` finds no span or no content, the fields do not match: see `scope.spanFields` in the docs
(mapping between your attributes and the expected `gen_ai.*` fields).

## 4. Read the results

- **AI Observability > Evaluations**: pass rate, average scores, distributions, drift. Click a result to open the trace.
- In DQL:
  ```
  fetch bizevents
  | filter event.type == "gen_ai.evaluation.result"
  | sort timestamp desc
  | limit 20
  ```
Questions to ask yourself: which answers are poorly scored? Do questions outside the documents produce hallucination?
With RAG and without RAG, what is the faithfulness gap? Is the judge's explanation right?

## 5. Create a custom evaluator

`dt-evals evaluators add` creates an LLM-judge evaluator from a criterion. Two ideas that reflect the chat's system message:
- **Citations**: "Does the answer cite the documents used in square brackets, for example [1], when passages are provided?"
- **Language**: "Is the answer written in the same language as the question?"

Check it with `dt-evals evaluators show <name>` and `dt-evals evaluators test <name>`, then add its name to the
`metrics.enabled` list in `.dt-eval.yaml` and rerun `dt-evals run`.

## 6. Compare (to go further)

Change the temperature or the system message in the interface, regenerate traffic (step 1), rerun the evaluation and compare
the scores (the *drift* compares recent scores with those of the last 7 days). `dt-evals run --ci` returns an error if
a score falls below its threshold: this is the building block for an automated quality check.

## Good to know
- dt-evals has no built-in scheduler: run it by hand, or from your own CI.
- A small model sometimes judges poorly: read the explanation of the score before trusting it.
- The Evaluations table is in Preview and may change.
