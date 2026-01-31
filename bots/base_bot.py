import threading
import os
import shutil
from pathlib import Path
from langchain_groq import ChatGroq
from langchain_community.vectorstores import Chroma
from core.embeddings import E5Embeddings
from bots.chatbot import Chatbot
from config.settings import GROQ_API_KEY

class BaseBot:
    def __init__(self, meta, persist_dir):
        self.meta = meta
        self.persist_dir = Path(persist_dir)
        self.embedding_model = E5Embeddings()
        self.vector_store = None
        self.chat_model = ChatGroq(api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile")
        self.enhanced_chatbot = None
        self.lock = threading.Lock()

    def ensure_vector_store(self):
        if not self.vector_store:
            self.vector_store = Chroma(
                persist_directory=str(self.persist_dir),
                embedding_function=self.embedding_model
            )
            self.enhanced_chatbot = Chatbot(
                self.vector_store, 
                self.embedding_model, 
                self.chat_model, 
                self.meta.fallback_response
            )

    def clear_knowledge_base(self):
        with self.lock:
            if self.vector_store:
                try:
                    self.vector_store.delete_collection()
                    print(f"Deleted collection for bot {self.meta.id}")
                except Exception as e:
                    print(f"Error deleting collection: {e}")
                
                if os.path.exists(self.persist_dir):
                    try:
                        shutil.rmtree(self.persist_dir)
                        print(f"Deleted persist directory for bot {self.meta.id}")
                    except Exception as e:
                        print(f"Error deleting persist directory: {e}")
                
                os.makedirs(self.persist_dir, exist_ok=True)
                
                self.vector_store = None
                self.enhanced_chatbot = None
                
                self.ensure_vector_store()
                print(f"Created fresh knowledge base for bot {self.meta.id}")

    def chat(self, message: str):
        self.ensure_vector_store()
        if self.enhanced_chatbot:
            return self.enhanced_chatbot.chat(message)
        else:
            docs = self.vector_store.similarity_search(message, k=3)
            return docs[0].page_content if docs else self.meta.fallback_response