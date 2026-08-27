import {
  formatBriefEditionTitle,
  formatEditionDate,
  formatEssentialStoryCount,
  getBriefEditionIdentity,
  getGreeting,
  isCurrentEdition,
} from "@/utils/edition";

describe("getGreeting", () => {
  it("always says Subah bakhair", () => {
    // This is a morning brief: produced once, early. The greeting names the
    // edition, not the hour the page was opened. An earlier version varied it
    // by the Karachi clock and greeted a reader "Assalam-o-alaikum" over the
    // same morning's brief at 2pm.
    expect(getGreeting().greeting).toBe("Subah bakhair");
    expect(getGreeting().translation).toBe("Good morning");
  });
});

describe("edition identity", () => {
  afterEach(() => jest.useRealTimers());

  it("calls today's brief today's", () => {
    const now = new Date("2026-08-25T08:00:00Z");
    expect(isCurrentEdition("2026-08-25T05:00:00Z", true, now)).toBe(true);
    expect(formatBriefEditionTitle("2026-08-25T05:00:00Z", true, now)).toMatch(/^Today's Brief ·/);
  });

  it("stops claiming 'today' once the brief is a day old", () => {
    const now = new Date("2026-08-26T08:00:00Z");
    expect(isCurrentEdition("2026-08-25T05:00:00Z", true, now)).toBe(false);
    expect(formatBriefEditionTitle("2026-08-25T05:00:00Z", true, now)).toMatch(/^Morning Brief ·/);
  });

  it("honours an explicit isFresh=false even on the same day", () => {
    const now = new Date("2026-08-25T23:00:00Z");
    expect(isCurrentEdition("2026-08-25T05:00:00Z", false, now)).toBe(false);
  });

  it("treats a missing timestamp as the current edition rather than as stale", () => {
    expect(isCurrentEdition(undefined, undefined, new Date("2026-08-25T08:00:00Z"))).toBe(true);
    expect(isCurrentEdition("garbage", undefined, new Date("2026-08-25T08:00:00Z"))).toBe(true);
  });

  it("crosses the day boundary in Karachi, not UTC", () => {
    // 20:00 UTC on the 24th is already 01:00 on the 25th in Karachi.
    expect(isCurrentEdition("2026-08-24T20:00:00Z", true, new Date("2026-08-24T21:00:00Z"))).toBe(
      true,
    );
  });

  it("switches every label together when the brief is stale", () => {
    const identity = getBriefEditionIdentity(
      "2026-08-24T05:00:00Z",
      false,
      new Date("2026-08-26T08:00:00Z"),
    );
    expect(identity.isCurrentEdition).toBe(false);
    expect(identity.briefLabel).toBe("Latest brief");
    expect(identity.editionLabel).toBe("Latest edition");
    expect(identity.backLinkLabel).toBe("Latest Brief");
    expect(identity.rankingNote).toMatch(/Last available brief/);
  });

  it("formats the edition date in Karachi", () => {
    expect(formatEditionDate("2026-08-24T20:00:00Z")).toMatch(/25 Aug/);
  });

  it("says 'story' for one and 'stories' for the rest", () => {
    expect(formatEssentialStoryCount(1)).toBe("1 essential story");
    expect(formatEssentialStoryCount(0)).toBe("0 essential stories");
    expect(formatEssentialStoryCount(12)).toBe("12 essential stories");
  });
});
