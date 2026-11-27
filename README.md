# 💎 Rare Cash

**Vyro clipping bot with a dashboard, 24x7.** `RareCash.exe` chalao, browser mein dashboard khulega, wahan se sab control karo.

Bot apne aap:
1. Vyro (app.vyro.com) pe naye campaigns dhundhta hai, tumhare logged-in account se
2. Har campaign ko sahi niche page pe bhejta hai (podcast / gaming / comedy / finance…), baaki skip
3. Campaign join karta hai, rules aur material padhta hai
4. Material → transcript → Claude AI viral moments chunta hai → 9:16 clip: subtitles, upar hook title, progress bar, slow zoom, background music
5. **YouTube Shorts, Instagram Reels aur TikTok** pe post karta hai (rate limit ke saath)
6. Post ka link Vyro pe submit karta hai
7. Views update karta hai, aur Vyro se **asli kamai** padhta hai
8. Telegram pe alerts bhejta hai, aur phone se `/on` `/off` `/status` se control hota hai

Dashboard: Bot ON/OFF · Pages · Add Video · Campaigns · Clips (preview) · Schedule · Earnings (andaza + Vyro asli) · Logs · Settings
(Vyro login, built-in VPN, Telegram, phone access, TikTok app, clip style, auto-start).

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

## Built-in VPN (Tier-1 country, bina VPN app ke)

Rare Cash ke andar VPN hai. Upar **🔒 VPN** button dabao aur Rare Cash ka saara kaam
(Vyro browser, YouTube/Instagram upload, views) us country ke server se jayega.
Koi VPN app install nahi karna, admin permission nahi chahiye, aur baaki PC (Chrome, games) normal internet pe rehta hai.

Ye open-source [wireproxy](https://github.com/windtf/wireproxy) (WireGuard) use karta hai.
Pehli baar Connect karne pe Rare Cash iska ~5 MB engine GitHub se khud download karta hai.

**Ek cheez chahiye: VPN server ki WireGuard config (`.conf` file).** VPN server kisi provider ka hi hota hai, Rare Cash khud server nahi deta:
- **Proton VPN** (free plan bhi hai): account → Downloads → WireGuard configuration → platform chuno → server (US/UK) → Create → `.conf` download
- **Surfshark / NordVPN / Mullvad / PIA** (paid): sab "manual setup → WireGuard" mein `.conf` dete hain
- Ya apna US VPS (~$5/mahina) pe WireGuard server

Phir: **Settings → VPN (built-in) → Server add karo** → `.conf` file chuno → Save → **Connect**.
Kai servers add kar sakte ho (us-newyork, uk-london…) aur kabhi bhi badal sakte ho.

Safety:
- **Kill switch:** VPN ON hai aur tunnel gir gaya, to bot ka traffic India IP se *nahi* jata. Requests fail hoti hain,
  Vyro/posting ruk jati hai, aur Rare Cash har 20 second mein dobara connect karta hai.
  Sirf "VPN OFF" dabane pe normal internet wapas aata hai.
- Claude API (`api.anthropic.com`) VPN ke bahar jata hai, kyunki uske liye country matter nahi karti.
- `.conf` mein tumhari private key hoti hai. Wo sirf `vpn/configs/` mein rehti hai aur dashboard pe kabhi nahi dikhti.
- **VPN guard** (Settings) ON rakho: internet allowed country (US, GB…) se na aa raha ho to bot kaam rok deta hai.

**VPN engine manually:** agar auto-download na ho to https://github.com/windtf/wireproxy/releases se
`wireproxy_windows_amd64.tar.gz` download karo, andar ki `wireproxy.exe` ko `vpn/bin/` folder mein rakh do.

Dhyan rakho:
- VPN sirf IP badalta hai. Campaign ke **Tier-1 views** ka matlab aksar ye hota hai ki *dekhne wale* US/UK ke hon.
  Wo tumhare content aur audience pe depend karta hai.
- Vyro payout ke waqt identity/country verify kar sakta hai. Campaign kisi country tak limited ho aur tum wahan se nahi ho,
  to submission reject ya payout hold ho sakta hai. Vyro ke rules padh ke chalana.
- Ek hi country fix rakho. Account pe India ↔ US baar baar badalna suspicious lagta hai.

---

## 1. Install (Windows): RareCash.exe

1. GitHub pe login karke latest build kholo: repo → **Actions** → "Build RareCash.exe (Windows)" → sabse upar wala run →
   neeche **Artifacts → RareCash-windows** download karo (~675 MB). Download ke liye GitHub mein login hona chahiye.
2. ZIP extract karo (andar ek aur zip ho to wo bhi), folder ko `C:\RareCash` jaisi jagah rakho.
3. **`RareCash.exe` double-click.** Windows "protected your PC" bole to **More info → Run anyway**.
   Kaali window khuli rakho, wo band = Rare Cash band.

Python, FFmpeg, browser, VPN engine sab exe ke andar hain. Tumhara data (bot.db, bot.yaml, .env, output, vpn, music) isi folder mein banta hai.
Naya version: naya ZIP extract karke purane folder ki ye files/folders copy kar lo: `bot.db`, `bot.yaml`, `.env`, `tokens`, `vpn`, `browser_profile*`, `output`, `music`.

<details><summary>Exe ke bina (Python se)</summary>

Python 3.10+ install karo ("Add to PATH" tick), phir folder mein `RareCash_Setup.bat` double-click, uske baad `start_rarecash.bat`.
</details>

## 2. Pehli baar setup (dashboard mein)

1. **Settings → Claude AI**: API key (https://platform.claude.com) → Save
2. **Settings → Vyro → 🔑 Vyro Login**: browser khulega (tumhara Edge/Chrome) → app.vyro.com pe email daalo →
   email mein aaya **code** wahin daalo, ya email ka **login link** copy karke "Link kholo" box mein paste karo →
   login ke baad **window band karo**. Rare Cash khud check karta hai: "✓ logged in" dikhna chahiye.
   Google se login block ho to **"🌐 Normal browser se"** use karo (login karke window band karo, ya "Login ho gaya" dabao).
   Vyro ke andar apne YouTube/Instagram/TikTok accounts bhi connect kar dena (views wahi se track hote hain).
3. **Pages → ＋ Naya page**: har niche ka ek page (YouTube channel / Instagram / TikTok accounts tum khud banao)
4. Har page pe **Connect** (YouTube, TikTok) aur Instagram token
5. Upar **Bot ON**. Bas!

Kuch missing ho to Dashboard pe "Zaroori / Dhyan do" box mein "Fix karo" link ke saath dikhta hai.
**Auto-start:** Settings → Bot → "PC on hote hi Rare Cash apne aap chalu ho". PC ka sleep band rakho (Settings → Power → Never).

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

## 5. TikTok setup

1. https://developers.tiktok.com → app banao → **Login Kit (Desktop)** + **Content Posting API** (Direct Post ON)
2. Scopes: `video.publish`, `video.list`, `user.info.basic`
3. Redirect URI: Settings → TikTok app mein jo dikhta hai (jaise `http://127.0.0.1:8000/tiktok/callback`)
4. Client key + secret Settings mein → Save → Pages → TikTok **Connect**
5. **TikTok ka rule:** app audit hone tak videos sirf **private** post hoti hain (aur account bhi private chahiye).
   Private posts Vyro pe submit nahi hote. Public ke liye TikTok developer portal se audit karwao, phir page mein privacy "Public" karo.
   Agar portal localhost redirect na le, koi bhi apna https page do: login ke baad address bar ka poora link Settings → TikTok "Connect" box mein paste karo.

## 6. Telegram alerts + phone control

Telegram → **@BotFather** → `/newbot` → token copy → Settings → Telegram mein daalo → Save →
apne bot ko `/start` bhejo → Settings mein "Use karo" → "Test".
Alerts: har post, errors, VPN gira, login expire, naya campaign, roz ka hisaab (21:00).
Commands: `/status` `/on` `/off` `/run` `/scan` `/vpn_on` `/vpn_off` `/today`. Sirf tumhari chat se commands chalte hain.

## 7. Phone se dashboard (same Wi-Fi)

Settings → Phone se dashboard → PIN banao → "Phone access ON" → Save → Rare Cash band karke dobara kholo
(Windows Firewall poochhe to Private networks pe Allow). Phone browser mein `http://<PC ka IP>:8000` (Settings mein dikhta hai) → PIN.
5 galat PIN = 5 minute lock. PIN badalne pe purane phone logins band ho jaate hain.

## 8. Clip style

Settings → Clips: face / center / blur, subtitles, **hook title** (upar bold box), **progress bar**, **slow zoom**, **music**.
Music ke liye Rare Cash folder ke `music` folder mein **copyright-free** .mp3 daalo (khali = no music). Copyright wale gaane = video block ho sakti hai.

## 9. Asli kamai (Vyro)

Bot har 12 ghante Vyro se balance, pending aur har submission ka status/kamai padhta hai (sirf padhta hai: withdraw, payout,
bank wale buttons kabhi click nahi karta). Earnings → "⟳ Vyro se asli kamai lao" se abhi bhi kar sakte ho.

## Duplicate se bachav

Ek hi video alag links se aaye (youtu.be / youtube.com / shorts / Drive ke alag link) ya same file dobara aaye,
to bot nayi clips nahi banata: purani clips hi use karta hai, aur ek clip ek platform pe ek hi baar post hoti hai.

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
| `clipper/uploader.py` / `clipper/instagram.py` / `clipper/tiktok.py` | YouTube / Instagram / TikTok posting + views |
| `clipper/telegram.py` | Telegram alerts + commands |
| `clipper/vpn.py` / `clipper/network.py` | built-in VPN + VPN guard |
| `clipper/state.py` | SQLite memory (`bot.db`) |
