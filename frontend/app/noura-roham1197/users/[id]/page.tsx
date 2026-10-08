'use client';

import { MessageSquare, NotebookText } from 'lucide-react';
import { History, Images } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useAdminUser,
  useUpdateUserStatus,
  useUserActivity,
  useUserAssets,
  useUserChatMessages,
  useUserChats,
  useUserWalletTransactions,
  useWalletAdjustment,
  type UserChat,
} from '@/features/admin/hooks';
import { formatToman, tomanToIrr } from '@/lib/currency';
import { formatDateTime, formatNumber } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Modal } from '@/components/Modal';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { ActivityKind, AssetItem } from '@/types/api';

const ACTIVITY_LABELS: Record<ActivityKind, string> = {
  login: 'ورود',
  ai_request: 'درخواست هوش مصنوعی',
  payment: 'پرداخت',
  wallet: 'کیف پول',
  gallery: 'نگارخانه',
  admin_action: 'اقدام ادمین',
};

const ASSET_LABELS: Record<AssetItem['kind'], string> = {
  generated_image: 'تصویر تولیدشده',
  chat_input_image: 'تصویر ورودی چت',
  input_image_original: 'ورودی اصلی ویرایش',
  input_image_processed: 'ورودی پردازش‌شده',
  input_audio: 'صوت ورودی',
  output_audio: 'صوت خروجی',
};

type Tab = 'activity' | 'chats' | 'generated' | 'chat_input' | 'edit_input' | 'wallet' | 'session';

const statusSchema = z.object({
  reason: z.string().trim().min(3, 'دلیل تغییر وضعیت را بنویسید (حداقل ۳ حرف).'),
});
const adjustmentSchema = z.object({
  amountToman: z
    .number({ invalid_type_error: 'مبلغ را وارد کنید.' })
    .refine((v) => v !== 0, 'مبلغ نباید صفر باشد.'),
  reason: z.string().trim().min(3, 'دلیل اصلاح موجودی را بنویسید (حداقل ۳ حرف).'),
});

/** Admin user detail: info, balance, status toggle, wallet adjustment, tabs. */
export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('activity');
  const [activityPage, setActivityPage] = useState(1);
  const [chatsPage, setChatsPage] = useState(1);
  const [chatMsgPage, setChatMsgPage] = useState(1);
  const [selectedChat, setSelectedChat] = useState<UserChat | null>(null);
  const [walletPage, setWalletPage] = useState(1);
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [adjustModalOpen, setAdjustModalOpen] = useState(false);

  const user = useAdminUser(id);
  const activity = useUserActivity(id, activityPage);
  const chats = useUserChats(id, chatsPage);
  const chatMessages = useUserChatMessages(id, selectedChat?.id ?? null, chatMsgPage);
  const walletTx = useUserWalletTransactions(id, walletPage);
  const generatedAssets = useUserAssets(id, 'generated', tab === 'generated');
  const chatInputAssets = useUserAssets(id, 'chat_input', tab === 'chat_input');
  const editInputAssets = useUserAssets(id, 'edit_input', tab === 'edit_input');

  const updateStatus = useUpdateUserStatus();
  const adjustWallet = useWalletAdjustment();

  const statusForm = useForm<z.infer<typeof statusSchema>>({ resolver: zodResolver(statusSchema) });
  const adjustForm = useForm<z.infer<typeof adjustmentSchema>>({ resolver: zodResolver(adjustmentSchema) });

  if (user.isLoading) return <LoadingSpinner label="در حال بارگذاری کاربر…" />;
  if (user.isError || !user.data) {
    return (
      <ErrorState
        message={user.error instanceof ApiError ? getErrorMessage(user.error.code, user.error.message) : 'کاربر یافت نشد.'}
        onRetry={() => user.refetch()}
      />
    );
  }

  const u = user.data;

  const submitStatusChange = (values: z.infer<typeof statusSchema>) => {
    updateStatus.mutate(
      { id, isActive: !u.is_active, reason: values.reason },
      {
        onSuccess: () => {
          setStatusModalOpen(false);
          statusForm.reset();
          toast(u.is_active ? 'کاربر غیرفعال شد.' : 'کاربر فعال شد.', 'success');
        },
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const submitAdjustment = (values: z.infer<typeof adjustmentSchema>) => {
    adjustWallet.mutate(
      { id, amountIrr: tomanToIrr(values.amountToman), reason: values.reason },
      {
        onSuccess: () => {
          setAdjustModalOpen(false);
          adjustForm.reset();
          toast('موجودی اصلاح شد و در دفترکل ثبت شد.', 'success');
        },
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const tabs: { value: Tab; label: string }[] = [
    { value: 'activity', label: 'timeline فعالیت' },
    { value: 'chats', label: 'گفتگوها' },
    { value: 'generated', label: 'تصاویر تولیدشده' },
    { value: 'chat_input', label: 'تصاویر ورودی چت' },
    { value: 'edit_input', label: 'تصاویر ورودی ویرایش' },
    { value: 'wallet', label: 'تراکنش‌های کیف پول' },
    { value: 'session', label: 'آخرین نشست' },
  ];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">جزئیات کاربر</h1>

      {/* Summary card */}
      <section aria-label="خلاصه کاربر" className="card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <p className="text-lg font-bold" dir="ltr">
              {u.mobile_masked && u.mobile_masked !== '***' ? u.mobile_masked : '🤖 کاربر بات'}
            </p>
            {u.channels && Object.keys(u.channels).length > 0 && (
              <p className="flex flex-wrap gap-1">
                {Object.entries(u.channels).map(([platform, info]) => (
                  <span key={platform} className="badge-info">
                    {platform === 'bale' ? '📱 بله' : platform === 'eitaa' ? '📱 ایتا' : platform === 'telegram' ? '📱 تلگرام' : platform}
                    {info.usage_count ? ` (${info.usage_count})` : ''}
                  </span>
                ))}
              </p>
            )}
            <p className="text-sm text-neutral-500 dark:text-slate-400">
              عضویت: {formatDateTime(u.created_at)}
              {u.last_login_at && <> — آخرین ورود: {formatDateTime(u.last_login_at)}</>}
            </p>
            <p>
              {u.is_active ? <span className="badge-success">فعال</span> : <span className="badge-danger">غیرفعال</span>}
            </p>
          </div>
          <div className="text-left">
            <p className="text-sm text-neutral-500 dark:text-slate-400">موجودی</p>
            <p className="text-2xl font-extrabold tabular-nums">{formatToman(u.balance_irr)}</p>
            <p className="mt-1 text-xs text-neutral-500">مجموع مصرف: {formatToman(u.total_spent_irr)}</p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={() => setStatusModalOpen(true)} className={u.is_active ? 'btn-danger btn-sm' : 'btn-primary btn-sm'}>
            {u.is_active ? 'غیرفعال کردن کاربر' : 'فعال کردن کاربر'}
          </button>
          <button type="button" onClick={() => setAdjustModalOpen(true)} className="btn-secondary btn-sm">
            اصلاح موجودی
          </button>
        </div>
      </section>

      {/* Tabs */}
      <div role="tablist" aria-label="بخش‌های جزئیات کاربر" className="flex gap-2 overflow-x-auto pb-1">
        {tabs.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`btn-sm whitespace-nowrap rounded-xl px-4 font-semibold transition-colors ${
              tab === t.value
                ? 'bg-brand-600 text-white dark:bg-brand-500 dark:text-navy-950'
                : 'btn-secondary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Activity timeline */}
      {tab === 'activity' && (
        <section aria-label="timeline فعالیت">
          {activity.isLoading && <LoadingSpinner />}
          {activity.isError && <ErrorState message="بارگذاری فعالیت‌ها ناموفق بود." onRetry={() => activity.refetch()} />}
          {activity.data && activity.data.items.length === 0 && (
            <EmptyState icon={History} title="فعالیتی ثبت نشده" description="هنوز فعالیتی برای این کاربر ثبت نشده است." />
          )}
          {activity.data && activity.data.items.length > 0 && (
            <>
              <ol className="relative flex flex-col gap-4 border-r-2 border-neutral-200 pr-6 dark:border-white/10">
                {activity.data.items.map((a) => (
                  <li key={a.id} className="relative">
                    <span aria-hidden="true" className="absolute -right-[31px] top-1 h-3 w-3 rounded-full bg-brand-600 dark:bg-brand-400" />
                    <div className="card !p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-bold">
                          <span className="badge badge-info ml-2">{ACTIVITY_LABELS[a.kind]}</span>
                          {a.title}
                        </p>
                        <time className="text-xs text-neutral-500 dark:text-slate-400">{formatDateTime(a.created_at)}</time>
                      </div>
                      {a.description && <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">{a.description}</p>}
                    </div>
                  </li>
                ))}
              </ol>
              <Pagination page={activityPage} totalPages={activity.data.meta.total_pages} onPageChange={setActivityPage} />
            </>
          )}
        </section>
      )}

      {/* User chats */}
      {tab === 'chats' && (
        <section aria-label="گفتگوهای کاربر">
          {chats.isLoading && <LoadingSpinner />}
          {chats.isError && <ErrorState message="بارگذاری گفتگوها ناموفق بود." onRetry={() => chats.refetch()} />}
          {chats.data && chats.data.items.length === 0 && (
            <EmptyState icon={MessageSquare} title="گفتگویی نیست" description="این کاربر هنوز گفتگویی نداشته است." />
          )}
          {chats.data && chats.data.items.length > 0 && (
            <>
              <ul className="flex flex-col gap-2">
                {chats.data.items.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedChat(c)}
                      className="card !p-4 w-full text-right transition hover:border-brand-400"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-bold" dir="auto">{c.title || 'بدون عنوان'}</p>
                        <time className="text-xs text-neutral-500 dark:text-slate-400">{c.created_at ? formatDateTime(c.created_at) : ''}</time>
                      </div>
                      {c.preview && <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400" dir="auto">{c.preview}…</p>}
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-neutral-500 dark:text-slate-400">
                        {c.model && <span className="badge badge-info">{c.model}</span>}
                        <span>{formatNumber(c.message_count)} پیام</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
              <Pagination page={chatsPage} totalPages={chats.data.meta.total_pages} onPageChange={setChatsPage} />
            </>
          )}
        </section>
      )}

      {/* Chat messages modal */}
      <Modal
        open={!!selectedChat}
        title={selectedChat?.title || 'گفتگو'}
        onClose={() => { setSelectedChat(null); setChatMsgPage(1); }}
        maxWidth="max-w-2xl"
      >
        {chatMessages.isLoading && <LoadingSpinner />}
        {chatMessages.isError && <ErrorState message="بارگذاری پیام‌ها ناموفق بود." onRetry={() => chatMessages.refetch()} />}
        {chatMessages.data && (
          <>
            <ul className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto">
              {chatMessages.data.items.map((m) => (
                <li
                  key={m.id}
                  className={`rounded-lg p-3 text-sm ${m.role === 'user' ? 'self-end bg-brand-100 dark:bg-brand-900/30' : 'self-start bg-neutral-100 dark:bg-white/5'} max-w-[90%]`}
                  dir="auto"
                >
                  <p className="mb-1 text-xs font-bold text-neutral-500 dark:text-slate-400">
                    {m.role === 'user' ? 'کاربر' : 'نورا'}
                  </p>
                  <p className="whitespace-pre-wrap">{m.content}</p>
                  {(m.input_tokens || m.output_tokens) && (
                    <p className="mt-1 text-[11px] text-neutral-400">
                      {m.input_tokens ? `${formatNumber(m.input_tokens)} ورودی` : ''}
                      {m.input_tokens && m.output_tokens ? ' · ' : ''}
                      {m.output_tokens ? `${formatNumber(m.output_tokens)} خروجی` : ''}
                    </p>
                  )}
                </li>
              ))}
            </ul>
            <Pagination page={chatMsgPage} totalPages={chatMessages.data.meta.total_pages} onPageChange={setChatMsgPage} />
          </>
        )}
      </Modal>

      {/* Generated images */}
      {tab === 'generated' && <AssetGrid query={generatedAssets} emptyTitle="تصویر تولیدشده‌ای نیست" />}

      {/* Chat input images */}
      {tab === 'chat_input' && <AssetGrid query={chatInputAssets} emptyTitle="تصویر ورودی چتی نیست" />}

      {/* Edit input images (original upload + processed derivative) */}
      {tab === 'edit_input' && <AssetGrid query={editInputAssets} emptyTitle="تصویر ورودی ویرایشی نیست" />}

      {/* Wallet transactions */}
      {tab === 'wallet' && (
        <section aria-label="تراکنش‌های کیف پول کاربر">
          {walletTx.isLoading && <LoadingSpinner />}
          {walletTx.isError && <ErrorState message="بارگذاری تراکنش‌ها ناموفق بود." onRetry={() => walletTx.refetch()} />}
          {walletTx.data && walletTx.data.items.length === 0 && (
            <EmptyState icon={NotebookText} title="تراکنشی نیست" description="هنوز تراکنشی برای این کاربر ثبت نشده است." />
          )}
          {walletTx.data && walletTx.data.items.length > 0 && (
            <>
              <ResponsiveTable
                ariaLabel="تراکنش‌های کیف پول کاربر"
                keyOf={(t) => t.id}
                rows={walletTx.data.items}
                cardHeader={(t) => (
                  <span className={`tabular-nums ${t.amount_irr >= 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                    {t.amount_irr >= 0 ? '+' : ''}{formatToman(t.amount_irr)}
                  </span>
                )}
                columns={[
                  {
                    header: 'مبلغ',
                    render: (t) => (
                      <span className={`tabular-nums ${t.amount_irr >= 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                        {t.amount_irr >= 0 ? '+' : ''}{formatToman(t.amount_irr)}
                      </span>
                    ),
                  },
                  { header: 'شرح', render: (t) => t.description ?? '—' },
                  { header: 'موجودی بعد', render: (t) => <span className="tabular-nums">{formatToman(t.balance_after_irr)}</span>, hideOnCard: true },
                  { header: 'تاریخ', render: (t) => formatDateTime(t.created_at) },
                ]}
              />
              <Pagination page={walletPage} totalPages={walletTx.data.meta.total_pages} onPageChange={setWalletPage} />
            </>
          )}
        </section>
      )}

      {/* Last session */}
      {tab === 'session' && (
        <section aria-label="آخرین نشست کاربر">
          <div className="card">
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs text-neutral-500">آخرین ورود</dt>
                <dd className="font-bold">{u.last_login_at ? formatDateTime(u.last_login_at) : '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-neutral-500">آی‌پی</dt>
                <dd className="font-bold tabular-nums" dir="ltr">{u.last_login_ip ?? '—'}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-neutral-500">دستگاه / مرورگر</dt>
                <dd className="break-all text-sm" dir="ltr">{u.last_login_user_agent ?? '—'}</dd>
              </div>
            </dl>
            {!u.last_login_at && (
              <p className="mt-3 text-sm text-neutral-500">هنوز ورودی ثبت نشده است.</p>
            )}
          </div>
        </section>
      )}

      {/* Status change modal */}
      <Modal open={statusModalOpen} title={u.is_active ? 'غیرفعال کردن کاربر' : 'فعال کردن کاربر'} onClose={() => setStatusModalOpen(false)}>
        <p className="mb-4 text-sm text-neutral-600 dark:text-slate-400">
          {u.is_active
            ? 'با غیرفعال شدن، نشست‌های فعال کاربر لغو و درخواست‌های جدید او متوقف می‌شود؛ سوابق قبلی حفظ می‌ماند.'
            : 'کاربر دوباره فعال می‌شود و می‌تواند از سرویس‌ها استفاده کند.'}
        </p>
        <form onSubmit={statusForm.handleSubmit(submitStatusChange)} className="flex flex-col gap-4">
          <div>
            <label htmlFor="status-reason" className="label">
              دلیل (ثبت در گزارش حسابرسی)
            </label>
            <textarea
              id="status-reason"
              rows={3}
              className={`input resize-none ${statusForm.formState.errors.reason ? 'input-error' : ''}`}
              {...statusForm.register('reason')}
            />
            {statusForm.formState.errors.reason && (
              <p role="alert" className="field-error">
                {statusForm.formState.errors.reason.message}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={updateStatus.isPending} className={u.is_active ? 'btn-danger flex-1' : 'btn-primary flex-1'}>
              {updateStatus.isPending ? 'در حال ثبت…' : 'تأیید'}
            </button>
            <button type="button" onClick={() => setStatusModalOpen(false)} className="btn-secondary flex-1">
              انصراف
            </button>
          </div>
        </form>
      </Modal>

      {/* Wallet adjustment modal */}
      <Modal open={adjustModalOpen} title="اصلاح موجودی کاربر" onClose={() => setAdjustModalOpen(false)}>
        <p className="mb-4 text-sm text-neutral-600 dark:text-slate-400">
          مبلغ مثبت موجودی را افزایش و مبلغ منفی آن را کاهش می‌دهد. هر اصلاح با دلیل، در دفترکل ثبت می‌شود.
        </p>
        <form onSubmit={adjustForm.handleSubmit(submitAdjustment)} className="flex flex-col gap-4">
          <div>
            <label htmlFor="adjust-amount" className="label">
              مبلغ (تومان؛ منفی برای کسر)
            </label>
            <input
              id="adjust-amount"
              type="number"
              inputMode="numeric"
              step={1}
              dir="ltr"
              className={`input text-left ${adjustForm.formState.errors.amountToman ? 'input-error' : ''}`}
              {...adjustForm.register('amountToman', { valueAsNumber: true })}
            />
            {adjustForm.formState.errors.amountToman && (
              <p role="alert" className="field-error">
                {adjustForm.formState.errors.amountToman.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="adjust-reason" className="label">
              دلیل (ثبت در دفترکل و گزارش حسابرسی)
            </label>
            <textarea
              id="adjust-reason"
              rows={3}
              className={`input resize-none ${adjustForm.formState.errors.reason ? 'input-error' : ''}`}
              {...adjustForm.register('reason')}
            />
            {adjustForm.formState.errors.reason && (
              <p role="alert" className="field-error">
                {adjustForm.formState.errors.reason.message}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={adjustWallet.isPending} className="btn-primary flex-1">
              {adjustWallet.isPending ? 'در حال ثبت…' : 'ثبت اصلاح'}
            </button>
            <button type="button" onClick={() => setAdjustModalOpen(false)} className="btn-secondary flex-1">
              انصراف
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function AssetGrid({
  query,
  emptyTitle,
}: {
  query: { isLoading: boolean; isError: boolean; data?: AssetItem[]; refetch: () => void };
  emptyTitle: string;
}) {
  if (query.isLoading) return <LoadingSpinner />;
  if (query.isError) return <ErrorState message="بارگذاری تصاویر ناموفق بود." onRetry={() => query.refetch()} />;
  const items = query.data ?? [];
  if (items.length === 0) {
    return <EmptyState icon={Images} title={emptyTitle} description="موردی برای نمایش وجود ندارد." />;
  }
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {items.map((a) => (
        <li key={a.id} className="overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-100 dark:border-white/10 dark:bg-navy-900">
          <div className="relative aspect-square w-full">
            <img src={a.thumbnail_url ?? a.url} alt={ASSET_LABELS[a.kind]} loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
          </div>
          <p className="px-3 py-2 text-xs text-neutral-500 dark:text-slate-400">
            {ASSET_LABELS[a.kind]} — {formatDateTime(a.created_at)}
          </p>
        </li>
      ))}
    </ul>
  );
}
