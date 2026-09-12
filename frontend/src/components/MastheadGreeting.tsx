import { GREETING_BANDS } from "@/utils/edition";

/**
 * The word the brief opens with, shared by both mastheads.
 *
 * All three time bands are in the DOM on every render and CSS shows the one
 * that matches `data-pkt-band` on <html>, which a blocking inline script sets
 * from the Karachi clock before first paint (see PKT_BAND_SCRIPT). The page is
 * served from Vercel's cache, so the band cannot be decided at render time -
 * and deciding it after mount would flash the wrong greeting in 34-54px
 * display type. Rendering all three costs two hidden spans and means the
 * server and the client emit byte-identical markup.
 *
 * The hidden bands are `display: none`, so a screen reader announces exactly
 * one greeting. The English gloss sits on each span rather than on the h1
 * because only one of the three can be the right tooltip at a time, and CSS
 * cannot swap an attribute.
 *
 * Deliberately not a client component: BrandHeader is a server component and
 * MorningGreeting is a client one, and this renders inside both.
 */
export default function MastheadGreeting({ className }: { className: string }) {
  return (
    <h1 className={className} lang="ur-Latn">
      {GREETING_BANDS.map(({ band, greeting, translation }) => (
        <span key={band} data-band={band} title={translation}>
          {greeting}
        </span>
      ))}
    </h1>
  );
}
