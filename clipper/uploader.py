"""Upload clips to YouTube Shorts via the YouTube Data API v3."""
from __future__ import annotations

from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = Path("client_secret.json")
TOKEN = Path("token.json")


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise FileNotFoundError(
                    "client_secret.json nahi mili. README ke 'YouTube upload setup' steps follow karo."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)  # opens browser once for login
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload_short(file: Path, title: str, description: str, tags: list[str], privacy: str = "private") -> str:
    from googleapiclient.http import MediaFileUpload

    if "#shorts" not in (title + description).lower():
        description = f"{description}\n\n#Shorts".strip()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": [t.lstrip("#") for t in tags][:30],
            "categoryId": "22",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    request = _service().videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(file), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4"),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"\r  Uploading {int(status.progress() * 100)}%", end="", flush=True)
    print()
    return f"https://youtube.com/shorts/{response['id']}"
