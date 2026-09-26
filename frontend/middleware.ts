import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Fast-path route guards based on session cookie presence.
// Deep authentication is always verified via API (ProtectedRoute / server data).
// Cookie names are configurable via NEXT_PUBLIC_*_SESSION_COOKIE.

const USER_COOKIE = process.env.NEXT_PUBLIC_USER_SESSION_COOKIE || 'nourai_user_session';
const ADMIN_COOKIE = process.env.NEXT_PUBLIC_ADMIN_SESSION_COOKIE || 'nourai_admin_session';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith('/admin')) {
    if (pathname === '/admin/login') return NextResponse.next();
    if (!request.cookies.get(ADMIN_COOKIE)) {
      return NextResponse.redirect(new URL('/admin/login', request.url));
    }
    return NextResponse.next();
  }

  if (pathname.startsWith('/dashboard')) {
    if (!request.cookies.get(USER_COOKIE)) {
      return NextResponse.redirect(new URL('/auth/login', request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/admin/:path*'],
};
