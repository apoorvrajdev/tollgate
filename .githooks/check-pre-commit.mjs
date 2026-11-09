#!/usr/bin/env node
// Pre-commit guard: the repository owner is the sole author.
// 1. Author and committer email must equal `git config authorguard.email`.
// 2. AI assistant files (CLAUDE.md, .claude/, SKILL.md, skills/, ai-notes/)
//    may never be committed, even with `git add -f`.
//
// Usage (by git):     node .githooks/check-pre-commit.mjs
// Usage (for tests):  node .githooks/check-pre-commit.mjs --files <path> [<path> ...]
//                     (checks only the given paths, skips the identity check)
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const BLOCKED = [
  { re: /(^|\/)CLAUDE(\.local)?\.md$/i, why: 'Claude instruction file' },
  { re: /(^|\/)\.claude(\/|$)/i, why: '.claude folder' },
  { re: /(^|\/)SKILL\.md$/i, why: 'skill file' },
  { re: /(^|\/)\.?skills\//i, why: 'skills folder' },
  { re: /(^|\/)ai-notes\//i, why: 'private AI notes' },
];

/** Returns "path (reason)" for every path that must not be committed. */
export function blockedPaths(paths) {
  const hits = [];
  for (const raw of paths) {
    const p = raw.replace(/\\/g, '/');
    const rule = BLOCKED.find(({ re }) => re.test(p));
    if (rule) hits.push(`${raw} (${rule.why})`);
  }
  return hits;
}

/** Extracts the email from a git ident string: "Name <email> 1700000000 +0530". */
export function emailFromIdent(ident) {
  const match = /<([^>]*)>/.exec(ident);
  return match ? match[1].trim() : '';
}

function git(args) {
  return execFileSync('git', args, { encoding: 'utf8' }).trim();
}

function identityProblems() {
  let expected = '';
  try {
    expected = git(['config', '--get', 'authorguard.email']);
  } catch {
    return ['authorguard.email is not set. Run: git config authorguard.email "<your email>"'];
  }
  const problems = [];
  for (const variable of ['GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT']) {
    const email = emailFromIdent(git(['var', variable]));
    if (email.toLowerCase() !== expected.toLowerCase()) {
      problems.push(`${variable} email is "${email}", expected "${expected}"`);
    }
  }
  return problems;
}

function stagedPaths() {
  const out = execFileSync('git', ['diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR'], {
    encoding: 'utf8',
  });
  return out.split('\0').filter(Boolean);
}

const isDirectRun =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  const filesFlag = process.argv.indexOf('--files');
  const testMode = filesFlag !== -1;
  const paths = testMode ? process.argv.slice(filesFlag + 1) : stagedPaths();

  const identity = testMode ? [] : identityProblems();
  const blocked = blockedPaths(paths);
  if (identity.length + blocked.length > 0) {
    console.error('Commit rejected by the owner authorship guard:');
    for (const p of [...identity, ...blocked]) console.error(`  - ${p}`);
    if (blocked.length > 0) {
      console.error('Unstage AI assistant files with: git restore --staged <path>');
    }
    if (identity.length > 0) {
      console.error('Fix your identity with: git config user.email "<your email>"');
    }
    process.exit(1);
  }
}
