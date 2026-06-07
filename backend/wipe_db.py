from app.document_store import store
import os

print("Wiping all users and chat history from the database...")

if not store._storage_ready:
    from app.config import get_settings
    settings = get_settings()
    store.configure(settings.database_url, settings.sqlite_path)

try:
    users = store._users_collection.get()
    if users and users.get('ids'):
        store._users_collection.delete(ids=users['ids'])
        print(f"Deleted {len(users['ids'])} users.")
    else:
        print("No users found.")
        
    chats = store._chat_collection.get()
    if chats and chats.get('ids'):
        store._chat_collection.delete(ids=chats['ids'])
        print(f"Deleted {len(chats['ids'])} chat messages.")
    else:
        print("No chat history found.")
        

    print("Database cleared successfully!")
except Exception as e:
    print(f"Error wiping database: {e}")
