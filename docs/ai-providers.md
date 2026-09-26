# اتصال به مدل‌های هوش مصنوعی

این سند مرجع اتصال «نورا» به مدل‌های AI است.

> **اصل طراحی:** کد نورا به هیچ provider خاصی (از جمله متیس) قفل نیست.
> متیس فقط **یک نمونه** است. معماری باید provider-agnostic باشد: اضافه کردن
> یک provider جدید = فقط env و ثبت مدل در کاتالوگ، بدون تغییر کد.

## ۱. معماری provider-agnostic

- هر مدل در کاتالوگ یک `provider_key` دارد (مثلاً `metis`، `openai`، ...).
- یک کلاینت HTTP **مشترک و سازگار با OpenAI** (`/chat/completions` و...)
  همه‌ی providerها را صدا می‌زند؛ تفاوتشان فقط `base_url` و `api_key` است.
- مشخصات هر provider با این اولویت resolve می‌شود:
  1. **فرم ادمین** — فیلدهای `base_url` و `api_key` روی فرم مدل (write-only؛
     API فقط `has_credentials` برمی‌گرداند، نه خود کلید).
  2. **env** — `AI_PROVIDER_<KEY>_BASE_URL` / `AI_PROVIDER_<KEY>_API_KEY`.
  3. **env عمومی** — `AI_TEXT_BASE_URL` / `AI_TEXT_API_KEY`.

```bash
AI_PROVIDER_<KEY>_BASE_URL=https://...
AI_PROVIDER_<KEY>_API_KEY=<secret>
```

مثال — متیس:

```bash
AI_PROVIDER_METIS_BASE_URL=https://api.metisai.ir/openai/v1
AI_PROVIDER_METIS_API_KEY=<کلید داشبورد متیس>
```

- انتخاب adapter در رانتایم با `provider_key` مدل انجام می‌شود، نه با
  if/else هاردکدشده برای هر provider.
- کلیدها **هرگز** در کد ذخیره نمی‌شوند. می‌توان آن‌ها را در فرم ادمین
  (راحت‌تر — ولی در دیتابیس می‌ماند) یا env / secret manager
  (امن‌تر — فقط روی سرور) نگه داشت.

## ۲. ارائه‌دهنده‌های قابل اتصال در متیس

متیس «اتصال مستقیم به مدل‌ها» را برای این ارائه‌دهنده‌ها دارد (به‌عنوان نمونه):

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

- داشبورد متیس: https://console.metisai.ir/dashboard
- مستندات متیس: https://docs.metisai.ir
- Endpoint سازگار با OpenAI متیس: `https://api.metisai.ir/openai/v1`

نکته: چون متیس endpoint سازگار با OpenAI می‌دهد، `provider_model_name` همان
شناسه‌ی مدلی است که در داشبورد متیس می‌بینید و همان کلاینت مشترک کافی است.

## ۲. مقادیر اتصال (نمونه: متیس)

| مقدار | توضیح |
|---|---|
| `base_url` | `https://api.metisai.ir/openai/v1` |
| `Authorization` | هدر `Bearer <API_KEY>` |
| `API_KEY` | از داشبورد provider گرفته می‌شود؛ **هرگز در کد یا دیتابیس ذخیره نشود** — فقط env / secret manager |
| `model` | شناسه‌ی دقیق مدل در داشبورد provider (مثلاً `gpt-4.1-mini`) |

مثال curl برای تست دستی (متیس):

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
برای اتصال واقعی، کلاینت مشترک سازگار با OpenAI باید پیاده شود؛ انتخاب
provider در رانتایم با `provider_key` مدل و envهای زیر انجام می‌شود:

```bash
# نوع adapter (مشترک برای همه‌ی providerها)
AI_TEXT_PROVIDER=openai_compat
AI_AUDIO_PROVIDER=openai_compat
AI_IMAGE_PROVIDER=openai_compat

# مشخصات هر provider — الگو: AI_PROVIDER_<KEY>_BASE_URL / _API_KEY
AI_PROVIDER_METIS_BASE_URL=https://api.metisai.ir/openai/v1
AI_PROVIDER_METIS_API_KEY=<کلید داشبورد متیس>
# provider بعدی بدون تغییر کد:
AI_PROVIDER_OPENAI_BASE_URL=https://api.openai.com/v1
AI_PROVIDER_OPENAI_API_KEY=<کلید OpenAI>
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
