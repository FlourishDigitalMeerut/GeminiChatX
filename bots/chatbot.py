from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from core.intent_analyzer import analyze_intent
from core.retriever import advanced_retrievers

class Chatbot:
    def __init__(self, vector_store, embedding_model, chat_model, fallback_response):
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.fallback_response = fallback_response
        self.retriever = None
        self.chat_history = []
        
    def ensure_retriever(self):
        if not self.retriever and self.vector_store:
            self.retriever = advanced_retrievers(self.vector_store, self.embedding_model)
    
    def chat(self, user_input: str) -> str:
        if not self.vector_store:
            return self.fallback_response
        
        self.ensure_retriever()
        
        try:
            detected_intent = analyze_intent(user_input)
            print(f"Detected Intent: {detected_intent}")

            retrieved_docs = self.retriever.invoke(user_input)
            retrieved_content = "\n\n".join([doc.page_content for doc in retrieved_docs])

            chat_history = []
            for msg in self.chat_history[-10:]:
                if msg["type"] == "human":
                    chat_history.append(HumanMessage(content=msg["content"]))
                else:
                    chat_history.append(AIMessage(content=msg["content"]))

            prompt_template = PromptTemplate(
                template="""
You are an intelligent assistant chatbot. Use the knowledge base content to answer questions accurately.Your responses should be based on the provided knowledge base content and you resonse must be bussiness and professional and clear and must look like that actual human respoonds.

USER QUERY: {query}
DETECTED INTENT: {detected_intent}

RELEVANT KNOWLEDGE BASE CONTENT:
{retrieved_doc}

INSTRUCTIONS:
- Use knowledge base content primarily
- Provide comprehensive answer if relevant
- If not relevant, use general knowledge but indicate it related to the query and relevant knowledgebase boundary.
- Keep responses concise and accurate
- Do not use vague disclaimers
- Provide brief and clear response to the user query by default unless explicitly mentioned
- If you did not find any content or retrieved doc which is related to the query(means the matching score is not good) then just simply use the following fallback response:-> "{fallback_response}"

Note:If a person right ok, alright, good or any one words regarding satisfaction and dissatifaction so respond to them accordingly in a friendly and gentle manner also do not say vague statements like According to my knowledge base, as my knowledge base do not include this, etc(try to avoid this vagues statements use).

RESPONSE:
""",
                input_variables=['query', 'detected_intent', 'retrieved_doc', 'fallback_response']
            )

            formatted_prompt = prompt_template.format(
                query=user_input,
                detected_intent=detected_intent,
                retrieved_doc=retrieved_content,
                fallback_response=self.fallback_response
            )

            system_message = SystemMessage(content=formatted_prompt)
            human_message = HumanMessage(content=user_input)
            messages = [system_message] + chat_history + [human_message]

            response = self.chat_model.invoke(messages)

            self.chat_history.append({"type": "human", "content": user_input})
            self.chat_history.append({"type": "AI", "content": response.content})
            if len(self.chat_history) > 10:
                self.chat_history = self.chat_history[-10:]

            return response.content
        except Exception as e:
            print(f"Error in chat: {e}")
            return self.fallback_response

    def clear_history(self):
        self.chat_history = []