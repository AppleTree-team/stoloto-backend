from uuid import uuid4

# session_id -> user_id
sessions = {}


def create_session(user_id: int) -> str:
    session_id = str(uuid4())
    sessions[session_id] = user_id
    return session_id


def get_user_id(session_id: str):
    return sessions.get(session_id)


def delete_session(session_id: str):
    sessions.pop(session_id, None)