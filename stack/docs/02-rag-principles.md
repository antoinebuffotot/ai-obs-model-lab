# RAG principles (Retrieval-Augmented Generation)

[Version française](02-rag-principles.fr.md)

RAG consists of giving the model the right document excerpts at the time of answering, instead of relying only on what it learned during training.

## Step 1: index the documents

Documents are split into passages of about 900 characters, with a slight overlap so that an idea is not cut in two. Each passage is turned into a vector by an embedding model (here nomic-embed-text), then stored in a vector database (here ChromaDB).

## Step 2: retrieve the relevant passages

The user's question is turned into a vector with the same model. The database returns the passages whose vector is closest, measured by cosine similarity. By default, the application keeps the top three.

## Step 3: generate the answer

The retained passages are added to the prompt along with the question. The model (here qwen2.5:7b) answers based on them and cites the passages by their number, for example [1] or [2].

## Limitations to know

- if the right passage is not retrieved, the model answers without it: the quality of the chunking and of the embedding matters as much as that of the generation model
- a 7-billion-parameter model on CPU produces a few tokens per second: response times are measured in seconds, not milliseconds
- the more passages there are in the prompt, the longer the time to first token
