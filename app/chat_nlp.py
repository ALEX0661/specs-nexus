import os
import requests
import pickle
import numpy as np
import faiss
from functools import lru_cache
from sentence_transformers import SentenceTransformer


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FAISS_INDEX_PATH = os.path.join(BASE_DIR, "faiss_system_index.pkl")
DOC_MAPPING_PATH = os.path.join(BASE_DIR, "system_doc_mapping.pkl")


with open(FAISS_INDEX_PATH, "rb") as f:
    faiss_index = pickle.load(f)
with open(DOC_MAPPING_PATH, "rb") as f:
    documents = pickle.load(f)


embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


TOGETHER_AI_KEY = "d33551f1ead6362d8ad07b4787274f4007a11d64cb2ab3d5c1be2b325c8b285c"

@lru_cache(maxsize=128)
def get_query_embedding(query: str):
    return np.array(embedding_model.encode([query])).astype("float32")

def retrieve_context(query: str, k: int = 3) -> str:

    query_embedding_np = get_query_embedding(query)
    distances, indices = faiss_index.search(query_embedding_np, k)
    retrieved_texts = [documents[i] for i in indices[0] if i < len(documents)]
    return "\n\n".join(retrieved_texts)

def get_chat_response(user_query: str) -> str:

    context = retrieve_context(user_query)
    full_prompt = (
        "You are SPECS NEXUS Assistance, a helpful chatbot that uses only the context provided below to answer questions. "
        "SPECS info is in the context."
        "This is SPECS NEXUS.SPECS Nexus is a comprehensive platform designed for a student organization. It streamlines membership registration, event participation, and announcement updates, helping members stay connected and informed. The system makes it easy for students to manage their profiles, track their membership status, and engage with community activities in a user-friendly environment."
        "The system i called SPECS NEXUS. This has 5 main pages - Dashboard, Profile, Events, Announcements, and MembershipS. "
        "If the context does not include the answer, respond with: \"I'm sorry, I do not have that information.\" \n\n"
        f"Context:\n{context}\n\n"
        f"User Query: {user_query}\n"
        "Answer:"
    )
    
    url = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {TOGETHER_AI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistralai/Mistral-7B-Instruct-v0.1",  # Adjust if needed
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 256,
        "temperature": 0.7,
        "do_sample": True
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Together.ai API error {response.status_code}: {response.text}")
    
    data = response.json()
    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    return answer
