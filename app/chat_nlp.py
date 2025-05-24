import os
import requests

def get_chat_response(user_query: str) -> str:
    full_prompt = (
        "You are SPECS NEXUS Assistance, a helpful chatbot. "
        "SPECS Nexus is a comprehensive platform designed for a student organization. It streamlines membership registration, event participation, and announcement updates, helping members stay connected and informed. The system makes it easy for students to manage their profiles, track their membership status, and engage with community activities in a user-friendly environment. "
        "The system is called SPECS NEXUS. It has 5 main pages - Dashboard, Profile, Events, Announcements, and Membership. "
        "If you do not have the information, respond with: 'I'm sorry, I do not have that information.' \n\n"
        f"User Query: {user_query}\n"
        "Answer:"
    )
    
    url = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('TOGETHER_AI_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistralai/Mistral-7B-Instruct-v0.1",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 256,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except requests.RequestException as e:
        raise Exception(f"Together.ai API error: {str(e)}")
