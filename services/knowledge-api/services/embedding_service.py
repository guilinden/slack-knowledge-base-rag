from langchain_huggingface import HuggingFaceEmbeddings

_embeddings: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')
    return _embeddings


def embed_text(text: str) -> list[float]:
    return get_embeddings().embed_query(text)
