// Minimal Node ESM loader so a component test can import the real .tsx sources without adding a
// test framework to this app (there is none — package.json has no vitest/jest, and installing one
// the week of the presentation is not a change worth making for two assertions).
//
// It does two things: resolve the "@/..." alias the way tsconfig does, and transpile .ts/.tsx with
// the TypeScript compiler that is already a devDependency. Everything else is plain Node ESM.
import { readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import ts from "typescript";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src");
const EXTS = ["", ".tsx", ".ts", "/index.tsx", "/index.ts"];

async function probe(base) {
  for (const ext of EXTS) {
    try {
      await readFile(base + ext);
      return pathToFileURL(base + ext).href;
    } catch { /* try the next extension */ }
  }
  return null;
}

export async function resolve(specifier, context, next) {
  // "@/..." — the tsconfig path alias.
  if (specifier.startsWith("@/")) {
    const url = await probe(path.join(SRC, specifier.slice(2)));
    if (url) return { url, shortCircuit: true };
  }
  // "./x" / "../x" from a TS file — TS source omits the extension, Node ESM requires it.
  if (specifier.startsWith(".") && context.parentURL?.startsWith("file:") &&
      /\.tsx?$/.test(context.parentURL)) {
    const url = await probe(path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier));
    if (url) return { url, shortCircuit: true };
  }
  return next(specifier, context);
}

export async function load(url, context, next) {
  if (/\.tsx?($|\?)/.test(url)) {
    const source = await readFile(fileURLToPath(url), "utf8");
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
        jsx: ts.JsxEmit.ReactJSX,
      },
      fileName: fileURLToPath(url),
    });
    return { format: "module", source: outputText, shortCircuit: true };
  }
  return next(url, context);
}
