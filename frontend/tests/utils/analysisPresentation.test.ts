import {
  publishersNamedInAnalysis,
  splitSentences,
  toAnalysisParagraphs,
} from "@/utils/analysisPresentation";

describe("publishersNamedInAnalysis", () => {
  it("finds a publisher the analysis actually quotes", () => {
    expect(
      publishersNamedInAnalysis("Brecorder reports that the figure rose sharply."),
    ).toEqual(["brecorder"]);
    expect(
      publishersNamedInAnalysis("The Nation reports that PIMS received Rs22bn."),
    ).toEqual(["nation"]);
    expect(
      publishersNamedInAnalysis("According to Dawn, the ward had been closed."),
    ).toEqual(["dawn"]);
  });

  it("does not mistake ordinary prose for an attribution", () => {
    // The same false positives that used to discard a whole analysis in the
    // backend validator would have promoted the wrong source row here.
    expect(
      publishersNamedInAnalysis("The government launched an e-pension app for retirees."),
    ).toEqual([]);
    expect(publishersNamedInAnalysis("Protests spread across the nation.")).toEqual([]);
    expect(publishersNamedInAnalysis("Police raided the compound at dawn.")).toEqual([]);
  });

  it("returns nothing for a missing analysis", () => {
    expect(publishersNamedInAnalysis(null)).toEqual([]);
    expect(publishersNamedInAnalysis("")).toEqual([]);
  });
});

describe("toAnalysisParagraphs", () => {
  it("leaves a short analysis as one paragraph", () => {
    expect(toAnalysisParagraphs("One sentence. Two sentences.")).toEqual([
      "One sentence. Two sentences.",
    ]);
  });

  it("breaks a long analysis into readable paragraphs", () => {
    const sentence = "Fourteen newborns died in the PIMS nursery fire overnight. ";
    const paragraphs = toAnalysisParagraphs(sentence.repeat(7));

    expect(paragraphs.length).toBeGreaterThan(1);
    expect(paragraphs.join(" ").replace(/\s+/g, " ").trim()).toBe(
      sentence.repeat(7).replace(/\s+/g, " ").trim(),
    );
  });

  it("splits four sentences into two balanced paragraphs", () => {
    // Grouping in threes left a one-sentence tail, and the guard against that
    // merged it back, so a four-sentence analysis rendered as one paragraph.
    const paragraphs = toAnalysisParagraphs(
      "A long opening sentence that carries the main development of the day. " +
        "A second supporting sentence with more of the detail. " +
        "A third sentence closing the first group out. " +
        "Short tail.",
    );

    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[1]).toContain("Short tail.");
  });

  it("does not break a paragraph on an abbreviation", () => {
    const paragraphs = toAnalysisParagraphs(
      "The Supreme Court met on Sept. 16 to hear the plea in Islamabad. " +
        "Dr. Uzma Khan filed the second application on Thursday. " +
        "The bench reserved its ruling after a long hearing. " +
        "Lawyers for the state opposed the request before the court rose.",
    );

    // "Dr." must not be stranded at the end of the previous paragraph.
    expect(paragraphs.every((p) => !p.trimEnd().endsWith("Dr."))).toBe(true);
    expect(paragraphs.join(" ")).toContain("Dr. Uzma Khan");
  });

  it("returns nothing for empty text", () => {
    expect(toAnalysisParagraphs("")).toEqual([]);
  });
});


describe("splitSentences", () => {
  it("treats a known abbreviation as part of the sentence", () => {
    expect(splitSentences("The court met on Sept. 16 today. Dr. Uzma Khan spoke.")).toEqual([
      "The court met on Sept. 16 today.",
      "Dr. Uzma Khan spoke.",
    ]);
  });

  it("splits ordinary sentences", () => {
    expect(splitSentences("One thing. Two things.")).toEqual(["One thing.", "Two things."]);
  });

  it("returns nothing for empty text", () => {
    expect(splitSentences("   ")).toEqual([]);
  });
});
