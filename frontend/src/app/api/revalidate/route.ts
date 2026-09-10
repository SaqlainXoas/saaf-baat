import { NextRequest, NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

// The tags fetchJson attaches in src/data/api.ts. Revalidating a tag no fetch
// carries is a silent no-op, so these two lists have to stay in step.
const REVALIDATABLE_TAGS = ["feed", "story"];

type Payload = {
  tags?: string[];
};

function getSecret() {
  const secret = process.env.REVALIDATE_SECRET?.trim();
  return secret || "";
}

export async function POST(req: NextRequest) {
  const secret = getSecret();
  if (!secret) {
    return NextResponse.json(
      { ok: false, error: "REVALIDATE_SECRET is not configured." },
      { status: 500 },
    );
  }

  const provided =
    req.headers.get("x-revalidate-secret") || "";
  if (provided !== secret) {
    return NextResponse.json({ ok: false, error: "Unauthorized." }, { status: 401 });
  }

  let tags: string[] = [...REVALIDATABLE_TAGS];
  try {
    const body = (await req.json()) as Payload;
    if (Array.isArray(body?.tags) && body.tags.length) {
      tags = body.tags.filter((tag) => REVALIDATABLE_TAGS.includes(tag));
    }
  } catch {
    // Ignore invalid/missing JSON; use defaults.
  }

  for (const tag of tags) revalidateTag(tag);
  return NextResponse.json({ ok: true, tags });
}

