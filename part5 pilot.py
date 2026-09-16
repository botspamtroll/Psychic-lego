#!/usr/bin/env python3
"""PSYCHIC LEGO Part 5 pilot — cross-domain SER/IDR measurement.

Single-operator pilot. Mechanical blindness only (corruption sites chosen by
seeded RNG, never by the author after seeing data; verifier functions never
read corruption metadata). NOT agent-blind: one model wrote generator,
corruptor, self-checks, and verifiers. That limitation is the headline
caveat of the writeup, stated there in full.

Design frozen before execution:
  - 10 domains, 3 seeded corruption classes each = 30 corrupted runs
  - +10 uncorrupted control runs through the identical pipeline
  - self-check = the ordinary aggregate/endpoint check a model would run
  - independent check = pointwise/structural recomputation from source
  - SER = corrupted runs passing self-check / corrupted runs
  - IDR = corrupted runs flagged by independent check / corrupted runs
  - LEGO event = self-check PASS and independent FAIL (the phenomenon)
  - double miss = corruption passing both (recorded, not hidden)
  - false positive = control flagged by either check (recorded)

Seed: 20260916 (run date). No artifact -> no Fact.
"""
import json, time
import numpy as np
from scipy import integrate, optimize

SEED = 20260916
TWO_PI = 2.0 * np.pi

# ---------------------------------------------------------------- domains
def gen_primes():
    limit = 1300
    s = np.ones(limit, bool); s[:2] = False
    for i in range(2, int(limit ** 0.5) + 1):
        if s[i]:
            s[i * i::i] = False
    ps = np.nonzero(s)[0][:200].astype(float)
    return ps, {"count": 200, "first": 2.0, "last": 1223.0}

def self_primes(a, m):
    return len(a) == m["count"] and a[0] == m["first"] and a[-1] == m["last"]

def ind_primes(a, m):
    truth, _ = gen_primes()
    ok = len(a) == len(truth) and np.array_equal(a, truth)
    return ok, "exact sequence match vs recomputed sieve"

def gen_catalan():
    c = [1]
    for n in range(19):
        c.append(c[-1] * 2 * (2 * n + 1) // (n + 2))
    return np.array(c, float), {"count": 20, "last": 1767263190.0}

def self_catalan(a, m):
    return len(a) == m["count"] and a[0] == 1.0 and a[-1] == m["last"]

def ind_catalan(a, m):
    truth, _ = gen_catalan()
    return np.array_equal(a, truth), "recurrence recomputation, exact"

def gen_eigen():
    r = np.random.default_rng(SEED + 3)
    A = r.normal(size=(12, 12)); A = (A + A.T) / 2.0
    w = np.linalg.eigvalsh(A)
    return w.copy(), {"trace": float(np.trace(A)), "A": A}

def self_eigen(a, m):
    return abs(a.sum() - m["trace"]) < 1e-8

def ind_eigen(a, m):
    truth = np.linalg.eigvalsh(m["A"])
    ok = len(a) == 12 and np.max(np.abs(a - truth)) < 1e-9
    return ok, "eigvalsh recomputation from stored matrix, pointwise 1e-9"

ODE_T = np.linspace(0.1, 5.0, 50)

def gen_ode():
    # y' = -y, y(0)=1, RK4 fixed step
    h, y, t, out, k = 1e-3, 1.0, 0.0, [], 0
    ts = list(ODE_T)
    nxt = 0
    while nxt < len(ts):
        while t + h / 2 < ts[nxt]:
            k1 = -y; k2 = -(y + h * k1 / 2); k3 = -(y + h * k2 / 2); k4 = -(y + h * k3)
            y += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
            t += h
        out.append(y)
        nxt += 1
    return np.array(out), {"y_final_analytic": float(np.exp(-5.0))}

def self_ode(a, m):
    return abs(a[-1] - m["y_final_analytic"]) < 1e-4

def ind_ode(a, m):
    sol = integrate.solve_ivp(lambda t, y: -y, (0, 5), [1.0], method="Radau",
                              t_eval=ODE_T, rtol=1e-11, atol=1e-13)
    ok = np.max(np.abs(a - sol.y[0])) < 1e-6
    return ok, "independent Radau integration, pointwise 1e-6"

def gen_logistic():
    x, out, r = 0.2, [], 3.9
    for _ in range(200):
        x = r * x * (1.0 - x)
        out.append(x)
    return np.array(out), {"r": 3.9, "x0": 0.2}

def self_logistic(a, m):
    return bool(np.all((a >= 0) & (a <= 1)) and 0.3 < a.mean() < 0.75)

def ind_logistic(a, m):
    x, out = m["x0"], []
    for _ in range(200):
        x = m["r"] * x * (1.0 - x)
        out.append(x)
    return np.max(np.abs(a - np.array(out))) < 1e-15, "exact deterministic re-iteration"

def regen_logistic_wrong(rng):
    x, out, r = 0.2, [], 3.9 + 1e-9
    for _ in range(200):
        x = r * x * (1.0 - x)
        out.append(x)
    return np.array(out)

def gen_stats():
    r = np.random.default_rng(SEED + 6)
    s = r.normal(10.0, 2.0, 100)
    return s.copy(), {"claimed_mean": float(s.mean()), "claimed_std": float(s.std())}

def self_stats(a, m):
    return abs(a.mean() - m["claimed_mean"]) < 0.01 and abs(a.std() - m["claimed_std"]) < 0.05

def ind_stats(a, m):
    r = np.random.default_rng(SEED + 6)
    truth = r.normal(10.0, 2.0, 100)
    return np.array_equal(a, truth), "regeneration from documented seed, exact"

def rosen(x):
    return (1 - x[0]) ** 2 + 100.0 * (x[1] - x[0] ** 2) ** 2

def rosen_grad(x):
    return np.array([-2 * (1 - x[0]) - 400 * x[0] * (x[1] - x[0] ** 2),
                     200 * (x[1] - x[0] ** 2)])

def gen_opt():
    res = optimize.minimize(rosen, np.array([-1.2, 1.0]), jac=rosen_grad,
                            method="BFGS", options={"gtol": 1e-12})
    return res.x.copy(), {"f_claimed": float(res.fun)}

def self_opt(a, m):
    return m["f_claimed"] < 1e-10           # plausibility of the *claimed* value only

def ind_opt(a, m):
    ok = rosen(a) < 1e-10 and np.linalg.norm(rosen_grad(a)) < 1e-4
    return ok, "objective + gradient recomputed at reported point"

FFT_N = 256
FFT_T = np.arange(FFT_N) / FFT_N

def gen_fft():
    sig = np.sin(TWO_PI * 5 * FFT_T) + 0.5 * np.sin(TWO_PI * 12 * FFT_T)
    X = np.abs(np.fft.rfft(sig))
    return X.copy(), {"signal_power": float(np.sum(sig ** 2))}

def self_fft(a, m):
    tot = (a[0] ** 2 + a[-1] ** 2 + 2 * np.sum(a[1:-1] ** 2)) / FFT_N
    return abs(tot - m["signal_power"]) < 1e-6

def ind_fft(a, m):
    sig = np.sin(TWO_PI * 5 * FFT_T) + 0.5 * np.sin(TWO_PI * 12 * FFT_T)
    truth = np.abs(np.fft.rfft(sig))
    return np.max(np.abs(a - truth)) < 1e-10, "rfft recomputation from source signal"

def gen_binom():
    from math import comb
    n, p = 20, 0.3
    pmf = np.array([comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)])
    return pmf.copy(), {"n": 20, "p": 0.3}

def self_binom(a, m):
    return abs(a.sum() - 1.0) < 1e-12

def ind_binom(a, m):
    truth, _ = gen_binom()
    return np.max(np.abs(a - truth)) < 1e-15, "exact pmf recomputation"

INT_EDGES = np.linspace(0.0, 5.0, 26)

def gen_integration():
    vals = np.array([integrate.quad(lambda x: np.exp(-x * x), INT_EDGES[i], INT_EDGES[i + 1])[0]
                     for i in range(25)])
    from math import erf, sqrt, pi
    return vals, {"analytic_total": sqrt(pi) / 2.0 * erf(5.0)}

def self_integration(a, m):
    return abs(a.sum() - m["analytic_total"]) < 1e-9

def ind_integration(a, m):
    truth, _ = gen_integration()
    return np.max(np.abs(a - truth)) < 1e-10, "per-panel quadrature recomputation"

# ---------------------------------------------------------------- corruptions
def _pick_index(b, rng):
    """Interior index when the array has an interior; any index otherwise."""
    if len(b) > 3:
        return int(rng.integers(1, len(b) - 1))
    return int(rng.integers(0, len(b)))

def c_fabricate(a, m, rng, dom):
    b = a.copy()
    i = _pick_index(b, rng)
    if dom in ("primes", "catalan"):
        b[i] = b[i] + 2.0
    else:
        s = max(b.std(), 1e-6 * max(abs(b.mean()), 1.0), 1e-9)
        b[i] = b[i] + (0.5 + rng.random()) * s * (1 if rng.random() < 0.5 else -1)
    return b, f"index {i}"

def c_transpose(a, m, rng, dom):
    b = a.copy()
    for _ in range(50):
        i = int(rng.integers(1, len(b) - 2))
        if b[i] != b[i + 1]:
            b[i], b[i + 1] = b[i + 1], b[i]
            return b, f"swap {i},{i+1}"
    return b, "no-op"

def c_aggpair(a, m, rng, dom):
    b = a.copy()
    i, j = rng.choice(np.arange(1, len(b) - 1), 2, replace=False)
    d = 0.1 * max(b.std(), 1e-6)
    b[int(i)] += d; b[int(j)] -= d
    return b, f"+/-{d:.3g} at {int(i)},{int(j)}"

def c_round(a, m, rng, dom):
    b = np.round(a, 4)
    if np.array_equal(a, b):
        b = np.round(a, 2)
    return b, "rounded to 4 decimals"

def c_substitute(a, m, rng, dom):
    b = a.copy()
    i = _pick_index(b, rng)
    if i == 0:
        i = 1
    b[i] = b[i - 1]
    return b, f"index {i} <- neighbor"

def c_wrongparam(a, m, rng, dom):
    if dom == "logistic":
        return regen_logistic_wrong(rng), "r = 3.9 + 1e-9"
    raise ValueError

def c_perturb(a, m, rng, dom):
    b = a.copy()
    i = int(rng.integers(0, len(b)))
    b[i] += 5e-3
    return b, f"+5e-3 at index {i}"

CORRUPTIONS = {"fabricate": c_fabricate, "transpose": c_transpose,
               "agg_preserving": c_aggpair, "rounding": c_round,
               "substitute": c_substitute, "wrong_param": c_wrongparam,
               "precision_perturbation": c_perturb}

DOMAINS = [
    ("primes",      gen_primes,      self_primes,      ind_primes,
     ["fabricate", "transpose", "substitute"]),
    ("catalan",     gen_catalan,     self_catalan,     ind_catalan,
     ["fabricate", "transpose", "substitute"]),
    ("eigenvalues", gen_eigen,       self_eigen,       ind_eigen,
     ["fabricate", "transpose", "agg_preserving", "rounding"]),
    ("ode",         gen_ode,         self_ode,         ind_ode,
     ["fabricate", "agg_preserving", "rounding"]),
    ("logistic",    gen_logistic,    self_logistic,    ind_logistic,
     ["fabricate", "wrong_param", "rounding", "substitute"]),
    ("statistics",  gen_stats,       self_stats,       ind_stats,
     ["fabricate", "agg_preserving", "rounding", "transpose"]),
    ("optimization", gen_opt,        self_opt,         ind_opt,
     ["fabricate", "substitute", "precision_perturbation"]),
    ("fourier",     gen_fft,         self_fft,         ind_fft,
     ["fabricate", "agg_preserving", "rounding", "transpose"]),
    ("binomial",    gen_binom,       self_binom,       ind_binom,
     ["fabricate", "agg_preserving", "rounding", "transpose"]),
    ("integration", gen_integration, self_integration, ind_integration,
     ["fabricate", "agg_preserving", "rounding", "transpose"]),
]

def main():
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    ledger = []

    # seeded corruption assignment: 3 distinct classes per domain, chosen by RNG
    assignment = {}
    for name, *_rest, applicable in [(d[0], d[1], d[4]) for d in DOMAINS]:
        pass
    for d in DOMAINS:
        name, applicable = d[0], d[4]
        assignment[name] = list(rng.choice(applicable, 3, replace=False))
    print("seeded assignment:")
    for k, v in assignment.items():
        print(f"  {k}: {v}")

    for name, gen, selfc, indc, applicable in DOMAINS:
        truth, meta = gen()

        # control run (uncorrupted)
        sc = bool(selfc(truth.copy(), meta))
        ic, diag = indc(truth.copy(), meta)
        ledger.append(dict(domain=name, corruption="NONE (control)", detail="",
                           self_check="PASS" if sc else "FAIL",
                           independent="PASS" if ic else "FAIL",
                           truth_state="clean"))

        # corrupted runs
        for ctype in assignment[name]:
            cand, detail = CORRUPTIONS[ctype](truth, meta, rng, name)
            changed = not np.array_equal(cand, truth)
            sc = bool(selfc(cand, meta))
            ic, diag = indc(cand, meta)
            ledger.append(dict(domain=name, corruption=ctype, detail=detail,
                               self_check="PASS" if sc else "FAIL",
                               independent="PASS" if ic else "FAIL",
                               truth_state="corrupted" if changed else "UNCHANGED-BUG"))

    # ---------------- scoring
    corr = [r for r in ledger if r["truth_state"] == "corrupted"]
    ctrl = [r for r in ledger if r["truth_state"] == "clean"]
    bug = [r for r in ledger if r["truth_state"] == "UNCHANGED-BUG"]
    ser_pass = [r for r in corr if r["self_check"] == "PASS"]
    idr_catch = [r for r in corr if r["independent"] == "FAIL"]
    lego = [r for r in corr if r["self_check"] == "PASS" and r["independent"] == "FAIL"]
    miss = [r for r in corr if r["self_check"] == "PASS" and r["independent"] == "PASS"]
    both = [r for r in corr if r["self_check"] == "FAIL" and r["independent"] == "FAIL"]
    weird = [r for r in corr if r["self_check"] == "FAIL" and r["independent"] == "PASS"]
    fp = [r for r in ctrl if r["self_check"] == "FAIL" or r["independent"] == "FAIL"]

    print(f"\ncorrupted runs: {len(corr)}   controls: {len(ctrl)}   "
          f"corruption no-ops (bugs): {len(bug)}")
    print(f"SER  (self-check escape rate)      = {len(ser_pass)}/{len(corr)} "
          f"= {len(ser_pass)/len(corr):.2f}")
    print(f"IDR  (independent detection rate)  = {len(idr_catch)}/{len(corr)} "
          f"= {len(idr_catch)/len(corr):.2f}")
    print(f"LEGO events (self PASS + ind FAIL) = {len(lego)}")
    print(f"double misses (both PASS)          = {len(miss)}")
    print(f"caught by both                     = {len(both)}")
    print(f"self FAIL + ind PASS (anomaly)     = {len(weird)}")
    print(f"control false positives            = {len(fp)}")

    print("\nfull ledger:")
    print(f"{'domain':<13}{'corruption':<24}{'self':<6}{'indep':<6}detail")
    for r in ledger:
        print(f"{r['domain']:<13}{r['corruption']:<24}{r['self_check']:<6}"
              f"{r['independent']:<6}{r['detail']}")

    with open("/home/claude/part5_ledger.json", "w") as f:
        json.dump(dict(seed=SEED, assignment={k: list(map(str, v)) for k, v in assignment.items()},
                       ledger=ledger,
                       metrics=dict(corrupted=len(corr), controls=len(ctrl),
                                    SER=len(ser_pass) / len(corr),
                                    IDR=len(idr_catch) / len(corr),
                                    lego_events=len(lego), double_misses=len(miss),
                                    caught_by_both=len(both), false_positives=len(fp))),
                  f, indent=1)
    print(f"\nledger written; runtime {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
