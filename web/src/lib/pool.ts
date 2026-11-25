// Shares a build's work between its workers.
import type { FontmintWorker } from "./client";

const KEY = "fontmint-workers";

// Browsers hide the real core count: Safari says 4 or 8, Brave a random number up to the real
// one. So it only sets the automatic number, and never takes away a choice below 8. The memory
// they report (Chromium only, random in Brave) isn't used at all.
const cores = () => navigator.hardwareConcurrency || 2;

/** The workers a build uses unless the user picks a number: few on phones and tablets, which
 * have little memory, elsewhere all cores but one, for the page and everything else. */
export function automaticWorkers(): number {
  if (matchMedia("(pointer: coarse)").matches) return Math.min(cores(), 2);
  return Math.max(1, Math.min(cores() - 1, 8));
}

/** The most workers the user can pick. */
export function mostWorkers(): number {
  return Math.min(Math.max(cores(), 8), 16);
}

/** The user's choice, or null for automatic. */
export function storedWorkers(): number | null {
  try {
    const workers = Number(localStorage.getItem(KEY));
    return Number.isInteger(workers) && workers > 0 ? Math.min(workers, mostWorkers()) : null;
  } catch {
    return null;
  }
}

export function saveWorkers(workers: number | null): void {
  try {
    if (workers === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(workers));
  } catch {
    // Private windows can refuse storage; the choice then lasts until the page closes.
  }
}

/** Seconds left, from how long each finished job took: the workers share the rest, but never
 * finish it sooner than one job takes. */
export function secondsLeft(finished: number[], total: number, workers: number): number {
  const mean = finished.reduce((sum, seconds) => sum + seconds, 0) / finished.length;
  const remaining = total - finished.length;
  return remaining ? mean * Math.max(remaining / workers, 1) : 0;
}

export type Task<W> = (worker: W) => Promise<void>;

/** Runs every task, each worker taking the next one once it's free, and ends with the last
 * task: not with workers that are still starting by then. The first worker has started; one
 * of the others that can't start is left out. */
export function runTasks<W extends Pick<FontmintWorker, "ready">>(workers: W[], tasks: Task<W>[]): Promise<void> {
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  const queue = [...tasks];
  let left = queue.length;
  if (!left) resolve();
  const work = async (worker: W) => {
    try {
      await worker.ready;
    } catch {
      return;
    }
    for (let task = queue.shift(); task; task = queue.shift()) {
      await task(worker);
      if (--left === 0) resolve();
    }
  };
  for (const worker of workers) work(worker).catch(reject);
  return promise;
}
