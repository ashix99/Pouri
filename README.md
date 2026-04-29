# Pouri FX Bot

ربات تلگرامی محاسبه سود و ضرر معاملات ارزی با `Telethon` و منطق دقیق دو مرحله‌ای.

## امکانات

- پردازش فقط در چت خصوصی و فقط برای پیام‌های متنی
- نادیده گرفتن دستورها مثل `/start`
- اجرای محاسبات با `Decimal` و دقت `50`
- استانداردسازی اعداد فارسی/عربی، فاصله‌ها و جداکننده‌های هزارگان
- گزارش ردیف‌های ردشده یا مشکوک با دلیل
- مرحله اول بدون نیاز به `FEE`
- مرحله دوم با جدول کامل در صورت وجود `FEE`
- نگه‌داشتن لیست معلق کاربر تا وقتی که بعدا فقط `FEE` را بفرستد
- پشتیبانی از استیکر برای شروع، موفقیت، هشدار و خطا از طریق `.env`
- ساخت فایل `PDF` با جدول‌بندی مشخص و ارسال آن برای کاربر

## نصب

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

مقادیر `API_ID` و `API_HASH` را از `my.telegram.org` و `BOT_TOKEN` را از `@BotFather` بگذارید.

اگر می‌خواهید ربات قبل از پیام‌ها استیکر بفرستد، مسیر فایل استیکرها را در این متغیرها بگذارید:

- `STICKER_START`
- `STICKER_SUCCESS`
- `STICKER_WARNING`
- `STICKER_ERROR`

برای فونت PDF، ربات اول اگر مسیر خاصی داده باشید از همان استفاده می‌کند؛ وگرنه از فونت‌های عمومی سیستم مثل `DejaVu Sans`، `Tahoma` یا fallbackهای رایج استفاده می‌کند.

اگر روی سرور هیچ فونت مناسبی پیدا نشود، ربات به‌صورت خودکار فونت آزاد `Vazirmatn` را داخل پوشه `fonts/` دانلود و cache می‌کند.

اگر خواستید `Yekan Bakh` را دستی override کنید، این مسیرها هم پشتیبانی می‌شوند:

- `fonts/YekanBakh-Regular.ttf`
- `fonts/YekanBakh-Bold.ttf`

یا می‌توانید مسیر دلخواه را هم ست کنید:

- `PDF_FONT_PATH`
- `PDF_FONT_BOLD_PATH`

اگر هیچ فونت دلخواهی تنظیم نکنید، ربات با فونت‌های پیش‌فرض قابل‌دسترس سیستم PDF را می‌سازد.

## اجرا

```powershell
python main.py
```

## GitHub

این پروژه عمدا فایل‌های حساس را داخل ریپو نمی‌برد:

- `.env`
- `*.session`
- فایل‌های موقت و کش

مراحل پیشنهادی:

```powershell
git init
git add .
git commit -m "Initial bot version"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

قبل از `git add .` مطمئن شوید `.env` واقعی شما داخل `.gitignore` مانده و فایل `.env.example` فقط نمونهٔ بدون راز است.

## دیپلوی سرور

برای سرور لینوکسی، فایل نمونهٔ `systemd` اینجاست:

- [deploy/pouri-bot.service](</C:/Users/Ashix/Desktop/Chiz Miz/python/pouri/deploy/pouri-bot.service>)

روال پیشنهادی روی سرور:

1. ریپو را داخل `/opt/pouri` کلون کنید.
2. پایتون و `venv` را نصب کنید.
3. `.env` واقعی را روی سرور بسازید.
4. اگر PDF باید با `Yekan Bakh` باشد، فونت‌ها را در پوشه `fonts/` بگذارید یا مسیرشان را در `.env` ست کنید.
5. سرویس `systemd` را کپی و فعال کنید.

نمونه:

```bash
sudo mkdir -p /opt/pouri
sudo chown $USER:$USER /opt/pouri
git clone https://github.com/<your-user>/<your-repo>.git /opt/pouri
cd /opt/pouri
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

بعد از تنظیم `.env`:

```bash
sudo cp deploy/pouri-bot.service /etc/systemd/system/pouri-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now pouri-bot
sudo systemctl status pouri-bot
```

برای دیدن لاگ:

```bash
journalctl -u pouri-bot -f
```

## نمونه پیام

```text
فروش
6م علی 153200
2.5m رضا 149950

خرید
4م سارا 151800
1.75m مهدی 150400

FEE: 152600
```

اگر `FEE` را نگذارید، ربات مرحله اول را می‌فرستد و بعد از شما `FEE` می‌خواهد.

اگر گزارش قابل پردازش باشد، ربات علاوه بر متن، یک فایل `PDF` هم با جدول‌های خانه‌بندی‌شده ارسال می‌کند.
