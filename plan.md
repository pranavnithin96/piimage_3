# Plan: Improve Sampling Speed & Resolution

## Goal
Only sample active/configured CT channels, increase SPI speed, and increase sample count so each active channel gets significantly more samples per AC cycle — improving RMS accuracy and low-load detection.

## Changes

All changes are in two files: `src/pi_monitor_script.py` and `config/config.conf`.

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

### Step 3: Increase sample count

**File: `src/pi_monitor_script.py`**
- Change `NUM_SAMPLES = 500` → `NUM_SAMPLES = 1200` (line 41)
- With faster SPI and fewer channels, this gives dense per-channel coverage

### Step 4: Only sample active channels

**File: `src/pi_monitor_script.py`**
- `collect_all_ct_samples()` already iterates `CT_CHANNELS` — since Step 1 rebuilds `CT_CHANNELS` to only active ones, this works automatically
- Update `main()` payload loop (line 647): instead of `for ct in range(1,7)`, iterate only active channels, but still send zeros for inactive ones so the server payload format stays consistent

### Step 5: Log the improvement

**File: `src/pi_monitor_script.py`**
- In `main()` startup logging, add a line showing active CTs and estimated samples/cycle
- Example: `"Active CTs: 1,2,3 | ~400 samples/channel/cycle @ 1.35MHz SPI"`

### Step 6: Update interactive setup

**File: `src/turnkey_setup_interactive.py`**
- Add `ACTIVE_CTS` to the config editor fields so users can configure which CTs are active from the TUI

## Impact Summary

| Metric | Before | After (3 active CTs) |
|--------|--------|----------------------|
| SPI speed | 500 kHz | 1.35 MHz |
| Channels sampled | 6 | 3 |
| Total samples/window | 500 | 1200 |
| Samples/channel/window | ~83 | ~400 |
| Samples/channel/cycle (8 cycles) | ~10 | ~50 |
| Effective sampling rate/channel | ~625 Hz | ~9 kHz |

## Files Modified
1. `src/pi_monitor_script.py` — SPI speed, NUM_SAMPLES, ACTIVE_CTS parsing, config validation
2. `config/config.conf` — add ACTIVE_CTS field
3. `src/turnkey_setup_interactive.py` — add ACTIVE_CTS to TUI editor
