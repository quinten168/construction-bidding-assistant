// Registers the .tsx loader for `node --test`. Kept separate because module.register() must run
// before the test file is imported.
import { register } from "node:module";
register("./2026-08-10-tsx-loader.mjs", import.meta.url);
