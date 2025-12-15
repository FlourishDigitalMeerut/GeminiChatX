from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

def split_documents(all_docs: list[Document], batch_size: int = 16):
    total_chars = sum(len(doc.page_content) for doc in all_docs)
    dynamic_chunk_size = min(1000, max(200, total_chars // 20))
    dynamic_chunk_overlap = int(dynamic_chunk_size * 0.15)
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=dynamic_chunk_size,
        chunk_overlap=dynamic_chunk_overlap
    )
    return splitter.split_documents(all_docs)