import { afterEach, describe, expect, it, vi } from "vitest";

import { isOidcEnabled, keycloakFetch, rewriteKeycloakUrl } from "./oidc";

const PUBLIC = "http://localhost:8080/realms/shield";
const INTERNAL = "http://keycloak:8080/realms/shield";

describe("isOidcEnabled", () => {
  const original = process.env.SHIELD_AUTH_OIDC_ENABLED;
  afterEach(() => {
    process.env.SHIELD_AUTH_OIDC_ENABLED = original;
  });

  it.each([
    ["true", true],
    ["false", false],
    ["TRUE", false], // exact match only — no case-folding
    ["1", false],
    ["", false],
    [undefined, false],
  ])("SHIELD_AUTH_OIDC_ENABLED=%o -> %s", (value, expected) => {
    if (value === undefined) {
      delete process.env.SHIELD_AUTH_OIDC_ENABLED;
    } else {
      process.env.SHIELD_AUTH_OIDC_ENABLED = value;
    }
    expect(isOidcEnabled()).toBe(expected);
  });
});

describe("rewriteKeycloakUrl", () => {
  it("rewrites the discovery URL from the public origin to the internal origin", () => {
    expect(
      rewriteKeycloakUrl(
        `${PUBLIC}/.well-known/openid-configuration`,
        PUBLIC,
        INTERNAL,
      ),
    ).toBe(`${INTERNAL}/.well-known/openid-configuration`);
  });

  it("preserves path and query while swapping only the origin", () => {
    expect(
      rewriteKeycloakUrl(
        "http://localhost:8080/realms/shield/protocol/openid-connect/token?x=1",
        PUBLIC,
        INTERNAL,
      ),
    ).toBe(
      "http://keycloak:8080/realms/shield/protocol/openid-connect/token?x=1",
    );
  });

  it("passes through a URL already on the internal origin (backchannel-dynamic token/JWKS)", () => {
    const internalToken = `${INTERNAL}/protocol/openid-connect/token`;
    expect(rewriteKeycloakUrl(internalToken, PUBLIC, INTERNAL)).toBe(
      internalToken,
    );
  });

  it("passes through an unrelated host untouched", () => {
    const other = "https://example.gov/whatever";
    expect(rewriteKeycloakUrl(other, PUBLIC, INTERNAL)).toBe(other);
  });

  it("passes through when either issuer env is blank (no rewrite)", () => {
    const url = `${PUBLIC}/.well-known/openid-configuration`;
    expect(rewriteKeycloakUrl(url, "", INTERNAL)).toBe(url);
    expect(rewriteKeycloakUrl(url, PUBLIC, "")).toBe(url);
  });
});

describe("keycloakFetch", () => {
  const pub = process.env.KEYCLOAK_ISSUER;
  const int = process.env.KEYCLOAK_INTERNAL_ISSUER;
  afterEach(() => {
    process.env.KEYCLOAK_ISSUER = pub;
    process.env.KEYCLOAK_INTERNAL_ISSUER = int;
    vi.restoreAllMocks();
  });

  it("fetches the rewritten internal URL for a string discovery input", async () => {
    process.env.KEYCLOAK_ISSUER = PUBLIC;
    process.env.KEYCLOAK_INTERNAL_ISSUER = INTERNAL;
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));

    await keycloakFetch(`${PUBLIC}/.well-known/openid-configuration`);

    expect(fetchMock).toHaveBeenCalledWith(
      `${INTERNAL}/.well-known/openid-configuration`,
      undefined,
    );
  });

  it("rewrites the URL of a Request input while preserving it as a Request", async () => {
    process.env.KEYCLOAK_ISSUER = PUBLIC;
    process.env.KEYCLOAK_INTERNAL_ISSUER = INTERNAL;
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));

    await keycloakFetch(
      new Request(`${PUBLIC}/.well-known/openid-configuration`),
    );

    const firstArg = fetchMock.mock.calls[0][0] as Request;
    expect(firstArg).toBeInstanceOf(Request);
    expect(firstArg.url).toBe(`${INTERNAL}/.well-known/openid-configuration`);
  });
});
