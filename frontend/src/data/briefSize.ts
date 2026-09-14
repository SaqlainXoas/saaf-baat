/**
 * How many cards a brief holds.
 *
 * One constant, because the number was previously written out in three places
 * that could disagree: the homepage slice, the API request limit, and the
 * backend's SAAF_EDITORIAL_MAX_STORIES. They did disagree — the request limit
 * was left at 9 while the brief moved, and because the backend applies
 * the limit before sorting by editorial priority, the highest-priority card of
 * the day was silently cut.
 *
 * Keep in step with SAAF_EDITORIAL_MAX_STORIES in backend/.env.example.
 */
export const MAX_STORIES = 12;

/**
 * Ask for more rows than the brief shows.
 *
 * The backend applies `limit` at the database level and only then sorts by
 * editorial priority, so requesting exactly MAX_STORIES risks dropping a
 * high-priority card before it is ever ranked.
 */
export const FEED_REQUEST_LIMIT = 30;

/**
 * The floor the editor aims for, recorded on the frontend side of the contract.
 *
 * The reader is no longer told when an edition falls below it. A short brief is
 * the product working - it ends rather than padding - and the banner that
 * announced it apologised for that in the amber box reserved for real faults.
 * The masthead states the story count regardless.
 *
 * Keep in step with TARGET_STORY_FLOOR in backend/src/agents/editorial.py.
 */
export const MIN_STORIES = 6;
