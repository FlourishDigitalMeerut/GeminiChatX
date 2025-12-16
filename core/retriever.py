from langchain_classic.retrievers import ContextualCompressionRetriever # pyright: ignore[reportMissingImports]
from langchain_classic.retrievers.document_compressors import EmbeddingsFilter # pyright: ignore[reportMissingImports]

def advanced_retrievers(vector_store, embedding_model):
    mmr_retriever = vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={"k":3, "lambda_mult":0.6}
    )
    embeddings_filter = EmbeddingsFilter(
        embeddings=embedding_model,
        similarity_threshold=0.75
    )
    return ContextualCompressionRetriever(
        base_compressor=embeddings_filter,
        base_retriever=mmr_retriever
    )