# Vyro Clipping Automation

Ek command se poora clipping kaam:

```
Video link → Download → Transcript (Whisper) → Claude AI best moments chunega
→ 9:16 vertical + animated captions → YouTube Shorts upload → Vyro ke liye links ki list
```

## 1. Ek baar ka setup (Windows / Mac / Linux)

1. **Python 3.10+** install karo (https://python.org), install karte waqt "Add to PATH" tick karna.
2. **FFmpeg** install karo:
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
3. Is folder mein terminal kholo aur:
   ```bash
   python -m venv .venv
   # Windows:  .venv\Scripts\activate
   # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Claude API key**: https://platform.claude.com pe account bana ke API key lo.
   `.env.example` ko copy karke `.env` naam do aur key daalo.
   (Ek ghante ki video pe roughly 5-15 cents ka kharcha aata hai.)

## 2. Campaign file banao

`campaign.example.yaml` copy karke `campaign.yaml` banao. Vyro campaign page se:
- source video links `sources:` mein daalo
- campaign ke rules `rules:` mein paste karo (Claude unko follow karega)
- clip length, language, hashtags set karo

## 3. Chalao

```bash
# campaign file se (sab links process honge)
python run.py --campaign campaign.yaml

# ya seedha link se
python run.py "https://www.youtube.com/watch?v=XXXX" --clips 3 --no-upload

# local file
python run.py my_podcast.mp4 --crop blur
```

Clips `output/<video>/` mein milenge: `.mp4` (1080x1920) + `.json` (title, description, hashtags, timestamps).
`output/submissions.csv` mein har clip ka YouTube link hota hai — wahi links Vyro pe submit karo.

Useful options:

| Option | Kaam |
|---|---|
| `--clips 5` | har video se kitne clips |
| `--min 20 --max 60` | clip length (seconds) |
| `--crop face/center/blur` | `face` = chehra center mein, `blur` = poora frame + blurred background |
| `--no-captions` | subtitles band |
| `--upload` / `--no-upload` | YouTube upload on/off |
| `--privacy public` | upload privacy |
| `--whisper medium` | behtar transcript (GPU pe), slow PC pe `base` |

Same command dobara chalao to jo videos ho chuke hain wo skip ho jaate hain, isliye isko
**Task Scheduler (Windows) / cron (Mac/Linux)** pe roz chala sakte ho — campaign file mein naye links daalte jao.

## 4. YouTube upload setup (ek baar)

1. https://console.cloud.google.com → naya project banao.
2. "APIs & Services → Library" → **YouTube Data API v3** enable karo.
3. "OAuth consent screen" → External → apna Gmail "Test users" mein add karo.
4. "Credentials → Create credentials → OAuth client ID → Desktop app" → JSON download karo,
   naam `client_secret.json` rakh ke is folder mein daalo.
5. Pehli baar upload pe browser khulega, apna YouTube channel select karo. Uske baad `token.json` ban jaati hai, dobara login nahi.

Dhyan rakho:
- Google ka free quota roughly **6 uploads/din** deta hai (har upload ~1600 units, 10,000/din).
- Naye (unverified) Google project se upload hui videos YouTube **private lock** kar sakta hai jab tak
  project ka audit na ho. Agar aisa ho to YouTube Studio se manually public karo, ya Google ka
  "API audit" form bharo.
- Default `privacy: private` hai — pehle kuch clips dekh ke quality check karo, phir `public` karo.

## Vyro ke baare mein

- Vyro ka koi public API nahi hai, isliye **submission manual** hai: `submissions.csv` se link copy karke Vyro dashboard pe submit karo.
- Sirf Vyro campaign mein diye gaye source videos clip karo, aur campaign ke rules follow karo, warna clips reject ho sakte hain.
- TikTok/Instagram upload abhi nahi hai — wahan `.mp4` files manually upload kar sakte ho.

## Files

| File | Kaam |
|---|---|
| `run.py` | main command |
| `clipper/download.py` | yt-dlp se download |
| `clipper/transcribe.py` | faster-whisper transcript (word timestamps) |
| `clipper/selector.py` | Claude se best moments + titles/hashtags |
| `clipper/render.py` | 9:16 crop/blur, face tracking, animated captions |
| `clipper/uploader.py` | YouTube Shorts upload |
