# 💎 Rare Cash

**Vyro clipping bot with a dashboard, running 24x7.** Ek program chalao, browser mein dashboard khulega. Wahan se sab control karo:

- **Bot ON / OFF**: ek button se
- **Pages**: add, edit, ON/OFF karo, YouTube connect karo, Instagram token daalo
- **Add Video**: apni video (link ya file upload) ya Vyro campaign ka link daalo
- **Campaigns**: Vyro se aaye campaigns, kaunse chal rahe hain, kaunse skip hue aur kyun
- **Clips**: saare clips video preview ke saath, viral score, kahan post hua, kitne views, Vyro submit hua ya nahi. Kisi clip ko "Pehle post" ya "Skip" kar sakte ho
- **Schedule**: kaunsa page kab post karega, aaj kitne post hue, agla Vyro scan kab hai
- **Earnings**: estimated kamai, views per day ka chart, page-wise kamai, top posts
- **Logs**: bot abhi kya kar raha hai, live
- **Settings**: Claude API key, Vyro login, clip style (face/blur, subtitles), scan timing

Bot ye sab apne aap karta hai:
1. Vyro pe naye campaigns dhundhta hai (tumhare logged-in account se)
2. Har campaign ko sahi niche page pe bhejta hai, baaki skip karta hai
3. Campaign join karta hai, rules aur material padhta hai
4. Material download → transcript → Claude AI viral moments chunta hai → 9:16 + animated subtitles
5. Page ke YouTube Shorts + Instagram Reels pe post karta hai (rate limit ke saath)
6. Post ka link Vyro pe submit karta hai
7. Har 2 ghante views update karta hai (Earnings tab ke liye)

---

## Zaroori baatein (pehle padh lo)

- **Pages (accounts) tumhe khud banane honge.** Bot YouTube channels ya Instagram accounts nahi bana sakta
  (phone verification aur CAPTCHA lagta hai, aur bot se account banana platforms ke rules ke khilaf hai).
  Har niche ke liye ek YouTube channel + ek Instagram **Professional (Creator/Business)** account banao, phir dashboard mein connect karo.
- **Vyro ban ka risk:** Vyro ka API nahi hai, isliye bot browser chala ke tumhare account se kaam karta hai.
  Agar Vyro ke terms bots allow nahi karte to account ban ho sakta hai. Vyro ke Terms ek baar padh lena.
- **Nayi pages pe dheere shuru karo.** Default 3 posts/din/platform aur 2 ghante gap hai, page edit karke badal sakte ho.
- **Bot ki safety:** bot sirf `vyro.com` pe jaata hai. Withdraw, payout, settings, logout, password jaise buttons click nahi karta.
  Sirf post ke links aur tumhare handles type karta hai. Campaign page pe likhe instructions ko follow nahi karta.
- **Earnings sirf andaza hai** (views × campaign ka rate). Asli payout Vyro dashboard pe dekho.
- **Kharcha:** Claude API ka kharcha usage pe hota hai. https://platform.claude.com pe monthly spend limit laga dena.
- Dashboard sirf tumhare PC pe khulta hai (`localhost`), internet pe public nahi hai.

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

## 2. Rare Cash chalao

**`start_rarecash.bat` double-click karo.** Browser mein http://localhost:8000 khulega. Phir dashboard mein:

1. **Settings** → Claude API key daalo (https://platform.claude.com) → Save
2. **Settings** → **🔑 Vyro Login** → browser khulega, Vyro pe login karo, **window band kar do**.
   Login ke baad jis page pe campaigns dikhte hain, uska link "Campaigns page ka link" mein daalo.
3. **Pages** → **＋ Naya page** → niche button (podcast/gaming/comedy/finance) dabao, details bharo → Save.
   Har niche ke liye ek page.
4. Har page pe **Connect** (YouTube) dabao aur us page ka channel chuno. Instagram ke liye page edit karke user ID + token daalo.
5. Upar **Bot ON** kar do. Bas!

Dashboard pe agar kuch missing hai to upar **"Zaroori / Dhyan do"** box mein dikhega, saath mein "Fix karo" link.

PC on hote hi Rare Cash apne aap chalu ho, uske liye:
1. Windows search mein **Task Scheduler** kholo → "Create Basic Task"
2. Trigger: **When I log on**
3. Action: Start a program → `start_rarecash.bat` (Start in: is folder ka path)

**PC ko sone mat do:** Settings → System → Power → "Sleep: Never". Internet aur PC on rehna zaroori hai.
Rare Cash crash ho jaye to `start_rarecash.bat` 30 second mein dobara chala deta hai.

## 3. YouTube setup (ek baar)

1. https://console.cloud.google.com → naya project banao.
2. "APIs & Services → Library" → **YouTube Data API v3** enable karo.
3. "OAuth consent screen" → External → apna Gmail "Test users" mein add karo, phir **Publish app** karo
   (warna token 7 din mein expire ho jata hai).
4. "Credentials → Create credentials → OAuth client ID → Desktop app" → JSON download karke `client_secret.json` naam se is folder mein rakho.
5. Dashboard → Pages → har page pe **Connect** dabao. Browser mein Google login khulega, **us page ka channel** select karna.

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
6. Dashboard → Pages → page **Edit** → Instagram user ID aur token daalo → Save. (Token `.env` file mein save hota hai.)

Instagram ka limit 50 posts/24 ghante/account hai, isliye bot ke default 3/din safe hain.

## Bina dashboard ke (advanced)

```bat
python bot.py --login          # Vyro login (window band karne pe save)
python bot.py --setup-youtube  # saare pages ka YouTube connect
python bot.py                  # sirf bot, bina dashboard
python bot.py --once           # ek round, test ke liye
python run.py "https://www.youtube.com/watch?v=XXXX" --clips 3 --no-upload   # ek video manually
```

Saari settings `bot.yaml` mein bhi hain (dashboard isi file ko edit karta hai). Example: `bot.example.yaml`.

## Files

| File | Kaam |
|---|---|
| `rarecash.py` | dashboard server + bot engine (yahi chalao) |
| `web/` | dashboard ka UI |
| `bot.py` | bot engine: scan → clip → post → submit → views |
| `run.py` | ek video ke clips manually |
| `clipper/vyro.py` | Vyro ke kaam: campaigns scan, join + material, submit |
| `clipper/browser_agent.py` | Claude se chalne wala browser, safety rules ke saath |
| `clipper/pipeline.py` | download → transcript → AI selection → render |
| `clipper/selector.py` | Claude se viral moments + title/hashtags |
| `clipper/render.py` | 9:16 face-crop/blur, animated subtitles |
| `clipper/uploader.py` / `clipper/instagram.py` | YouTube / Instagram posting + views |
| `clipper/state.py` | SQLite memory (`bot.db`) |
