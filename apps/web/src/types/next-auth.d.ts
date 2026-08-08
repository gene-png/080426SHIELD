// Auth.js v5 module augmentation. Declaration merging adds our custom claims
// onto the base `Session`/`User` (from @auth/core/types, re-exported by
// next-auth) and `JWT` (next-auth/jwt) interfaces — no `extends` needed, and
// v5 no longer exports `DefaultUser`.

declare module "next-auth" {
  interface Session {
    role?: "admin" | "client";
    accessToken?: string;
    error?: string;
    /**
     * When this session can no longer be renewed — the refresh token's expiry.
     * Past it no rotation can help and the user WILL be signed out, so it is the
     * only honest thing to count down to in the UI.
     */
    sessionExpiresAt?: string;
  }
  interface User {
    role?: "admin" | "client";
    accessToken?: string;
    refreshToken?: string;
    accessExpiresAt?: string;
    refreshExpiresAt?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: "admin" | "client";
    accessToken?: string;
    refreshToken?: string;
    accessExpiresAt?: string;
    refreshExpiresAt?: string;
    error?: string;
  }
}

export {};
