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
پنل ادمین (بخش «تعرفه‌ها») یا با `POST /api/v1/admin/pricing-rules` تعریف کنید.

### مدل‌های متنی: به‌ازای هر ۱ میلیون توکن

برای هر مدل متنی **دو** قانون تعریف کنید (ورودی و خروجی جدا):

| فیلد | قانون ورودی | قانون خروجی |
|---|---|---|
| `billing_unit` | `input_token` | `output_token` |
| `unit_size` | `1000000` | `1000000` |
| `unit_price_irr` | قیمت هر ۱M توکن ورودی به **تومان** | قیمت هر ۱M توکن خروجی به **تومان** |

مثال: اگر متیس برای مدلی ۲ دلار به‌ازای هر ۱M توکن ورودی می‌گیرد و دلار
۱۰۰٬۰۰۰ تومان است → `unit_price_irr = 200000`.

### تصویر و صوت: به‌ازای هر عدد

| سرویس | `billing_unit` | `unit_size` | `unit_price_irr` |
|---|---|---|---|
| تولید تصویر | `image_count` | `1` | قیمت هر تصویر به تومان |
| متن‌به‌گفتار / گفتاربه‌متن | `fixed_request` | `1` | قیمت هر درخواست به تومان |

(اگر بعداً خواستید صوت را ثانیه‌ای حساب کنید، `billing_unit = audio_second`
با `unit_size = 1` موجود است.)

### توکن مصرفی چطور محاسبه می‌شود؟

بله، با **tiktoken** و پیاده‌سازی فعلی درست است (`app/ai/tokens.py`):

- انکودینگ از فیلد `tokenizer_encoding` هر مدل خوانده می‌شود؛ هنگام ثبت مدل
  با `tiktoken.get_encoding()` اعتبارسنجی می‌شود و هیچ fallback پنهانی نیست —
  اگر انکودینگ نامعتبر باشد، مدل ذخیره نمی‌شود.
- **توکن ورودی:** روی دقیق‌ترین رشته‌ای که به provider فرستاده می‌شود شمرده
  می‌شود: پرامپت سیستمی + تا ۲۰ پیام آخر تاریخچه + پیام کاربر + نقش‌ها
  (`role`) + سربار framing خود provider.
- **توکن خروجی:** روی متن واقعی پاسخ تولیدشده شمرده می‌شود.
- قبل از تولید، با `max_output_tokens` **پیش‌فاکتور** گرفته می‌شود و بعد از
  تولید با تعداد واقعی تسویه می‌شود (`usage_source = "tiktoken"`).

> ⚠️ نکته: انکودینگ‌های tiktoken مال OpenAI هستند. برای مدل‌های غیر OpenAI
> (مثل Claude یا Gemini از طریق متیس) شمارش **تقریبی** است؛ نزدیک‌ترین
> انکودینگ را در `tokenizer_encoding` مدل ثبت کنید.
