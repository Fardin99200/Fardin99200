# Vyro Clipping Bot (24x7, fully automatic)

Ye bot apne aap, bina ruke:

1. **Vyro pe naye campaigns dhundhta hai** (har 3 ghante), tumhare logged-in account se
2. **Har campaign ko sahi niche page pe bhejta hai** (podcast / gaming / comedy / finance), baaki skip
3. **Campaign join karta hai**, rules aur source material ke links padhta hai
4. **Material download → transcript → Claude AI viral moments chunta hai → 9:16 + animated subtitles**
5. **Page ke YouTube Shorts + Instagram Reels pe post karta hai** (rate limit ke saath, spam nahi)
6. **Post ka link Vyro campaign pe submit karta hai**

Sab kuch `bot.db` mein save hota hai, to PC restart ho jaye to bhi jahan ruka wahin se chalega.

> Ek video manually clip karni ho to `run.py` bhi hai (neeche dekho).

---

## Zaroori baatein (pehle padh lo)

- **Pages (accounts) tumhe khud banane honge.** Bot YouTube channels ya Instagram accounts nahi bana sakta
  (phone verification aur CAPTCHA lagta hai, aur bot se account banana platforms ke rules ke khilaf hai).
  Har niche ke liye ek YouTube channel + ek Instagram **Professional (Creator/Business)** account banao. Ye ek baar ka kaam hai.
- **Vyro bot ban ka risk:** Vyro ka API nahi hai, isliye bot browser chala ke tumhare account se kaam karta hai.
  Agar Vyro ke terms bots allow nahi karte to account ban ho sakta hai. Vyro ke Terms ek baar padh lena.
- **Nayi pages pe dheere shuru karo.** Naye accounts pe din mein bahut posts karoge to reach kam ho sakti hai (shadowban).
  Default 3 posts/din/platform aur 2 ghante gap hai, `bot.yaml` mein badal sakte ho.
- **Bot ki safety:** bot sirf `vyro.com` pe jaata hai. Withdraw, payout, settings, logout, password jaise buttons click nahi karta.
  Sirf post ke links aur tumhare handles type karta hai. Campaign page pe likhe instructions ko follow nahi karta.
- **Kharcha:** Claude API ka kharcha usage pe hota hai (moments chunna + Vyro browser steps). Pehle hafte
  https://platform.claude.com pe usage dekhte rehna, aur wahan monthly spend limit laga dena.

---

## 1. Install (ek baar, Windows)

1. **Python 3.10+** (https://python.org). Install karte waqt "Add to PATH" tick karna.
2. **FFmpeg**: PowerShell mein `winget install ffmpeg`
3. Is folder mein terminal kholo:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```
4. `.env.example` ko copy karke `.env` banao, aur `ANTHROPIC_API_KEY` daalo (https://platform.claude.com).
5. `bot.example.yaml` ko copy karke `bot.yaml` banao.

## 2. Vyro login (ek baar)

```bat
python bot.py --login
```
Browser khulega. Vyro pe login karo, phir terminal mein ENTER dabao. Login `browser_profile/` mein save ho jata hai.
Login ke baad jis page pe campaigns ki list dikhti hai, uska URL `bot.yaml` mein `vyro.start_url` pe daal do.

Agar kabhi login expire hua to `logs/bot.log` mein `LOGIN_REQUIRED` aayega. Tab bas `python bot.py --login` dobara chalao.
Tab tak clipping aur posting chalti rahegi.

## 3. YouTube setup (ek baar)

1. https://console.cloud.google.com → naya project banao.
2. "APIs & Services → Library" → **YouTube Data API v3** enable karo.
3. "OAuth consent screen" → External → apna Gmail "Test users" mein add karo, phir **Publish app** karo
   (warna token 7 din mein expire ho jata hai).
4. "Credentials → Create credentials → OAuth client ID → Desktop app" → JSON download karke `client_secret.json` naam se is folder mein rakho.
5. Chalao:
   ```bat
   python bot.py --setup-youtube
   ```
   Har page ke liye browser khulega. Har baar **us page ka channel** select karna.

**Quota:** Google free mein ek project ko 10,000 units/din deta hai, aur ek upload ~1600 units ka hota hai, matlab
**~6 uploads/din saare pages mila ke**. 4 pages × 3 posts ke liye Google Console mein
"YouTube API quota extension" form bhar ke quota badhwa lo (free hai). Tab tak `max_per_day` kam rakho.
Naye project se upload hui videos YouTube private lock kar sakta hai jab tak API audit na ho. Wo form bhi wahi hai.

## 4. Instagram setup (har page ke liye)

1. Instagram account ko **Professional (Creator ya Business)** banao, aur ek **Facebook Page** se link karo.
2. https://developers.facebook.com → My Apps → Create App (type: Business). Usme **Instagram Graph API** add karo.
3. **Graph API Explorer** mein permissions lo: `instagram_basic`, `instagram_content_publish`,
   `pages_show_list`, `pages_read_engagement`, `business_management`.
4. User token ko **long-lived** banao (Access Token Debugger → "Extend"), phir `me/accounts` call karke
   us Facebook Page ka **Page access token** lo. Long-lived user token se nikla Page token expire nahi hota.
5. `<page-id>?fields=instagram_business_account` se **Instagram user ID** nikalo.
6. `bot.yaml` mein `user_id` daalo, aur token `.env` mein (jaise `IG_TOKEN_PODCAST=...`).

Instagram ka limit 50 posts/24 ghante/account hai, isliye bot ke default 3/din safe hain.

## 5. Chalao, 24x7

Test ke liye ek cycle:
```bat
python bot.py --once
```
Hamesha ke liye: **`start_bot.bat` double-click karo.** Bot crash ho jaye to 60 second mein apne aap restart ho jata hai.

PC on hote hi apne aap chalu ho, uske liye:
1. Windows search mein **Task Scheduler** kholo → "Create Basic Task"
2. Trigger: **When I log on**
3. Action: Start a program → `start_bot.bat` (Start in: is folder ka path)

**PC ko sone mat do:** Settings → System → Power → "Sleep: Never" (screen band ho sakti hai, PC nahi).
Internet aur PC on rehna zaroori hai.

## Kya ho raha hai, kaise dekhein

- `logs/bot.log`: har kaam ka log (campaigns, clips, posts, submit)
- `output/<page>/...`: saare clips (`.mp4` + `.json`)
- `bot.db`: state. Isko [DB Browser for SQLite](https://sqlitebrowser.org) se khol ke tables dekh sakte ho:
  `campaigns`, `clips`, `posts` (post URL + `vyro_status`)

## bot.yaml settings

| Setting | Kaam |
|---|---|
| `vyro.start_url` | Vyro ka campaigns page |
| `vyro.scan_every_hours` | naye campaigns kitni baar dekhne hain |
| `vyro.min_cpm_usd` | is se kam paise wale campaigns skip |
| `vyro.max_materials_per_campaign` | ek campaign ki kitni videos clip karni hain |
| `vyro.headless` | `true` = browser window chhupi |
| `pages[].niche` | page kis type ke campaigns lega (AI isse match karta hai) |
| `pages[].clips_per_video` | har source video se kitne clips |
| `pages[].min_gap_minutes` | do posts ke beech ka gap |
| `pages[].youtube.max_per_day` / `instagram.max_per_day` | roz ke posts ki limit |
| `clip_defaults` | `crop_mode` (face/center/blur), `captions`, `whisper_model`, `min_seconds`, `max_seconds` |

Kisi page pe YouTube ya Instagram nahi chahiye to us block mein `enabled: false` likh do.

---

## Ek video manually (run.py)

```bat
python run.py "https://www.youtube.com/watch?v=XXXX" --clips 3 --no-upload
python run.py my_video.mp4 --crop blur
python run.py --campaign campaign.yaml
```
Options: `--clips`, `--min`, `--max`, `--crop face|center|blur`, `--no-captions`, `--upload`, `--privacy`, `--whisper`.

## Files

| File | Kaam |
|---|---|
| `bot.py` | 24x7 bot (scan → clip → post → submit) |
| `run.py` | ek video ke clips manually |
| `clipper/vyro.py` | Vyro ke kaam: campaigns scan, join + material, submit |
| `clipper/browser_agent.py` | Claude se chalne wala browser, safety rules ke saath |
| `clipper/pipeline.py` | download → transcript → AI selection → render |
| `clipper/selector.py` | Claude se viral moments + title/hashtags |
| `clipper/render.py` | 9:16 face-crop/blur, animated subtitles |
| `clipper/uploader.py` / `clipper/instagram.py` | YouTube Shorts / Instagram Reels posting |
| `clipper/state.py` | SQLite memory (kuch bhi do baar nahi hota) |
