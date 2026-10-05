'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAdminMe, useMe } from '@/features/auth/hooks';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorState } from './ErrorState';
import { ApiError, getErrorMessage } from '@/lib/api';

function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.code === 'UNAUTHORIZED');
}

function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 403 || error.code === 'FORBIDDEN');
}

function GuardShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {children}
    </main>
  );
}

/**
 * Guard for user panel routes: requires a valid user session.
 * On 401 the user is sent to the login page.
 */
export function UserGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading, error, refetch } = useMe();

  useEffect(() => {
    if (!isLoading && (isAuthError(error) || (!user && !error))) {
      router.replace('/auth/login');
    }
  }, [isLoading, error, user, router]);

  if (isLoading) {
    return (
      <GuardShell>
        <LoadingSpinner label="در حال بررسی نشست…" />
      </GuardShell>
    );
  }
  if (isAuthError(error) || !user) return null;
  if (error instanceof ApiError) {
    return (
      <GuardShell>
        <ErrorState message={getErrorMessage(error.code, error.message)} onRetry={() => refetch()} />
      </GuardShell>
    );
  }
  return <>{children}</>;
}

/**
 * Guard for admin panel routes: requires a valid admin session.
 * On 401/403 the admin is sent to the admin login page.
 */
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: admin, isLoading, error, refetch } = useAdminMe();

  useEffect(() => {
    if (!isLoading && (isAuthError(error) || isForbidden(error) || (!admin && !error))) {
      router.replace('/noura-roham1197/login');
    }
  }, [isLoading, error, admin, router]);

  if (isLoading) {
    return (
      <GuardShell>
        <LoadingSpinner label="در حال بررسی نشست ادمین…" />
      </GuardShell>
    );
  }
  if (isAuthError(error) || isForbidden(error) || !admin) return null;
  if (error instanceof ApiError) {
    return (
      <GuardShell>
        <ErrorState message={getErrorMessage(error.code, error.message)} onRetry={() => refetch()} />
      </GuardShell>
    );
  }
  return <>{children}</>;
}
