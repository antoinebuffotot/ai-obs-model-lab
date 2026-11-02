# Principes du RAG (Retrieval-Augmented Generation)

[English version](02-rag-principles.md)

Le RAG consiste à donner au modèle les bons extraits de documents au moment de répondre, au lieu de compter uniquement sur ce qu'il a appris pendant son entraînement.

## Étape 1 : indexer les documents

Les documents sont découpés en passages d'environ 900 caractères, avec un léger chevauchement pour ne pas couper une idée en deux. Chaque passage est transformé en vecteur par un modèle d'embedding (ici nomic-embed-text), puis stocké dans une base vectorielle (ici ChromaDB).

## Étape 2 : retrouver les passages pertinents

La question de l'utilisateur est transformée en vecteur avec le même modèle. La base renvoie les passages dont le vecteur est le plus proche, mesuré par similarité cosinus. Par défaut, l'application garde les trois meilleurs.

## Étape 3 : générer la réponse

Les passages retenus sont ajoutés au prompt avec la question. Le modèle (ici qwen2.5:7b) répond en s'appuyant dessus et cite les passages par leur numéro, par exemple [1] ou [2].

## Limites à connaître

- si le bon passage n'est pas retrouvé, le modèle répond sans lui : la qualité du découpage et de l'embedding compte autant que celle du modèle de génération
- un modèle de 7 milliards de paramètres sur CPU produit quelques jetons par seconde : les temps de réponse se mesurent en secondes, pas en millisecondes
- plus il y a de passages dans le prompt, plus le temps avant le premier jeton augmente
