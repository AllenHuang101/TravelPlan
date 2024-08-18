from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import FileChatMessageHistory

history_store = {}

def get_session_history(session_id: str, plan: str) -> BaseChatMessageHistory:
    if (session_id, plan) not in history_store:
        history_store[(session_id, plan)] = FileChatMessageHistory(f"./history/chat_history_{session_id}_{plan}.txt")
    return history_store[(session_id, plan)]