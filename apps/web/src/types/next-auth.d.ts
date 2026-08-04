// Auth.js v5 module augmentation. Declaration merging adds our custom claims
// onto the base `Session`/`User` (from @auth/core/types, re-exported by
// next-auth) and `JWT` (next-auth/jwt) interfaces — no `extends` needed, and
// v5 no longer exports `DefaultUser`.

declare module "next-auth" {
  interface Session {
    role?: "admin" | "client";
    accessToken?: string;
    error?: string;
  }
  interface User {
    role?: "admin" | "client";
    accessToken?: string;
    refreshToken?: string;
    accessExpiresAt?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: "admin" | "client";
    accessToken?: string;
    refreshToken?: string;
    accessExpiresAt?: string;
    error?: string;
  }
}

export {};
