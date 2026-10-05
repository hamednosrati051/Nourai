import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Fast-path route guards based on session cookie presence.
// Deep authentication is always verified via API (ProtectedRoute / server data).
// Cookie names are configurable via NEXT_PUBLIC_*_SESSION_COOKIE.

// Cookie names must match the backend session cookies (app/auth/sessions.py):
// users -> nourai_at / nourai_rt, admins -> nourai_admin_at / nourai_admin_rt.
const USER_COOKIE = process.env.NEXT_PUBLIC_USER_SESSION_COOKIE || 'nourai_at';
const ADMIN_COOKIE = process.env.NEXT_PUBLIC_ADMIN_SESSION_COOKIE || 'nourai_admin_at';

// Behind a reverse proxy request.url can carry the internal host
// (e.g. localhost:3000), so build login redirects from the real Host header.
function loginRedirect(request: NextRequest, pathname: string) {
  const proto = request.headers.get('x-forwarded-proto') ?? 'http';
  const host =
    request.headers.get('x-forwarded-host') ??
    request.headers.get('host') ??
    'localhost:3000';
  return NextResponse.redirect(new URL(pathname, `${proto}://${host}`));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith('/admin')) {
    if (pathname === '/admin/login') return NextResponse.next();
    if (!request.cookies.get(ADMIN_COOKIE)) {
      return loginRedirect(request, '/admin/login');
    }
    return NextResponse.next();
  }

  if (pathname.startsWith('/dashboard')) {
    if (!request.cookies.get(USER_COOKIE)) {
      return loginRedirect(request, '/auth/login');
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/admin/:path*'],
};
