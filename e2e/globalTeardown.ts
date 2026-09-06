import { assertContainerIdsUnchanged } from "./helpers/containerIdentity";

export default function globalTeardown(): void {
  assertContainerIdsUnchanged();
}
