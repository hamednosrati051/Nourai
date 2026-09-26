# اتصال به مدل‌های هوش مصنوعی از طریق متیس (MetisAI)

این سند مرجع اتصال «نورا» به مدل‌های AI است. نورا مستقیم به OpenAI و...
وصل نمی‌شود؛ همه‌ی مدل‌ها از طریق **درگاه متیس** فراخوانی می‌شوند.

- داشبورد متیس: https://console.metisai.ir/dashboard
- مستندات متیس: https://docs.metisai.ir
- Endpoint سازگار با OpenAI: `https://api.metisai.ir/openai/v1`

## ۱. ارائه‌دهنده‌های قابل اتصال در متیس

متیس «اتصال مستقیم به مدل‌ها» را برای این ارائه‌دهنده‌ها دارد:

| ارائه‌دهنده | توضیح |
|---|---|
| OpenAI | مدل‌های GPT |
| Anthropic | مدل‌های Claude |
| TypeSafe AI | — |
| DeepSeek | مدل‌های DeepSeek |
| MiMo (Xiaomi) | مدل‌های شیائومی |
| GLM (Z.AI) | مدل‌های Zhipu |
| Kimi K3 (Moonshot) | مدل‌های Moonshot |
| Gemini | مدل‌های Google |

نکته‌ی مهم: چون متیس یک endpoint سازگار با OpenAI می‌دهد، سمت نورا فقط
**یک adapter** لازم است (کلاینت HTTP سازگار با OpenAI) و انتخاب مدلِ نهایی
با `provider_model_name` انجام می‌شود — یعنی همان شناسه‌ی مدلی که در
داشبورد متیس می‌بینید.

## ۲. مقادیر اتصال

| مقدار | توضیح |
|---|---|
| `base_url` | `https://api.metisai.ir/openai/v1` |
| `Authorization` | هدر `Bearer <API_KEY>` |
| `API_KEY` | از داشبورد متیس (console.metisai.ir) گرفته می‌شود؛ **هرگز در کد یا دیتابیس ذخیره نشود** — فقط env / secret manager |
| `model` | شناسه‌ی دقیق مدل در داشبورد متیس (مثلاً `gpt-4.1-mini`) |

مثال curl برای تست دستی:

```bash
curl https://api.metisai.ir/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $METIS_API_KEY" \
  -d '{"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "سلام"}]}'
```

## ۳. ثبت مدل در کاتالوگ نورا

ثبت مدل با `POST /api/v1/admin/models` انجام می‌شود. فیلدهای درست:

| فیلد | اجباری | مثال |
|---|---|---|
| `slug` | بله | `gpt-4-1-mini` |
| `display_name` | بله | `GPT-4.1 Mini` |
| `capability` | بله | `text` ،`speech_to_text` ،`text_to_speech` ،`image` |
| `provider_key` | بله | `metis` |
| `provider_model_name` | بله | شناسه‌ی مدل در داشبورد متیس |
| `pricing_type` | خیر (پیش‌فرض `token`) | `token` |
| `tokenizer_encoding` | برای مدل متنی اجباری | مثلاً `o200k_base` |
| `config_json` | خیر | تنظیمات غیرمحرمانه |
| `description` | خیر | توضیح |
| `is_active` | خیر (پیش‌فرض true) | — |

> ⚠️ **مشکل شناخته‌شده:** فرم «مدل جدید» در پنل ادمین (`/admin/models`)
> فیلدهای قدیمی می‌فرستد (`name`، `service`، `provider`، `pricing_hint`) که با
> قرارداد بالا نمی‌خواند و ساخت مدل با خطای ۴۲۲ مواجه می‌شود. تا زمان فیکس
> فرم، مدل را مستقیم با API (مثلاً curl) ثبت کنید.

## ۴. تنظیمات env برای adapter

وضعیت فعلی: در `app/ai/adapters.py` فقط adapterهای `fake` پیاده شده‌اند.
برای اتصال واقعی، adapter سازگار با OpenAI باید پیاده شود و سپس:

```bash
AI_TEXT_PROVIDER=openai_compat
AI_TEXT_BASE_URL=https://api.metisai.ir/openai/v1
AI_TEXT_API_KEY=<کلید متیس>
# به همین ترتیب برای صوت و تصویر:
AI_AUDIO_PROVIDER=openai_compat
AI_IMAGE_PROVIDER=openai_compat
```

## ۵. قیمت‌گذاری — فعلاً دستی

قیمت‌ها خودکار از متیس خوانده نمی‌شوند. برای هر مدل، تعرفه را دستی در
پنل ادمین (بخش «تعرفه‌ها») یا با `POST /api/v1/admin/pricing-rules` تعریف کنید:

| فیلد | توضیح |
|---|---|
| `model_id` | شناسه‌ی مدل در کاتالوگ نورا |
| `billing_unit` | واحد محاسبه: `token` ،`second` ،`request` ،`image` |
| `unit_size` | اندازه‌ی یک واحد قیمت (مثلاً `1000` برای هر ۱۰۰۰ توکن) |
| `unit_price_irr` | قیمت هر واحد به **تومان** (عدد صحیح) |
| `dimension_key` / `quality_key` | برای تعرفه‌ی وابسته به ابعاد/کیفیت (اختیاری) |
| `minimum_charge_irr` / `maximum_charge_irr` | سقف حداقل/حداکثر (اختیاری) |
| `rounding_mode` | `up` ،`down` ،`nearest` (پیش‌فرض `up`) |
| `effective_from` / `effective_to` | بازه‌ی اعتبار (اختیاری) |

**روش کار پیشنهادی:**
1. در داشبورد متیس قیمت مدل را ببینید (مثلاً دلار به‌ازای هر ۱M توکن).
2. به تومان تبدیل کنید و برای `unit_size=1000` (هر ۱۰۰۰ توکن) وارد کنید.
3. قوانین نسخه‌دار هستند (`version`)؛ برای تغییر قیمت، قانون جدید بسازید.

> قیمت‌های متیس ممکن است تغییر کنند؛ بازبینی دوره‌ای تعرفه‌ها با مسئول محصول است.
