// ARCHIVED COPY (2026-09-02) of the sole file `main.ts` in the Val Town val
// `prosciuttocrudo/close-the-windows-pinger`. Kept here so re-spinning is a
// paste job even if the val is ever lost. During hibernation the live val's
// file type was flipped `interval` -> `script`, which is what stops it firing;
// its cron expression (*/5 * * * *) and GH_PAT env var are otherwise intact.
// See ../HIBERNATION.md.

// Pings the close-the-windows monitor workflow via workflow_dispatch.
// GitHub `schedule` cron is best-effort and drops most runs, delaying the
// open/close-the-windows push. This reliable 5-min ping fixes that.

export default async function (interval: Interval) {
  const token = Deno.env.get("GH_PAT");
  if (!token) throw new Error("GH_PAT env var not set");

  const res = await fetch(
    "https://api.github.com/repos/prosciutto-crudo/close-the-windows/actions/workflows/monitor.yml/dispatches",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "close-the-windows-pinger (val.town)",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );

  if (res.status !== 204) {
    const text = await res.text();
    throw new Error(`Dispatch failed: ${res.status} ${text}`);
  }
  console.log(`Dispatched monitor.yml at ${new Date().toISOString()} (204)`);
}
