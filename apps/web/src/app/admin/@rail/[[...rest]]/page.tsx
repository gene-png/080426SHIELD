/**
 * #1385: every admin URL matches the `@rail` slot, so a soft navigation from a
 * client's page to any other page REPLACES the slot with nothing. A slot with
 * no match keeps what it last rendered on a soft navigation, and the previous
 * client's rail would stay beside an unrelated page. The client routes next to
 * this file are more specific and win.
 */
export default function NoRail(): null {
  return null;
}
