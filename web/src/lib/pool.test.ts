import { afterEach, describe, expect, spyOn, test } from "bun:test";
import { automaticWorkers, mostWorkers, runTasks, saveWorkers, secondsLeft, storedWorkers, type Task } from "./pool";

type FakeWorker = { id: number; ready: Promise<never> };
const started = (id: number): FakeWorker => ({ id, ready: Promise.resolve() as Promise<never> });
const starting = (id: number): FakeWorker => ({ id, ready: new Promise<never>(() => {}) });

const fail = () => Promise.reject(new Error("broken outline"));

describe("runTasks", () => {
  test("a free worker takes the next task", async () => {
    const ran: [task: number, worker: number][] = [];
    const slow = Promise.withResolvers<void>();
    const task =
      (n: number): Task<FakeWorker> =>
      async (worker) => {
        ran.push([n, worker.id]);
        if (n === 0) await slow.promise;
        if (n === 3) slow.resolve();
      };
    await runTasks([started(0), started(1)], [0, 1, 2, 3].map(task));
    expect(ran).toEqual([
      [0, 0],
      [1, 1],
      [2, 1],
      [3, 1],
    ]);
  });

  test("ends with the last task, not with workers still starting", async () => {
    let done = 0;
    await runTasks([started(0), starting(1)], [async () => void done++, async () => void done++]);
    expect(done).toBe(2);
    await runTasks([starting(0)], []);
  });

  test("a worker that can't start is left out", async () => {
    const broken = { id: 1, ready: Promise.reject(new Error("offline")) };
    const ran: number[] = [];
    await runTasks([started(0), broken], [async (w) => void ran.push(w.id), async (w) => void ran.push(w.id)]);
    expect(ran).toEqual([0, 0]);
  });

  test("a failing task fails the run", async () => {
    await expect(runTasks([started(0)], [fail, async () => {}])).rejects.toThrow("broken outline");
  });
});

const device = (hardwareConcurrency: number, touch = false) => {
  Object.defineProperty(navigator, "hardwareConcurrency", { value: hardwareConcurrency, configurable: true });
  spyOn(globalThis, "matchMedia").mockReturnValue({ matches: touch } as MediaQueryList);
};

test("the time left is shared between the workers", () => {
  expect(secondsLeft([6], 65, 8)).toBe(48);
  expect(secondsLeft([2, 4], 10, 4)).toBe(6);
  expect(secondsLeft([4, 4, 4], 4, 4)).toBe(4); // one job, on one worker
  expect(secondsLeft([4], 1, 4)).toBe(0);
});

describe("how many workers", () => {
  afterEach(() => {
    spyOn(globalThis, "matchMedia").mockRestore();
    Reflect.deleteProperty(navigator, "hardwareConcurrency");
    saveWorkers(null);
  });

  test("automatic leaves a core to everything else", () => {
    for (const [cores, workers] of [
      [8, 7],
      [4, 3],
      [2, 1],
      [1, 1],
      [32, 8],
    ] as const) {
      device(cores);
      expect(automaticWorkers()).toBe(workers);
    }
  });

  test("automatic is few on phones and tablets", () => {
    device(8, true);
    expect(automaticWorkers()).toBe(2);
    device(1, true);
    expect(automaticWorkers()).toBe(1);
  });

  test("a browser that hides cores doesn't take choices away", () => {
    device(4);
    expect(mostWorkers()).toBe(8);
    device(12);
    expect(mostWorkers()).toBe(12);
    device(64);
    expect(mostWorkers()).toBe(16);
  });

  test("the choice is kept, as far as it can be picked", () => {
    device(12);
    expect(storedWorkers()).toBeNull();
    saveWorkers(12);
    expect(storedWorkers()).toBe(12);
    device(8);
    expect(storedWorkers()).toBe(8);
    for (const broken of ["0", "-1", "2.5", "many"]) {
      localStorage.setItem("fontmint-workers", broken);
      expect(storedWorkers()).toBeNull();
    }
  });
});
