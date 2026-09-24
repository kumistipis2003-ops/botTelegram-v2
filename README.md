# 🎬 Video Downloader Bot Telegram — Tanpa Watermark

Bot Telegram serverless untuk mendownload video **tanpa watermark**, deploy di **Vercel**.

## ✅ Platform yang Didukung

| Platform | Status | Fitur |
|----------|--------|-------|
| 🎵 TikTok | ✅ | Video tanpa watermark |
| 🎶 Douyin | ✅ | Video tanpa watermark |
| 📕 RedNote (小红书) | ✅ | Video & gambar |
| 📸 Instagram | ✅ | Reels, Post |
| ▶️ YouTube | ✅ | Video & Shorts (480p) |
| 📘 Facebook | ✅ | Video & Reels |

## 🚀 Deploy ke Vercel (via GitHub)

### Step 1: Buat Bot di Telegram
1. Buka Telegram → cari `@BotFather`
2. Kirim `/newbot` → ikuti instruksi
3. Salin **token** yang diberikan

### Step 2: Push ke GitHub
```bash
cd "download vichin"
git init
git add .
git commit -m "Initial commit - Video Downloader Bot"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git push -u origin main
```

### Step 3: Deploy di Vercel
1. Buka [vercel.com](https://vercel.com) → Login dengan GitHub
2. Klik **"Add New Project"**
3. Import repo GitHub kamu
4. Di **Environment Variables**, tambahkan:
   - `BOT_TOKEN` = token dari BotFather
5. Klik **Deploy**

### Step 4: Aktifkan Webhook
Setelah deploy berhasil, buka URL ini **1x** di browser:

```
https://nama-project-kamu.vercel.app/api/set_webhook
```

Jika berhasil, akan muncul pesan:
```json
{"status": "success", "message": "Webhook berhasil di-set ke: ..."}
```

### Step 5: Test Bot
Buka bot di Telegram dan kirim link video! 🎉

## 📁 Struktur File

```
download vichin/
├── api/
│   └── webhook.py       # Handler utama (Flask + pyTelegramBotAPI)
├── bot.py               # Versi polling (untuk development lokal)
├── config.py            # Konfigurasi (versi polling)
├── downloader.py        # Modul download (versi polling)
├── requirements.txt     # Dependencies
├── vercel.json          # Konfigurasi Vercel
├── .gitignore           # File yang diabaikan git
├── .env.example         # Contoh environment
└── README.md            # Dokumentasi ini
```

## 🔧 Development Lokal

Untuk testing di komputer sendiri (mode polling):

```bash
# Install dependencies
pip install -r requirements.txt

# Buat file .env
copy .env.example .env
# Edit .env → isi BOT_TOKEN

# Jalankan
python api/webhook.py
```

Bot akan jalan dalam mode polling (tanpa webhook).

## ⚠️ Limitasi Vercel

| Aspek | Batas |
|-------|-------|
| Timeout | 10 detik (free) / 60 detik (Pro) |
| File size | Max 50MB (batas Telegram Bot API) |
| YouTube | Dibatasi 480p agar tidak timeout |
| FFmpeg | Tidak tersedia — YouTube merge terbatas |

> **Tips:** Untuk video YouTube panjang (>5 menit), kemungkinan akan timeout di free plan.
> Upgrade ke Vercel Pro untuk timeout 60 detik.

## 📋 Command Bot

| Command | Deskripsi |
|---------|-----------|
| `/start` | Mulai bot & lihat info |
| `/help` | Tampilkan bantuan |
