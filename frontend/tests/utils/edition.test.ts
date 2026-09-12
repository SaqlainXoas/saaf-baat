import {
  formatBriefEditionTitle,
  formatEditionDate,
  formatEssentialStoryCount,
  getBriefEditionIdentity,
  getGreeting,
  getGreetingBand,
  isCurrentEdition,
  isMorningEditionFresh,
  PKT_BAND_SCRIPT,
} from "@/utils/edition";

// PKT is UTC+5 with no DST, so a Karachi wall time is the UTC instant five
// hours earlier. Every boundary of every band, expressed both ways.
const BOUNDARIES = [
  { pkt: "04:59", utc: "2026-09-11T23:59:00Z", hour: 4, band: "evening" },
  { pkt: "05:00", utc: "2026-09-12T00:00:00Z", hour: 5, band: "morning" },
  { pkt: "11:59", utc: "2026-09-12T06:59:00Z", hour: 11, band: "morning" },
  { pkt: "12:00", utc: "2026-09-12T07:00:00Z", hour: 12, band: "midday" },
  { pkt: "16:59", utc: "2026-09-12T11:59:00Z", hour: 16, band: "midday" },
  { pkt: "17:00", utc: "2026-09-12T12:00:00Z", hour: 17, band: "evening" },
  { pkt: "23:59", utc: "2026-09-12T18:59:00Z", hour: 23, band: "evening" },
] as const;

describe("greeting bands", () => {
  afterEach(() => jest.useRealTimers());

  it.each(BOUNDARIES)("puts $pkt PKT in the $band band", ({ utc, band }) => {
    expect(getGreetingBand(new Date(utc))).toBe(band);
  });

  it.each(BOUNDARIES)("takes $pkt as a bare hour too", ({ hour, band }) => {
    // The hour overload is what makes the bands testable with no clock at all.
    expect(getGreetingBand(hour)).toBe(band);
  });

  it("reads the Karachi clock, not the reader's", () => {
    // 01:00 UTC is 2am for a reader in London and 06:00 in Karachi. They see
    // what Pakistan sees. This holds whatever TZ the test runner is in,
    // because the hour is formatted through Asia/Karachi rather than derived
    // from a local Date or a hardcoded +5 offset.
    expect(getGreetingBand(new Date("2026-09-12T01:00:00Z"))).toBe("morning");
    // And the reverse: 21:00 UTC is late evening in London, 02:00 in Karachi.
    expect(getGreetingBand(new Date("2026-09-12T21:00:00Z"))).toBe("evening");
  });

  it("keeps the { greeting, translation } shape for every band", () => {
    expect(getGreeting(8)).toEqual({ greeting: "Subah Bakhair", translation: "Good morning" });
    expect(getGreeting(20)).toEqual({ greeting: "Shaam Bakhair", translation: "Good evening" });
  });

  it("labels the afternoon rather than greeting it", () => {
    // "Aaj Ki Baat" is not a greeting, and that is the point. An earlier
    // hour-varying version greeted the same morning edition
    // "Assalam-o-alaikum" at 2pm, re-badging a morning brief as an afternoon
    // product. The midday band names the masthead instead.
    expect(getGreeting(14)).toEqual({ greeting: "Aaj Ki Baat", translation: "Today's word" });
  });

  it("defaults to the current Karachi hour when given nothing", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-09-12T07:30:00Z")); // 12:30 PKT
    expect(getGreeting().greeting).toBe("Aaj Ki Baat");
  });
});

describe("PKT_BAND_SCRIPT", () => {
  afterEach(() => {
    jest.useRealTimers();
    delete document.documentElement.dataset.pktBand;
  });

  // The script duplicates the band boundaries as a string because it has to
  // run before React and before first paint. This is what holds the two
  // copies together: if a boundary moves in one and not the other, it fails.
  it.each(Array.from({ length: 24 }, (_, hour) => hour))(
    "agrees with getGreetingBand at %i:00 PKT",
    (hour) => {
      const utcHour = (hour - 5 + 24) % 24;
      const day = hour < 5 ? "13" : "12";
      jest.useFakeTimers().setSystemTime(
        new Date(`2026-09-${day}T${String(utcHour).padStart(2, "0")}:00:00Z`),
      );

      eval(PKT_BAND_SCRIPT);

      expect(document.documentElement.dataset.pktBand).toBe(getGreetingBand(hour));
    },
  );

  it("leaves the attribute unset when Intl throws, so CSS falls back to morning", () => {
    const original = Intl.DateTimeFormat;
    // @ts-expect-error - deliberately breaking Intl for this one assertion
    Intl.DateTimeFormat = () => {
      throw new Error("no ICU data");
    };
    try {
      eval(PKT_BAND_SCRIPT);
      expect(document.documentElement.dataset.pktBand).toBeUndefined();
    } finally {
      Intl.DateTimeFormat = original;
    }
  });
});

describe("edition identity", () => {
  afterEach(() => jest.useRealTimers());

  it("calls today's brief today's", () => {
    const now = new Date("2026-08-25T08:00:00Z");
    expect(isCurrentEdition("2026-08-25T05:00:00Z", true, now)).toBe(true);
    expect(formatBriefEditionTitle("2026-08-25T05:00:00Z", true, now)).toMatch(/^Today's Brief ·/);
  });

  it("does not call an overnight pre-edition run fresh", () => {
    const now = new Date("2026-08-28T05:00:00Z"); // 10:00 PKT
    expect(isMorningEditionFresh("2026-08-27T19:25:00Z", now)).toBe(false);
    expect(isMorningEditionFresh("2026-08-28T02:05:00Z", now)).toBe(true);
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
