'use client';

import { Users } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAdminUsers } from '@/features/admin/hooks';
import { formatToman } from '@/lib/currency';
import { formatDateTime } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';

/** Admin user list: search, status filter, click-through to detail. */
export default function AdminUsersPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'' | 'active' | 'inactive'>('');

  const users = useAdminUsers({
    page,
    search,
    isActive: statusFilter === '' ? '' : statusFilter === 'active',
  });

  const applySearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(searchInput.trim());
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">کاربران</h1>

      <section aria-label="جست‌وجو و فیلتر کاربران" className="card">
        <form onSubmit={applySearch} className="flex flex-col gap-3 sm:flex-row">
          <div className="flex-1">
            <label htmlFor="user-search" className="sr-only">
              جست‌وجوی کاربر
            </label>
            <input
              id="user-search"
              type="search"
              placeholder="جست‌وجو با شماره موبایل…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="input"
              dir="ltr"
            />
          </div>
          <div className="flex gap-2">
            <label htmlFor="status-filter" className="sr-only">
              فیلتر وضعیت
            </label>
            <select
              id="status-filter"
              className="input sm:w-40"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as '' | 'active' | 'inactive');
                setPage(1);
              }}
            >
              <option value="">همه وضعیت‌ها</option>
              <option value="active">فعال</option>
              <option value="inactive">غیرفعال</option>
            </select>
            <button type="submit" className="btn-primary">
              جست‌وجو
            </button>
          </div>
        </form>
      </section>

      {users.isLoading && <LoadingSpinner />}
      {users.isError && <ErrorState message="بارگذاری کاربران ناموفق بود." onRetry={() => users.refetch()} />}
      {users.data && users.data.items.length === 0 && (
        <EmptyState icon={Users} title="کاربری پیدا نشد" description="با این فیلترها کاربری یافت نشد." />
      )}
      {users.data && users.data.items.length > 0 && (
        <>
          <ResponsiveTable
            ariaLabel="فهرست کاربران"
            keyOf={(u) => u.id}
            rows={users.data.items}
            onRowClick={(u) => router.push(`/noura-roham1197/users/${u.id}`)}
            cardHeader={(u) => (
              <span dir="ltr">
                {u.mobile_masked && u.mobile_masked !== '***' ? u.mobile_masked : '🤖 بات'}
                {u.channels && Object.keys(u.channels).map((p) => (
                  <span key={p} className="badge-info mr-1">{p === 'bale' ? 'بله' : p}</span>
                ))}
              </span>
            )}
            columns={[
              {
                header: 'موبایل',
                render: (u) => (
                  <span dir="ltr" className="tabular-nums">
                    {u.mobile_masked && u.mobile_masked !== '***' ? u.mobile_masked : '🤖 بات'}
                    {u.channels && Object.keys(u.channels).map((p) => (
                      <span key={p} className="badge-info mr-1">{p === 'bale' ? 'بله' : p}</span>
                    ))}
                  </span>
                ),
              },
              {
                header: 'آیدی',
                render: (u) => {
                  const botIds = u.channels
                    ? Object.entries(u.channels)
                        .filter(([, info]) => info.platform_user_id)
                        .map(([p, info]) => {
                          const label = p === 'bale' ? 'بله' : p;
                          const username = info.platform_username ? `@${info.platform_username} ` : '';
                          return `${label}: ${username}${info.platform_user_id}`;
                        })
                    : [];
                  return botIds.length > 0 ? (
                    <span dir="ltr" className="tabular-nums text-sm">{botIds.join('، ')}</span>
                  ) : (
                    <span className="text-neutral-400">—</span>
                  );
                },
              },
              {
                header: 'وضعیت',
                render: (u) =>
                  u.is_active ? (
                    <span className="badge-success">فعال</span>
                  ) : (
                    <span className="badge-danger">غیرفعال</span>
                  ),
              },
              {
                header: 'موجودی',
                render: (u) => <span className="tabular-nums">{formatToman(u.balance_irr)}</span>,
              },
              {
                header: 'مجموع مصرف',
                render: (u) => <span className="tabular-nums">{formatToman(u.total_spent_irr)}</span>,
                hideOnCard: true,
              },
              { header: 'عضویت', render: (u) => formatDateTime(u.created_at) },
            ]}
          />
          <Pagination page={page} totalPages={users.data.meta.total_pages} totalItems={users.data.meta.total_items} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
