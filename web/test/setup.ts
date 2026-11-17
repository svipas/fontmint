// Preloaded by `bun test` (bunfig.toml): a DOM for component tests, cleaned up after each.
import { afterEach } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

const { cleanup } = await import("@testing-library/react");
afterEach(cleanup);
