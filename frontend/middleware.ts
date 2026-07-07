import { NextResponse, type NextRequest } from "next/server";

// Middleware minimalista: só verifica a PRESENÇA do cookie de sessão do
// Supabase (sem validar assinatura/expiração do JWT) — evita depender de
// @supabase/ssr no Edge Runtime, que causava MIDDLEWARE_INVOCATION_FAILED
// no Vercel. A validação de verdade continua no client (Supabase Auth) e
// no backend (verify_token); isto aqui é só o guard de redirecionamento
// entre /login e o resto do app.
//
// @supabase/ssr costuma fatiar o cookie de sessão em várias partes
// (sb-<ref>-auth-token.0, .1, ...) quando o valor é grande — por isso
// startsWith no prefixo, não igualdade exata do nome.

const SESSION_COOKIE_PATTERN = /^sb-.*-auth-token/;

function hasSupabaseSession(request: NextRequest): boolean {
  return request.cookies.getAll().some((cookie) => SESSION_COOKIE_PATTERN.test(cookie.name));
}

export function middleware(request: NextRequest) {
  const isLoginRoute = request.nextUrl.pathname === "/login";
  const hasSession = hasSupabaseSession(request);

  if (!hasSession && !isLoginRoute) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (hasSession && isLoginRoute) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|favicon.png|logo|public/).*)"],
};
