import tempfile
import os
from pathlib import Path
from typing import List
from fastapi import UploadFile
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    TextLoader, PyMuPDFLoader, Docx2txtLoader, CSVLoader, UnstructuredExcelLoader
)

async def process_uploaded_files(files: List[UploadFile]) -> List[Document]:
    """Process uploaded files and return documents."""
    all_docs = []
    
    for file in files:
        filename = file.filename.lower()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        try:
            if filename.endswith(".txt"):
                loader = TextLoader(temp_file_path)
            elif filename.endswith(".pdf"):
                loader = PyMuPDFLoader(temp_file_path)
            elif filename.endswith(".docx"):
                loader = Docx2txtLoader(temp_file_path)
            elif filename.endswith(".csv"):
                loader = CSVLoader(temp_file_path)
            elif filename.endswith(".xlsx"):
                loader = UnstructuredExcelLoader(temp_file_path)
            else:
                os.unlink(temp_file_path)
                continue
            
            docs = loader.load()
            all_docs.extend(docs)
            
        except Exception as e:
            print(f"Error loading file {filename}: {e}")
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            continue
        
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
    
    return all_docs

async def process_website_content(website_url: str) -> List[Document]:
    """Process website URL and return documents."""
    from utils.web_utils import fetch_website_html, valid_url
    
    if not valid_url(website_url):
        return []
    
    html_text = fetch_website_html(website_url)
    if html_text:
        return [Document(page_content=html_text, metadata={"source": website_url})]
    return []