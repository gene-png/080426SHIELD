import { captureContainerIds } from "./helpers/containerIdentity";

export default function globalSetup(): void {
  captureContainerIds();
}
