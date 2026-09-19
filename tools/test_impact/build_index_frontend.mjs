#!/usr/bin/env node
// 프론트엔드 test impact 인덱스 생성기.
// frontend/src/**/*.{ts,tsx} 의 import 문을 정규식으로 분석해
// __tests__/**/*.{test,spec}.{ts,tsx} 의 의존성 그래프를 만든다.
// _workspace/test_index.yaml 의 frontend: 섹션을 갱신한다 (backend 섹션은 보존).

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join, relative, resolve, dirname, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import yaml from "js-yaml";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = resolve(__dirname, "..", "..");
const FRONT_SRC = join(ROOT, "frontend", "src");
const INDEX_PATH = join(ROOT, "_workspace", "test_index.yaml");

// 🔴 `[\s\S]` 로 **개행을 넘는다**. `.` 는 개행에 안 걸려서 여러 줄로 쓴 import 를
// 통째로 놓쳤다(2026-09-19 실측: 39파일 46건). 놓친 의존은 인덱스에서 사라지고,
// 그러면 그 모듈만 고치는 PR 에서 `affected.py --target=frontend` 가 빈 목록을 돌려줘
// 회귀 테스트가 **조용히 건너뛰어진다** — 붉어지는 것보다 나쁘다.
// 가드 = `tests/unit/deploy/test_cycle316_frontend_impact_index.py`.
const IMPORT_RE = /^\s*import\s+(?:[\s\S]+?\s+from\s+)?["']([^"']+)["']/gm;

function listFiles(dir, predicate) {
  // tracked + untracked(--exclude-standard로 .gitignore 제외) 모두 포함.
  // 새 테스트 파일이 아직 커밋되지 않았어도 인덱스에 반영된다.
  const tracked = execSync(`git ls-files "${dir}"`, { cwd: ROOT, encoding: "utf-8" })
    .split("\n")
    .filter(Boolean);
  const untracked = execSync(
    `git ls-files --others --exclude-standard "${dir}"`,
    { cwd: ROOT, encoding: "utf-8" },
  )
    .split("\n")
    .filter(Boolean);
  const all = [...new Set([...tracked, ...untracked])].map((p) => join(ROOT, p));
  return all.filter(predicate);
}

function isSourceFile(p) {
  return /\.(ts|tsx)$/.test(p) && !/__tests__/.test(p) && !/\.test\.|\.spec\./.test(p);
}
function isTestFile(p) {
  return /\.(test|spec)\.(ts|tsx)$/.test(p) || /__tests__\//.test(p);
}

function parseImports(file) {
  // git ls-files 는 staged 안 된 삭제 파일도 포함할 수 있음 → 안전망
  if (!existsSync(file)) return [];
  const text = readFileSync(file, "utf-8");
  const out = [];
  let m;
  IMPORT_RE.lastIndex = 0;
  while ((m = IMPORT_RE.exec(text))) {
    out.push(m[1]);
  }
  return out;
}

function resolveImport(fromFile, spec) {
  // 상대 경로만 처리. node_modules / 절대 alias는 무시
  if (!spec.startsWith(".")) return null;
  const base = resolve(dirname(fromFile), spec);
  for (const ext of [".ts", ".tsx", "/index.ts", "/index.tsx"]) {
    const cand = base.endsWith(".ts") || base.endsWith(".tsx") ? base : base + ext;
    if (existsSync(cand)) return cand;
  }
  return null;
}

function main() {
  const allFiles = listFiles("frontend/src", () => true);
  const srcFiles = allFiles.filter(isSourceFile);
  const testFiles = allFiles.filter(isTestFile);

  const srcImports = new Map();
  for (const f of srcFiles) {
    srcImports.set(
      f,
      parseImports(f)
        .map((s) => resolveImport(f, s))
        .filter(Boolean)
    );
  }
  const testImports = new Map();
  for (const f of testFiles) {
    testImports.set(
      f,
      parseImports(f)
        .map((s) => resolveImport(f, s))
        .filter(Boolean)
    );
  }

  // direct
  const direct = new Map();
  for (const s of srcFiles) direct.set(s, new Set());
  for (const [t, deps] of testImports) {
    for (const d of deps) {
      if (direct.has(d)) direct.get(d).add(t);
    }
  }

  // reverse src graph
  const reverseSrc = new Map();
  for (const s of srcFiles) reverseSrc.set(s, new Set());
  for (const [s, deps] of srcImports) {
    for (const d of deps) {
      if (reverseSrc.has(d)) reverseSrc.get(d).add(s);
    }
  }

  // transitive via BFS
  const transitive = new Map();
  for (const s of srcFiles) {
    const seen = new Set();
    const queue = [s];
    const tests = new Set();
    while (queue.length) {
      const cur = queue.shift();
      if (seen.has(cur)) continue;
      seen.add(cur);
      for (const p of reverseSrc.get(cur) || []) {
        if (!seen.has(p)) queue.push(p);
      }
      for (const t of direct.get(cur) || []) tests.add(t);
    }
    // direct 차감
    for (const t of direct.get(s) || []) tests.delete(t);
    transitive.set(s, tests);
  }

  const frontend = {};
  const unmapped = [];
  for (const s of srcFiles.sort()) {
    const rel = relative(ROOT, s);
    const d = [...direct.get(s)].map((p) => relative(ROOT, p)).sort();
    const t = [...transitive.get(s)].map((p) => relative(ROOT, p)).sort();
    if (!d.length && !t.length) unmapped.push(rel);
    frontend[rel] = { direct_tests: d, transitive_tests: t };
  }

  // backend 섹션 보존
  let existing = {};
  if (existsSync(INDEX_PATH)) {
    existing = yaml.load(readFileSync(INDEX_PATH, "utf-8")) || {};
  }

  // 🔴 미매핑 목록은 **양쪽이 나눠 쓴다** — 우리는 `frontend/` 밑만 책임지고 나머지는 보존한다.
  // 단순 이어붙이기는 이 도구를 두 번 돌리면 우리 항목이 **중복 누적**된다(정렬이 그것을 숨긴다).
  const priorUnmapped = existing?.stats?.unmapped_modules || [];
  const mergedUnmapped = [
    ...new Set([
      ...priorUnmapped.filter((m) => !m.startsWith("frontend/")),
      ...unmapped,
    ]),
  ].sort();

  const payload = {
    version: 1,
    generated_at: new Date().toISOString(),
    backend: existing.backend || {},
    frontend,
    stats: {
      backend_modules: Object.keys(existing.backend || {}).length,
      backend_tests: existing?.stats?.backend_tests ?? 0,
      frontend_modules: srcFiles.length,
      frontend_tests: testFiles.length,
      unmapped_modules: mergedUnmapped,
    },
  };

  if (!existsSync(dirname(INDEX_PATH))) mkdirSync(dirname(INDEX_PATH), { recursive: true });
  writeFileSync(INDEX_PATH, yaml.dump(payload, { sortKeys: true }), "utf-8");
  console.log(`[build_index_frontend] wrote ${relative(ROOT, INDEX_PATH)}`);
  console.log(`  frontend modules: ${srcFiles.length}`);
  console.log(`  frontend tests:   ${testFiles.length}`);
  console.log(`  unmapped:         ${unmapped.length}`);
}

main();
