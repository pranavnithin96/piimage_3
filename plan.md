# Plan: Improve Sampling Speed & Resolution

## Goal
1. Only sample active/configured CT channels (skip unused ones)
2. Increase SPI speed for faster ADC reads
3. Sample continuously across the full send interval (not just a brief snapshot)

This ensures we capture machine behavior over the entire interval, not just a 133ms peek.

## Changes

Files modified: `src/pi_monitor_script.py`, `config/config.conf`, `src/turnkey_setup_interactive.py`

### Step 1: Add `ACTIVE_CTS` config option

**File: `config/config.conf`**
- Add `ACTIVE_CTS=1,2,3` (user specifies which CT channels have sensors connected)

**File: `src/pi_monitor_script.py`**
- Add default `ACTIVE_CTS = "1,2,3,4,5,6"` with the other defaults (line ~38)
- In `load_and_apply_config()`, parse the `ACTIVE_CTS` string into a list and rebuild `CT_CHANNELS` to only include active ones
- In `validate_config()`, validate that ACTIVE_CTS values are in range 1-6

### Step 2: Increase SPI speed

**File: `src/pi_monitor_script.py`**
- In `init_spi()` (line 257), change `spi.max_speed_hz = 500_000` → `1_350_000` (MCP3008 max at 3.3V)
- This makes each ADC read ~18μs instead of ~48μs

### Step 3: Continuous sampling across the full send interval

**File: `src/pi_monitor_script.py`**

Current behavior (sample-then-sleep):
```
|--sample 133ms--|-------sleep 867ms-------| → send
      13% coverage per interval
```

New behavior (continuous multi-window sampling):
```
|--window 1--|--window 2--|--window 3--|...|--window 7--| → average & send
|  ~133ms    |  ~133ms    |  ~133ms    |   |  ~133ms    |
|<------------------ ~1 second interval ---------------->|
      93% coverage per interval
```

Implementation:
- Rename `collect_all_ct_samples()` → keep it as the single-window function (samples 8 AC cycles = ~133ms)
- Add new `collect_continuous_samples()` that calls the single-window function repeatedly to fill the send interval
- Each window produces an RMS power value per channel
- Average the RMS power values across all windows before building the payload
- The number of windows is automatic: `floor(SEND_INTERVAL / window_duration)`

### Step 4: Only sample active channels

**File: `src/pi_monitor_script.py`**
- `collect_all_ct_samples()` already iterates `CT_CHANNELS` — since Step 1 rebuilds that dict from config, this works automatically
- Update `main()` payload loop: still send zeros for inactive CTs so the server payload format stays consistent

### Step 5: Increase samples per window

**File: `src/pi_monitor_script.py`**
- Change `NUM_SAMPLES = 500` → `NUM_SAMPLES = 1200`
- With faster SPI and fewer channels, each active channel gets ~400 samples per 133ms window (~50 per AC cycle)

### Step 6: Log the improvement

**File: `src/pi_monitor_script.py`**
- Startup log shows: active CTs, SPI speed, samples/window, windows/interval
- Example: `"Active CTs: 1,2,3 | 1200 samples/window | 7 windows/interval | 1.35MHz SPI"`

### Step 7: Update interactive setup

**File: `src/turnkey_setup_interactive.py`**
- Add `ACTIVE_CTS` to the config editor fields so users can toggle which CTs are active from the TUI

## Impact Summary

| Metric | Before | After (3 active CTs, 1s interval) |
|--------|--------|-----------------------------------|
| SPI speed | 500 kHz | 1.35 MHz |
| Channels sampled | 6 | 3 (configurable) |
| Sampling windows/interval | 1 | ~7 |
| Samples/channel/window | ~83 | ~400 |
| Samples/channel/cycle | ~10 | ~50 |
| Time coverage per interval | ~13% | ~93% |
| Machine cycle visibility | Spotty snapshots | Near-continuous |

## Files Modified
1. `src/pi_monitor_script.py` — SPI speed, NUM_SAMPLES, ACTIVE_CTS, continuous multi-window sampling
2. `config/config.conf` — add ACTIVE_CTS field
3. `src/turnkey_setup_interactive.py` — add ACTIVE_CTS to TUI editor
