#!/usr/bin/env node
/**
 * Kills any process still bound to this project's dev ports (backend 8000,
 * frontend 5173) before `npm run dev` starts a fresh pair. Runs
 * automatically as the `predev` script — see package.json.
 *
 * Why this exists: uvicorn --reload's WatchFiles reloader spawns a child
 * worker process separate from the terminal-visible parent. On Windows, a
 * closed terminal or Ctrl+C doesn't always tear down that child cleanly —
 * it can survive, keep holding port 8000, and silently keep answering HTTP
 * requests with no visible console output, which is indistinguishable from
 * "the new server is broken" until you notice nothing is being logged for
 * incoming requests.
 */

const { execSync } = require("node:child_process")

const PORTS = [8000, 5173]
const isWindows = process.platform === "win32"

function pidsOnPort(port) {
  try {
    if (isWindows) {
      const out = execSync(
        `powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue).OwningProcess"`,
        { encoding: "utf8" },
      )
      return [...new Set(out.split(/\s+/).filter(Boolean))]
    }
    const out = execSync(`lsof -ti tcp:${port}`, { encoding: "utf8" })
    return [...new Set(out.split(/\s+/).filter(Boolean))]
  } catch {
    return [] // nothing listening on this port — not an error
  }
}

function killPid(pid) {
  try {
    if (isWindows) {
      execSync(`powershell -NoProfile -Command "Stop-Process -Id ${pid} -Force -ErrorAction SilentlyContinue"`)
    } else {
      execSync(`kill -9 ${pid}`)
    }
    console.log(`[free-dev-ports] killed pid ${pid}`)
  } catch {
    // already gone between listing and killing — fine
  }
}

for (const port of PORTS) {
  const pids = pidsOnPort(port)
  if (pids.length === 0) {
    console.log(`[free-dev-ports] port ${port} already free`)
    continue
  }
  console.log(`[free-dev-ports] port ${port} in use by pid(s) ${pids.join(", ")} — killing`)
  for (const pid of pids) killPid(pid)
}
