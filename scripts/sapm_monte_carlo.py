"""
SAPM Monte Carlo Simulation
============================
Postnieks Impossibility Program — System Asset Pricing Model
Runs 10,000-draw Monte Carlo simulations for all 25 calibrated domains.

Each domain's welfare cost channels are sampled from specified distributions:
  - triangular(lo, mode, hi)
  - log-normal parameterized to match (lo, mode, hi) as 5th/50th/95th percentiles
  - uniform(lo, hi)

For each draw:
  - Total welfare cost W = sum of channel draws (in $B)
  - Private payoff Pi sampled from uniform(Pi_lo, Pi_hi)
  - beta_W = W / Pi
  - Hollow Win = (beta_W > 1)

Outputs:
  - sapm_mc_results.json  : full results for all domains (for dashboard consumption)
  - sapm_mc_summary.csv   : human-readable summary table
  - sapm_mc_distributions/ : per-domain histogram data (for PSF and MC tab charts)

Usage:
  python sapm_monte_carlo.py
  python sapm_monte_carlo.py --domains dsm,cement,pops  # specific domains only
  python sapm_monte_carlo.py --draws 100000             # more draws
"""

import json
import csv
import os
import sys
import argparse
import numpy as np
from scipy import stats

# ── reproducibility ──────────────────────────────────────────────────────────
SEED = 42
rng  = np.random.default_rng(SEED)

# ── domain definitions ───────────────────────────────────────────────────────
# Each domain: key, pi_lo, pi_hi ($B), and 6 channels
# Channel: (name, dist, lo, hi, mode)  — all values in $B
# dist: "triangular" | "lognormal" | "uniform"
DOMAINS = [
  {
    "key": "sapm-algorithmic-pricing",
    "label": "Algorithmic Pricing",
    "pi_lo": 32, "pi_hi": 48,
    "channels": [
      ("Price inflation",           "triangular", 40,  90,  62),
      ("Competition suppression",   "triangular", 25,  65,  44),
      ("Consumer surplus extract.", "lognormal",  18,  55,  33),
      ("Market concentration",      "triangular", 10,  35,  20),
      ("Regulatory arbitrage",      "uniform",     5,  22,  13),
      ("Governance capture",        "triangular",  3,  14,   7),
    ],
  },
  {
    "key": "sapm-arms-exports",
    "label": "Arms Exports",
    "pi_lo": 240, "pi_hi": 350,
    "channels": [
      ("Mortality & morbidity",      "triangular",  95, 163, 129),
      ("Macro contraction",          "triangular", 120, 250, 185),
      ("Diversion & proliferation",  "lognormal",   85, 180, 130),
      ("Procurement corruption",     "triangular",  60, 140,  95),
      ("Arms race externalities",    "triangular",  90, 120, 105),
      ("Institutional decay",        "uniform",     20,  67,  43),
    ],
  },
  {
    "key": "sapm-aviation-emissions",
    "label": "Aviation Emissions",
    "pi_lo": 850, "pi_hi": 1200,
    "channels": [
      ("CO2 climate damages",        "triangular", 1800, 3200, 2400),
      ("Non-CO2 forcing (contrails)","lognormal",   800, 2100, 1400),
      ("Air quality mortality",      "triangular",   90,  180,  130),
      ("Community noise",            "triangular",   40,  120,   75),
      ("Distributional conc.",       "uniform",      60,  180,  115),
      ("Governance failure",         "triangular",   20,   80,   45),
    ],
  },
  {
    "key": "sapm-big-tech-platform-monopoly",
    "label": "Big Tech Monopoly",
    "pi_lo": 120, "pi_hi": 200,
    "channels": [
      ("Monopoly rent extraction",   "triangular", 280, 520, 390),
      ("Privacy & data exploit.",    "lognormal",  150, 380, 240),
      ("Innovation suppression",     "triangular", 120, 340, 210),
      ("Labor market monopsony",     "triangular",  80, 220, 145),
      ("Attention & mental health",  "lognormal",   90, 280, 170),
      ("Governance capture",         "uniform",     30, 110,  65),
    ],
  },
  {
    "key": "sapm-cement-calcination-floor",
    "label": "Cement (Calcination Floor)",
    "pi_lo": 280, "pi_hi": 380,
    "channels": [
      ("Calcination CO2 (process)",  "triangular",  980, 1480, 1210),
      ("Combustion CO2 (energy)",    "triangular",  420,  680,  540),
      ("Air quality mortality",      "triangular",  120,  280,  190),
      ("Quarrying ecosystem",        "uniform",      40,  120,   75),
      ("NOx & particulate health",   "triangular",   30,   90,   55),
      ("Governance failure",         "uniform",      15,   65,   38),
    ],
  },
  {
    "key": "sapm-coal",
    "label": "Coal Combustion",
    "pi_lo": 800, "pi_hi": 1200,
    "channels": [
      ("Climate damages (CO2)",      "triangular", 2200, 3500, 2850),
      ("Air pollution mortality",    "triangular", 2800, 4700, 3760),
      ("Coal mine methane",          "triangular",   55,   95,   72),
      ("Extraction harms",           "uniform",      30,   75,   50),
      ("Mercury neurotoxicity",      "triangular",    6,   12,  8.7),
      ("Governance capture",         "triangular",   80,  160,  117),
    ],
  },
  {
    "key": "sapm-cre-urban-hollowing",
    "label": "CRE Urban Hollowing",
    "pi_lo": 10, "pi_hi": 18,
    "channels": [
      ("Property tax base erosion",  "triangular",  25,  65,  42),
      ("Urban service reduction",    "triangular",  18,  48,  31),
      ("Small business displacement","lognormal",   12,  38,  22),
      ("Pedestrian economy loss",    "triangular",   8,  28,  16),
      ("Transit ridership decline",  "uniform",      5,  18,  11),
      ("Governance capture",         "triangular",   2,  10,   5),
    ],
  },
  {
    "key": "sapm-dsm-abyssal-recovery-floor",
    "label": "Deep-Sea Mining (Abyssal Floor)",
    "pi_lo": 3.5, "pi_hi": 6.5,
    "channels": [
      ("Benthic habitat destruction","triangular",  6.5, 11.0,  8.5),
      ("Sediment plume damage",      "triangular",  4.2,  8.5,  6.2),
      ("Midwater ecosystem disrupt.","lognormal",   3.5,  8.5,  5.8),
      ("Carbon sequestration loss",  "triangular",  2.5,  6.0,  4.1),
      ("Biodiversity extinction",    "lognormal",   5.0, 11.5,  8.0),
      ("Governance failure",         "uniform",     0.5,  2.5,  1.5),
    ],
  },
  {
    "key": "sapm-fisheries-no-impossibility",
    "label": "Global Fisheries",
    "pi_lo": 28, "pi_hi": 48,
    "channels": [
      ("Stock depletion",            "triangular",  51, 105,  83),
      ("Bycatch & discards",         "triangular",   8,  22,  15),
      ("Benthic habitat destruction","triangular",  12,  45,  27),
      ("IUU fishing",                "triangular",  10,  24,  17),
      ("Capacity-enhancing subsidies","triangular", 18,  28, 22.2),
      ("Governance & forced labor",  "uniform",      6,  22,  13.2),
    ],
  },
  {
    "key": "sapm-gambling",
    "label": "Gambling Industry",
    "pi_lo": 35, "pi_hi": 55,
    "channels": [
      ("Problem gambling health",    "triangular",  85, 160, 118),
      ("Bankruptcy & financial",     "triangular",  40,  90,  62),
      ("Family & domestic harm",     "lognormal",   25,  65,  42),
      ("Crime & fraud",              "triangular",  18,  48,  30),
      ("Youth initiation",           "triangular",  12,  38,  22),
      ("Governance capture",         "uniform",      5,  18,  10),
    ],
  },
  {
    "key": "sapm-gene-drives",
    "label": "Gene Drives (Ecological Ratchet)",
    "pi_lo": 1.5, "pi_hi": 4.5,
    "channels": [
      ("Ecological cascade risk",    "lognormal",    8,  45,  22),
      ("Resistance evolution",       "triangular",   4,  18,   9),
      ("Off-target species harm",    "lognormal",    3,  15,   7),
      ("Gene flow non-target pop.",  "triangular",   2,  12,   5),
      ("Irreversibility cost",       "lognormal",    5,  30,  14),
      ("Governance failure",         "uniform",      1,   8,   4),
    ],
  },
  {
    "key": "sapm-gig-economy",
    "label": "Gig Economy",
    "pi_lo": 48, "pi_hi": 80,
    "channels": [
      ("Benefits & labor prot. gap", "triangular",  65, 140,  98),
      ("Wage suppression",           "triangular",  40,  95,  65),
      ("Safety & workers comp",      "triangular",  20,  55,  35),
      ("Public benefits externaliz.","uniform",     18,  48,  30),
      ("Algorithm control loss",     "lognormal",   10,  35,  20),
      ("Governance capture",         "triangular",   5,  20,  12),
    ],
  },
  {
    "key": "sapm-oil-gas",
    "label": "Oil & Gas Extraction",
    "pi_lo": 3000, "pi_hi": 4000,
    "channels": [
      ("Climate damages (CO2)",      "triangular", 12000, 21000, 16100),
      ("Methane externalities",      "triangular",  1500,  3500,  2400),
      ("Air quality mortality",      "triangular",   850,  1800,  1250),
      ("Ecosystem destruction",      "lognormal",    400,  1200,   720),
      ("Governance capture",         "triangular",   600,  1400,   960),
      ("Stranded asset risk",        "uniform",      300,   900,   570),
    ],
  },
  {
    "key": "sapm-opioids",
    "label": "Opioid Industry",
    "pi_lo": 18, "pi_hi": 32,
    "channels": [
      ("Mortality (overdose)",       "triangular", 100, 185, 140),
      ("Healthcare & treatment",     "triangular",  40,  85,  58),
      ("Lost productivity",          "triangular",  30,  70,  48),
      ("Criminal justice costs",     "uniform",     12,  35,  22),
      ("Child welfare & NAS",        "triangular",   8,  25,  15),
      ("Governance capture",         "triangular",   5,  20,  11),
    ],
  },
  {
    "key": "sapm-orbital-debris",
    "label": "Orbital Debris (Kessler Ceiling)",
    "pi_lo": 220, "pi_hi": 380,
    "channels": [
      ("Kessler cascade risk",       "lognormal",  400000, 1200000, 700000),
      ("LEO congestion externalities","lognormal",  50000,  200000, 110000),
      ("Satellite lifetime reduction","triangular", 15000,   60000,  35000),
      ("Launch risk & insurance",    "triangular",  8000,   25000,  15000),
      ("Astronomy & dark sky",       "triangular",  2000,    8000,   4500),
      ("Governance failure",         "uniform",     1000,    5000,   2800),
    ],
  },
  {
    "key": "sapm-palm-oil",
    "label": "Palm Oil Deforestation",
    "pi_lo": 52, "pi_hi": 84,
    "channels": [
      ("Deforestation & carbon",     "triangular", 140, 280, 205),
      ("Peat drainage emissions",    "triangular",  80, 180, 128),
      ("Biodiversity loss",          "lognormal",   55, 145,  95),
      ("Indigenous land rights",     "triangular",  30,  80,  52),
      ("Water contamination",        "uniform",     15,  45,  28),
      ("Governance failure",         "triangular",  10,  35,  20),
    ],
  },
  {
    "key": "sapm-pbm-rebate",
    "label": "Pharmacy Benefit Managers",
    "pi_lo": 22, "pi_hi": 34,
    "channels": [
      ("Rebate trap / formulary",    "triangular",  36,  60,  48),
      ("Patient OOP extraction",     "triangular", 2.5, 3.2, 2.85),
      ("Pharmacy desert formation",  "triangular",   8,  22,  14),
      ("Medication non-adherence",   "lognormal",  100, 528, 280),
      ("List-price inflation",       "triangular", 180, 420, 290),
      ("Governance capture",         "uniform",     30,  90,  55),
    ],
  },
  {
    "key": "sapm-pops-beyond-pfas",
    "label": "POPs Beyond PFAS (Inheritance Floor)",
    "pi_lo": 55, "pi_hi": 85,
    "channels": [
      ("Neurodevelopmental damage",  "triangular", 266, 340, 280),
      ("Metabolic & carcinogenic",   "triangular", 44.7, 73,  58),
      ("Remediation & management",   "triangular", 3.8, 5.2, 4.5),
      ("Ecological contamination",   "lognormal",   15,  40,  27),
      ("Arctic & Indigenous",        "triangular",   8,  25,  16),
      ("Governance failure",         "uniform",    2.5, 4.5, 3.5),
    ],
  },
  {
    "key": "sapm-student-loans-forprofit",
    "label": "For-Profit Student Loans",
    "pi_lo": 38, "pi_hi": 58,
    "channels": [
      ("Default & unrepayable debt", "triangular",  55, 115,  82),
      ("Credential non-fulfillment", "triangular",  35,  75,  52),
      ("Foregone earnings",          "triangular",  25,  60,  40),
      ("Family formation delay",     "uniform",     12,  32,  21),
      ("Mental health burden",       "triangular",   8,  22,  14),
      ("Governance capture",         "triangular",   5,  18,  10),
    ],
  },
  {
    "key": "sapm-tobacco",
    "label": "Tobacco Industry",
    "pi_lo": 800, "pi_hi": 1150,
    "channels": [
      ("Premature mortality (VSL)",  "triangular", 3800, 5800, 4750),
      ("Healthcare & morbidity",     "triangular",  600, 1200,  850),
      ("Secondhand smoke harm",      "triangular",  280,  580,  420),
      ("Youth initiation & addict.", "lognormal",   120,  320,  210),
      ("Environmental degradation",  "uniform",      40,  120,   75),
      ("Governance capture",         "triangular",   25,   80,   48),
    ],
  },
  {
    "key": "sapm-topsoil-erosion",
    "label": "Topsoil Erosion (Pedogenesis Floor)",
    "pi_lo": 300, "pi_hi": 470,
    "channels": [
      ("Ag productivity loss",       "triangular", 650, 1200,  890),
      ("Carbon release from soil",   "triangular", 320,  680,  480),
      ("Water retention & flood",    "triangular", 180,  420,  280),
      ("Water quality degradation",  "triangular",  90,  240,  155),
      ("Biodiversity & ecosystem",   "lognormal",   55,  180,  108),
      ("Governance failure",         "uniform",     20,   80,   48),
    ],
  },
  {
    "key": "sapm-upf-full",
    "label": "Ultra-Processed Food",
    "pi_lo": 240, "pi_hi": 360,
    "channels": [
      ("Metabolic disease",          "triangular",  800, 1300, 1100),
      ("Addiction & behavioral",     "lognormal",   100,  280,  180),
      ("Agricultural distortion",    "triangular",   95,  220,  155),
      ("Environmental degradation",  "triangular",   65,  180,  115),
      ("Governance capture",         "triangular",   30,  120,   70),
      ("Intergenerational harm",     "triangular",   55,  165,  100),
    ],
  },
  {
    "key": "sapm-upf-no-impossibility",
    "label": "Ultra-Processed Food (No Impossibility)",
    "pi_lo": 240, "pi_hi": 360,
    "channels": [
      ("Metabolic disease",          "triangular",  800, 1300, 1100),
      ("Addiction & behavioral",     "lognormal",   100,  280,  180),
      ("Agricultural distortion",    "triangular",   95,  220,  155),
      ("Environmental degradation",  "triangular",   65,  180,  115),
      ("Governance capture",         "triangular",   30,  120,   70),
      ("Intergenerational harm",     "triangular",   55,  165,  100),
    ],
  },
  {
    "key": "sapm-water-privatization",
    "label": "Water Privatization",
    "pi_lo": 200, "pi_hi": 300,
    "channels": [
      ("Access denial & exclusion",  "triangular", 180, 380, 265),
      ("Infrastructure underinvest.","triangular", 120, 280, 195),
      ("Public health externalities","triangular",  80, 200, 135),
      ("Democratic accountability",  "uniform",     40, 120,  75),
      ("Environmental compliance",   "triangular",  25,  80,  48),
      ("Governance capture",         "uniform",     15,  55,  32),
    ],
  },
  {
    "key": "sapm-wmd-capability-diffusion-ceiling",
    "label": "WMD/LAWS (Capability Diffusion Ceiling)",
    "pi_lo": 60, "pi_hi": 120,
    "channels": [
      ("Nuclear first-use EV",       "lognormal",   50000, 5000000, 500000),
      ("Knowledge diffusion stock",  "lognormal",    5000,   200000,  40000),
      ("LAWS autonomous diffusion",  "triangular",    500,    50000,   8000),
      ("WMD terrorism premium",      "lognormal",    1000,   100000,  12000),
      ("New START instability",      "uniform",      2000,    20000,  10000),
      ("Proliferation ratchet",      "lognormal",    1000,    50000,   8000),
    ],
  },
]

# ── distribution samplers ─────────────────────────────────────────────────────

def sample_triangular(n, lo, hi, mode):
    """Sample from triangular distribution."""
    c = (mode - lo) / (hi - lo)
    return rng.triangular(lo, mode, hi, size=n)

def sample_lognormal(n, lo, mode, hi):
    """
    Fit log-normal so that:
      lo   ≈ 5th  percentile
      mode ≈ 50th percentile (median)
      hi   ≈ 95th percentile
    We solve for mu and sigma using the median and the spread.
    """
    # Use median = mode for log-normal (approximate)
    mu = np.log(max(mode, 1e-9))
    # Estimate sigma from spread: 95th - 5th spans ~3.29 sigma on log scale
    if hi > lo and lo > 0:
        sigma = (np.log(hi) - np.log(lo)) / 3.29
        sigma = max(sigma, 0.01)
    else:
        sigma = 0.3
    return rng.lognormal(mu, sigma, size=n)

def sample_uniform(n, lo, hi, mode=None):
    return rng.uniform(lo, hi, size=n)

SAMPLERS = {
    "triangular": sample_triangular,
    "lognormal":  sample_lognormal,
    "uniform":    sample_uniform,
}

# ── run simulation ────────────────────────────────────────────────────────────

def run_domain(domain, n_draws=10000):
    """Run MC for one domain. Returns dict of results."""
    key     = domain["key"]
    pi_lo   = domain["pi_lo"]
    pi_hi   = domain["pi_hi"]
    channels= domain["channels"]

    # Sample private payoff
    pi_draws = rng.uniform(pi_lo, pi_hi, size=n_draws)

    # Sample each channel and sum
    channel_draws = {}
    W_draws = np.zeros(n_draws)
    for ch in channels:
        name, dist, lo, hi, mode = ch
        s = SAMPLERS[dist](n_draws, lo, hi, mode)
        s = np.maximum(s, 0)          # clamp to non-negative
        channel_draws[name] = s
        W_draws += s

    # Compute beta_W per draw
    beta_draws = W_draws / pi_draws

    # Classify
    is_hollow_win = beta_draws > 1.0

    # Summary stats
    mean_beta   = float(np.mean(beta_draws))
    median_beta = float(np.median(beta_draws))
    ci_lo       = float(np.percentile(beta_draws, 5))
    ci_hi       = float(np.percentile(beta_draws, 95))
    pct_hw      = float(np.mean(is_hollow_win) * 100)
    pct_above_3 = float(np.mean(beta_draws > 3) * 100)
    pct_above_5 = float(np.mean(beta_draws > 5) * 100)

    mean_W  = float(np.mean(W_draws))
    mean_pi = float(np.mean(pi_draws))

    # Beta histogram (50 bins for dashboard)
    hist_lo  = max(0, float(np.percentile(beta_draws, 0.5)))
    hist_hi  = float(np.percentile(beta_draws, 99.5))
    counts, edges = np.histogram(beta_draws, bins=50, range=(hist_lo, hist_hi))
    histogram = [
        {"bin_lo": float(edges[i]), "bin_hi": float(edges[i+1]), "count": int(counts[i])}
        for i in range(len(counts))
    ]

    # Channel contribution stats
    channel_stats = {}
    for name, draws in channel_draws.items():
        channel_stats[name] = {
            "mean":   float(np.mean(draws)),
            "p5":     float(np.percentile(draws, 5)),
            "p50":    float(np.percentile(draws, 50)),
            "p95":    float(np.percentile(draws, 95)),
            "share":  float(np.mean(draws) / mean_W) if mean_W > 0 else 0,
        }

    return {
        "key":         key,
        "label":       domain["label"],
        "n_draws":     n_draws,
        "seed":        SEED,
        "beta_W": {
            "mean":         mean_beta,
            "median":       median_beta,
            "ci_lo_5":      ci_lo,
            "ci_hi_95":     ci_hi,
            "pct_hw":       pct_hw,
            "pct_above_3":  pct_above_3,
            "pct_above_5":  pct_above_5,
            "min":          float(np.min(beta_draws)),
            "max":          float(np.max(beta_draws)),
        },
        "welfare_cost_B": {
            "mean":   mean_W,
            "ci_lo":  float(np.percentile(W_draws, 5)),
            "ci_hi":  float(np.percentile(W_draws, 95)),
        },
        "private_payoff_B": {
            "mean":   mean_pi,
            "lo":     pi_lo,
            "hi":     pi_hi,
        },
        "system_adjusted_payoff_B": {
            "mean": float(np.mean(W_draws - pi_draws) * -1),  # negative = deficit
        },
        "channels": channel_stats,
        "histogram": histogram,
    }

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAPM Monte Carlo Simulation")
    parser.add_argument("--draws",   type=int, default=10000, help="Number of MC draws (default: 10000)")
    parser.add_argument("--domains", type=str, default="all",  help="Comma-separated domain keys, or 'all'")
    parser.add_argument("--outdir",  type=str, default=".",    help="Output directory")
    args = parser.parse_args()

    n_draws  = args.draws
    out_dir  = args.outdir
    os.makedirs(out_dir, exist_ok=True)

    # Filter domains
    if args.domains == "all":
        domains_to_run = DOMAINS
    else:
        keys = set(args.domains.split(","))
        domains_to_run = [d for d in DOMAINS if d["key"] in keys or
                          any(k in d["key"] for k in keys)]

    print(f"Running {n_draws:,} draws for {len(domains_to_run)} domains (seed={SEED})")
    print("-" * 60)

    all_results = []
    for domain in domains_to_run:
        result = run_domain(domain, n_draws)
        all_results.append(result)
        bw = result["beta_W"]
        print(f"  {result['label']:<42} β_W={bw['mean']:.2f}  "
              f"90%CI=[{bw['ci_lo_5']:.2f},{bw['ci_hi_95']:.2f}]  "
              f"HW={bw['pct_hw']:.1f}%")

    # ── write JSON ──────────────────────────────────────────────────────────
    json_path = os.path.join(out_dir, "sapm_mc_results.json")
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nJSON results → {json_path}")

    # ── write CSV summary ───────────────────────────────────────────────────
    csv_path = os.path.join(out_dir, "sapm_mc_summary.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "key", "label", "n_draws", "seed",
            "beta_W_mean", "beta_W_median", "beta_W_ci_lo_5", "beta_W_ci_hi_95",
            "pct_hollow_win", "pct_above_3", "pct_above_5",
            "welfare_cost_mean_B", "welfare_cost_ci_lo_B", "welfare_cost_ci_hi_B",
            "pi_mean_B", "psa_deficit_mean_B",
        ])
        for r in all_results:
            bw  = r["beta_W"]
            wc  = r["welfare_cost_B"]
            pi  = r["private_payoff_B"]
            psa = r["system_adjusted_payoff_B"]
            writer.writerow([
                r["key"], r["label"], r["n_draws"], r["seed"],
                f"{bw['mean']:.4f}", f"{bw['median']:.4f}",
                f"{bw['ci_lo_5']:.4f}", f"{bw['ci_hi_95']:.4f}",
                f"{bw['pct_hw']:.2f}", f"{bw['pct_above_3']:.2f}", f"{bw['pct_above_5']:.2f}",
                f"{wc['mean']:.2f}", f"{wc['ci_lo']:.2f}", f"{wc['ci_hi']:.2f}",
                f"{pi['mean']:.2f}", f"{psa['mean']:.2f}",
            ])
    print(f"CSV summary   → {csv_path}")
    print(f"\nDone. {len(all_results)} domains completed.")


if __name__ == "__main__":
    main()
