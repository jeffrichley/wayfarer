import { Diff, type FileDiff, type Line } from "./Diff";
import { layout, Section, Specimen } from "./gallery/Section";

// A file the change adds whole: every line new, numbered from 1.
function added(code: string[]): Line[] {
  return code.map((line, i) => ({ old: null, new: i + 1, code: line }));
}

// PR #141 as the review desk draws it (prototype/review-desk.html's FILES).
const LIMITS: FileDiff = {
  path: "worker/analysis/limits.ts",
  lines: [
    { old: 3, new: 3, code: "export const ACX_LIMITS = {" },
    { old: 4, new: 4, code: "  rms: { min: -23, max: -18 }," },
    { old: null, new: 5, code: "  peak: { max: -3 }," },
    { old: 5, new: 6, code: "} as const;" },
  ],
};
const PEAK: FileDiff = {
  path: "worker/analysis/checks/peak.ts",
  lines: added([
    "import { ACX_LIMITS } from '../limits';",
    "import { explain } from '../explain';",
    "import type { ChapterAnalysis, CheckResult } from '../types';",
    "",
    "export function checkPeak(chapter: ChapterAnalysis): CheckResult {",
    "  const { peakDb, peakAt } = chapter;",
    "  const limit = ACX_LIMITS.peak.max;",
    "",
    "  if (peakDb <= limit) {",
    "    return { check: 'peak', status: 'pass', measured: peakDb, limit };",
    "  }",
    "",
    "  return {",
    "    check: 'peak',",
    "    status: 'fail',",
    "    measured: peakDb,",
    "    limit,",
    "    at: peakAt,",
    "    reason: explain.peak({ measured: peakDb, limit, at: peakAt }),",
    "  };",
    "}",
  ]),
};
const PEAK_TEST: FileDiff = {
  path: "worker/analysis/checks/peak.test.ts",
  lines: added([
    "import { describe, expect, it } from 'vitest';",
    "import { analyseFixture } from '../../test/fixtures';",
    "import { checkPeak } from './peak';",
    "",
    "describe('checkPeak', () => {",
    "  it('passes the clean fixture', async () => {",
    "    const result = checkPeak(await analyseFixture('clean'));",
    "    expect(result.status).toBe('pass');",
    "  });",
    "",
    "  it('flags the clipped fixture above -3 dB', async () => {",
    "    const result = checkPeak(await analyseFixture('clipped'));",
    "    expect(result.status).toBe('fail');",
    "    expect(result.measured).toBeGreaterThan(-3);",
    "  });",
    "",
    "  it('reports when the loudest peak happens', async () => {",
    "    const result = checkPeak(await analyseFixture('clipped'));",
    "    expect(result.at).toBeDefined();",
    "  });",
    "});",
  ]).map((line) =>
    line.new === 19
      ? {
          ...line,
          finding: {
            by: "/code-review · Spec axis",
            body: (
              <>
                Only checks that <code>at</code> exists. Assert the clipped fixture’s known peak time so
                story 4 is actually proven.
              </>
            ),
          },
        }
      : line,
  ),
};
const CHECK_LABEL: FileDiff = {
  path: "app/compliance/check-label.ts",
  lines: [
    { old: 1, new: null, code: "export type CheckName = 'loudness';" },
    { old: null, new: 1, code: "export type CheckName = 'loudness' | 'peak';" },
    { old: 2, new: 2, code: "" },
    { old: 3, new: 3, code: "export const CHECK_LABELS: Record<CheckName, string> = {" },
    { old: 4, new: 4, code: "  loudness: 'Loudness'," },
    { old: null, new: 5, code: "  peak: 'Peaks'," },
    { old: 5, new: 6, code: "};" },
  ],
};
// A line longer than its column, so it can be seen to wrap.
const EXPLAIN: FileDiff = {
  path: "worker/analysis/explain.ts",
  lines: [
    { old: 11, new: 11, code: "export const explain = {" },
    {
      old: 12,
      new: null,
      code: "  peak: ({ measured, limit }: Failure) => `Peaks reach ${measured} dB, above the ${limit} dB ACX allows.`,",
    },
    {
      old: null,
      new: 12,
      code: "  peak: ({ measured, limit, at }: Failure) => `Peaks reach ${measured} dB at ${timestamp(at)}, above the ${limit} dB ceiling ACX allows for any chapter.`,",
    },
    { old: 13, new: 13, code: "};" },
  ],
};

export default function DiffGallery() {
  return (
    <Section title="Diff">
      <div className={layout.row}>
        <Specimen name="diff">
          <div style={{ width: 720 }}>
            <Diff files={[LIMITS, PEAK, PEAK_TEST, CHECK_LABEL]} />
          </div>
        </Specimen>
        <Specimen name="diff-changed">
          <div style={{ width: 720 }}>
            <Diff files={[CHECK_LABEL, LIMITS]} />
          </div>
        </Specimen>
        <Specimen name="diff-long-line">
          <div style={{ width: 420 }}>
            <Diff files={[EXPLAIN]} />
          </div>
        </Specimen>
      </div>
    </Section>
  );
}
