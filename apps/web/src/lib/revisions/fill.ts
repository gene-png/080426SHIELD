/**
 * Fill `{name}` placeholders in an approved copy template. Every placeholder in
 * the template must be given: a missing one throws rather than printing a
 * literal "{v}" to a consultant.
 */
export function fill(
  template: string,
  values: Record<string, string | number>,
): string {
  return template.replace(/\{([^{}]+)\}/g, (_m, key: string) => {
    if (!(key in values)) {
      throw new Error(`copy placeholder {${key}} was not given`);
    }
    return String(values[key]);
  });
}
