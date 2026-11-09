#!/usr/bin/env node
// Commit-message guard: the repository owner is the sole author.
// Rejects any message that carries AI attribution (co-author trailers,
// session links, "Generated with ..." lines).
//
// Usage (by git):  node .githooks/check-commit-msg.mjs <path-to-message-file>
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const FORBIDDEN = [
  { re: /^\s*co-authored-by\s*:/i, why: 'Co-authored-by trailer' },
  { re: /^\s*claude-session\s*:/i, why: 'Claude-Session trailer' },
  { re: /noreply@anthropic\.com/i, why: 'Anthropic noreply address' },
  { re: /generated with \[?claude code\]?/i, why: '"Generated with Claude Code" line' },
  { re: /claude\.ai\/code\/session/i, why: 'Claude session link' },
];

/** Returns a list of human-readable violations; empty when the message is clean. */
export function findViolations(message) {
  const violations = [];
  message.split(/\r?\n/).forEach((line, index) => {
    if (line.startsWith('#')) return; // git strips comment lines
    for (const { re, why } of FORBIDDEN) {
      if (re.test(line)) violations.push(`line ${index + 1}: ${why}`);
    }
  });
  return violations;
}

const isDirectRun =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  const file = process.argv[2];
  if (!file) {
    console.error('check-commit-msg: missing commit message file path');
    process.exit(2);
  }
  const violations = findViolations(readFileSync(file, 'utf8'));
  if (violations.length > 0) {
    console.error('Commit rejected: this repository has a single human author.');
    for (const v of violations) console.error(`  - ${v}`);
    console.error('Remove these lines and commit again.');
    process.exit(1);
  }
}
