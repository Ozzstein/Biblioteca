---
title: "SOP-001: Coin Cell Assembly (CR2032)"
version: "2.1"
last_updated: 2025-11-01
author: "Lab Operations"
source: manual
doc_type: sop
---

# SOP-001: Coin Cell Assembly (CR2032)

## Purpose

Standard procedure for assembling CR2032 coin cells for electrochemical characterization.

## Safety

- All assembly steps performed in argon-filled glovebox (<0.1 ppm O2, <0.1 ppm H2O).
- Electrolyte skin contact: rinse with water for 15 minutes.
- LiPF6-based electrolytes release HF when exposed to moisture — dispose in dedicated HF waste.

## Materials

- CR2032 coin cell cases (positive and negative caps)
- Cathode electrode disc (15 mm diameter)
- Anode disc or lithium metal disc (15 mm diameter)
- Separator: Celgard 2325, 19 mm diameter
- Electrolyte: 1M LiPF6 in EC/DMC 1:1 v/v
- Manual coin cell crimper

## Procedure

### 1. Preparation (inside glovebox)

1.1 Dry all components at 80°C overnight in vacuum oven before glovebox transfer.
1.2 Transfer via antechamber — minimum two pump/purge cycles.

### 2. Assembly

2.1 Place positive cap (flat side up) in assembly stand.
2.2 Place cathode disc (coated side up) in cap.
2.3 Add 40 μL electrolyte to cathode disc using micropipette.
2.4 Place separator on wetted cathode.
2.5 Add 20 μL electrolyte to separator.
2.6 Place anode disc (shiny side down for Li metal) on separator.
2.7 Place spacer disc and spring on anode.
2.8 Close with negative cap.
2.9 Crimp at 1000 N using manual crimper.

### 3. Quality Check

Measure OCV immediately after crimping. Expected ranges:
- LFP/Li: 3.3–3.5 V
- NMC/Li: 3.6–4.0 V
- Graphite/Li: 1.5–3.0 V (SOC-dependent)

Quarantine cells outside expected OCV range.

### 4. Rest Protocol

Rest assembled cells at room temperature for minimum 4 hours before electrochemical testing
to allow complete electrolyte wetting.

## Troubleshooting

| Symptom | Likely Cause | Action |
|---|---|---|
| OCV below expected range | Poor contact or partial short | Check crimp quality, remeasure |
| OCV drops immediately after crimp | Internal short circuit | Discard cell |
| High initial impedance | Insufficient electrolyte | Cannot fix post-crimp; discard |
| Electrolyte visible outside cell | Overfill or failed crimp | Discard; adjust fill volume next batch |
