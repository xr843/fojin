"""Local GPU embedding server compatible with OpenAI API format.

Usage:
    python embedding_server.py [--port 8090] [--model BAAI/bge-m3]

Provides /v1/embeddings endpoint that the generate_embeddings.py script can call.
"""

import argparse
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()
model = None
model_name = ""


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = ""


class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: list[float]
    index: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: dict = {"prompt_tokens": 0, "total_tokens": 0}


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest) -> EmbeddingResponse:
    texts = [req.input] if isinstance(req.input, str) else req.input
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=256)
    data = [
        EmbeddingData(embedding=emb.tolist(), index=i)
        for i, emb in enumerate(embeddings)
    ]
    return EmbeddingResponse(data=data, model=model_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--model", type=str, default="BAAI/bge-m3")
    parser.add_argument("--device", type=str, default="cuda:0")
    args = parser.parse_args()

    model_name = args.model
    print(f"Loading {model_name} on {args.device}...")
    model = SentenceTransformer(model_name, device=args.device)
    print(f"Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
