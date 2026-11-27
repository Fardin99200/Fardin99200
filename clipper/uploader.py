"""Upload clips to YouTube Shorts via the YouTube Data API v3."""
from __future__ import annotations

from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = Path("client_secret.json")
TOKEN = Path("token.json")


def _service(token_file: Path = TOKEN, client_secret: Path = CLIENT_SECRET):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_file, client_secret = Path(token_file), Path(client_secret)
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES) if token_file.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret.exists():
                raise FileNotFoundError(
                    f"{client_secret} nahi mili. README ke 'YouTube setup' steps follow karo."
                )
            print(f"  Browser khulega: is page ({token_file.stem}) ka YouTube channel select karo")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
            creds = flow.run_local_server(port=0)  # opens browser once for login
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload_short(file: Path, title: str, description: str, tags: list[str], privacy: str = "private",
                 token_file: str | Path = TOKEN, client_secret: str | Path = CLIENT_SECRET) -> str:
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
    request = _service(token_file, client_secret).videos().insert(
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
