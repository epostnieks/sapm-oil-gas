# SAPM Monte Carlo Simulation

## Overview
This directory contains the Monte Carlo simulation script and results for the System Asset Pricing Model (SAPM) domain analysis.

## Files
- `sapm_monte_carlo.py` — Python simulation script
- `data/mc_results.json` — Full simulation results for this domain (histogram, channel breakdowns, CI bounds)
- `data/domain_meta.json` — Domain metadata (axioms, thresholds, methods, PSF parameters)

## How to Run
```bash
pip install numpy pandas
python scripts/sapm_monte_carlo.py --seed 42
```

## Parameters
- **Seed**: 42 (fixed for reproducibility)
- **Draws**: 10,000 per domain
- **Method**: Parametric bootstrap with correlated channel draws

## Outputs
- `sapm_mc_results.json` — Per-domain: β_W distribution (50-bin histogram), channel welfare contributions (mean, P5, P50, P95, share), aggregate stats (mean, median, 90% CI, % Hollow Win, % above thresholds)
- `sapm_mc_summary.csv` — One row per domain with key statistics

## Interpretation
- **β_W** (System Beta): Welfare destruction per dollar of private gain. β_W > 1 = Hollow Win.
- **90% CI**: 5th–95th percentile of the simulated β_W distribution.
- **% Hollow Win**: Fraction of draws where β_W > 1 (both parties gain, system loses).
- **Channel shares**: Each channel's contribution to total welfare cost.
