def login(user: str, password: str) -> bool:
    """Fake function for login"""
    _ = password.lower()
    if user.lower().startswith("test"):
        return True
    else:
        return False
