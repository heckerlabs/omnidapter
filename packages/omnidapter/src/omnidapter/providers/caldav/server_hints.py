def detect_server_hint(server_url: str) -> str | None:
    url = server_url.lower()
    if "icloud" in url:
        return "icloud"
    if "nextcloud" in url:
        return "nextcloud"
    return None
