#!/usr/bin/env python3
"""
Raspberry Pi Power Monitor
- Reads CT sensors from MCP3008 over SPI
- Calculates RMS current and power
- Sends JSON payloads to a server
- First-time setup wizard -> /etc/powermonitor/config.conf
"""

import os, sys, json, time, math, signal, requests, spidev, pytz
from datetime import datetime, timezone

# ============================================================
# Defaults (used only if no config file exists)
# ============================================================
CONFIG_PATH       = "/etc/powermonitor/config.conf"
DEVICE_ID         = "powermon_default"
LOCATION_NAME     = "DefaultLocation"
SERVER_URL        = "https://linesights.com/api/data"
GRID_VOLTAGE      = 120.0
CT_RATING         = 30
SEND_INTERVAL     = 1
DETECTED_TIMEZONE = "UTC"

CT_BURDEN_RESISTOR = 18.0
CT_CALIBRATION     = 1.0
CT_REVERSED        = True
DEFAULT_CALIBRATION= 0.88

CT_CHANNELS       = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
FREQUENCY         = 60
ADC_MAX_CODE      = 1023.0
NUM_SAMPLES       = 500

# Globals
spi = None
running = True

# ============================================================
# Setup Wizard
# ============================================================
def first_time_setup():
    print("=== Power Monitor First-Time Setup ===")
    device_id   = input(f"Device ID [{DEVICE_ID}]: ").strip() or DEVICE_ID
    location    = input(f"Location name [{LOCATION_NAME}]: ").strip() or LOCATION_NAME
    server_url  = input(f"Server URL [{SERVER_URL}]: ").strip() or SERVER_URL
    grid_voltage= input(f"Grid voltage (V) [{GRID_VOLTAGE}]: ").strip() or str(GRID_VOLTAGE)
    ct_rating   = input(f"CT rating (A) [{CT_RATING}]: ").strip() or str(CT_RATING)
    send_interval = input(f"Send interval (s) [{SEND_INTERVAL}]: ").strip() or str(SEND_INTERVAL)
    timezone    = input(f"Timezone (IANA) [{DETECTED_TIMEZONE}]: ").strip() or DETECTED_TIMEZONE

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write(f"DEVICE_ID={device_id}\n")
        f.write(f"LOCATION_NAME={location}\n")
        f.write(f"SERVER_URL={server_url}\n")
        f.write(f"GRID_VOLTAGE={grid_voltage}\n")
        f.write(f"CT_RATING={ct_rating}\n")
        f.write(f"SEND_INTERVAL={send_interval}\n")
        f.write(f"DETECTED_TIMEZONE={timezone}\n")

    print(f"\n✅ Config saved to {CONFIG_PATH}")
    return {
        "DEVICE_ID": device_id,
        "LOCATION_NAME": location,
        "SERVER_URL": server_url,
        "GRID_VOLTAGE": grid_voltage,
        "CT_RATING": ct_rating,
        "SEND_INTERVAL": send_interval,
        "DETECTED_TIMEZONE": timezone,
    }

# ============================================================
# Config Loader
# ============================================================
def load_config():
    if not os.path.exists(CONFIG_PATH):
        return first_time_setup()
    cfg = {}
    with open(CONFIG_PATH) as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k,v=line.split("=",1)
                cfg[k.strip()] = v.strip()
    return cfg

cfg = load_config()
DEVICE_ID         = cfg.get("DEVICE_ID", DEVICE_ID)
LOCATION_NAME     = cfg.get("LOCATION_NAME", LOCATION_NAME)
SERVER_URL        = cfg.get("SERVER_URL", SERVER_URL)
GRID_VOLTAGE      = float(cfg.get("GRID_VOLTAGE", GRID_VOLTAGE))
CT_RATING         = int(cfg.get("CT_RATING", CT_RATING))
SEND_INTERVAL     = int(cfg.get("SEND_INTERVAL", SEND_INTERVAL))
DETECTED_TIMEZONE = cfg.get("DETECTED_TIMEZONE", DETECTED_TIMEZONE)

# ============================================================
# Logging & time
# ============================================================
def log_message(message: str):
    try:
        local_tz = pytz.timezone(DETECTED_TIMEZONE)
        local_time = datetime.now(local_tz)
        timestamp = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def get_utc_timestamp():
    utc_time = datetime.now(timezone.utc)
    return utc_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# ============================================================
# SPI / ADC
# ============================================================
def init_spi():
    global spi
    try:
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 500_000
        log_message("✅ SPI initialized successfully")
        return True
    except Exception as e:
        log_message(f"❌ SPI initialization failed: {e}")
        return False

def read_adc(channel: int):
    if channel < 0 or channel > 7: return -1
    try:
        adc = spi.xfer2([1, (8 + channel) << 4, 0])
        return ((adc[1] & 3) << 8) + adc[2]
    except Exception:
        return -1

def collect_all_ct_samples(num_samples: int):
    ct_samples = {ct_num: [] for ct_num in CT_CHANNELS.keys()}
    sample_interval = (8.0 / FREQUENCY) / num_samples
    start_time = time.time()
    for i in range(num_samples):
        for ct_num, ch in CT_CHANNELS.items():
            val = read_adc(ch)
            if val >= 0: ct_samples[ct_num].append(val)
        elapsed = time.time() - start_time
        expected = (i + 1) * sample_interval
        if expected > elapsed:
            time.sleep(expected - elapsed)
    return ct_samples

# ============================================================
# Power calculations
# ============================================================
def volts_per_amp(rating: int):
    if rating == 30: return 1.0/30
    if rating == 50: return 1.0/50
    if rating == 100: return 0.9/100
    if rating == 200: return 1.0/200
    return 1.0/float(rating)

def calculate_power_for_ct(samples, ct_num):
    if not samples or len(samples) < 100: return None
    num = len(samples)
    v_per_code = 3.31 / ADC_MAX_CODE
    scaling = (v_per_code * CT_CALIBRATION * DEFAULT_CALIBRATION) / volts_per_amp(CT_RATING)
    sum_squares = sum(s*s for s in samples)
    sum_values = sum(samples)
    avg_raw = sum_values/num
    mean_square = sum_squares/num
    current_rms = math.sqrt(max(0, mean_square - (avg_raw*avg_raw))) * scaling
    variation = max(samples) - min(samples)

    pf = 0.9
    power = GRID_VOLTAGE * abs(current_rms) * pf
    if CT_REVERSED:
        if power < 0: power = abs(power)
        else: current_rms = -abs(current_rms)
    if abs(power) < 1.0: power = 0.0
    apparent = GRID_VOLTAGE * abs(current_rms)
    pf = pf if apparent > 0.1 else 0.0

    return {"power": abs(power), "current": abs(current_rms),
            "voltage": GRID_VOLTAGE, "pf": pf, "variation": variation}

def calculate_all_ct_power(all_samples):
    return {ct: calculate_power_for_ct(all_samples.get(ct), ct) for ct in CT_CHANNELS}

# ============================================================
# Networking
# ============================================================
def send_to_server(data, retries=2, timeout=5):
    last_err = None
    for _ in range(retries+1):
        try:
            r = requests.post(SERVER_URL, json=data, timeout=timeout)
            if r.status_code == 200: return True, "Success"
            last_err = f"HTTP {r.status_code}"
        except requests.exceptions.Timeout: last_err = "Timeout"
        except requests.exceptions.ConnectionError: last_err = "Connection failed"
        except Exception as e: last_err = f"Error: {str(e)[:80]}"
        time.sleep(0.5)
    return False, last_err or "Unknown error"

def format_ct_results_for_log(ct_results):
    active, total = [], 0.0
    for ct, res in ct_results.items():
        if res and res['power']>0:
            total += res['power']
            active.append(f"CT{ct}:{res['power']:.1f}W/{res['current']:.3f}A")
    return f"Total:{total:.1f}W | " + " | ".join(active) if active else "No active loads detected"

# ============================================================
# Main loop & signals
# ============================================================
def signal_handler(sig, frame):
    global running
    log_message("Received shutdown signal, stopping service...")
    running = False
    if spi:
        try: spi.close()
        except: pass
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    log_message(f"🔌 Power Monitor Starting - {LOCATION_NAME}")
    log_message("="*60)
    log_message(f"Device ID: {DEVICE_ID}")
    log_message(f"Location: {LOCATION_NAME}")
    log_message(f"Voltage: {GRID_VOLTAGE}V | CT Rating: {CT_RATING}A | Interval: {SEND_INTERVAL}s")
    log_message(f"Server: {SERVER_URL}")
    log_message("="*60)

    if not init_spi():
        log_message("❌ Cannot start without SPI. Check wiring.")
        return

    while running:
        try:
            samples = collect_all_ct_samples(NUM_SAMPLES)
            results = calculate_all_ct_power(samples)
            if any(res for res in results.values()):
                payload = {
                    "device_id": DEVICE_ID,
                    "timestamp": get_utc_timestamp(),
                    "location": LOCATION_NAME,
                    "timezone": DETECTED_TIMEZONE,
                    "readings": {"cts": {}, "voltage_rms": round(GRID_VOLTAGE,1)}
                }
                for ct in range(1,7):
                    res = results.get(ct)
                    if res:
                        payload["readings"]["cts"][f"ct_{ct}"] = {
                            "real_power_w": round(res['power'],1),
                            "amps": round(res['current'],3),
                            "pf": round(res['pf'],3)
                        }
                    else:
                        payload["readings"]["cts"][f"ct_{ct}"] = {
                            "real_power_w":0.0,"amps":0.0,"pf":0.0
                        }
                ok,msg = send_to_server(payload)
                status = "✅" if ok else "❌"
                log_message(f"{status} {format_ct_results_for_log(results)} | {msg}")
            else:
                log_message("❌ No valid readings from CTs")
            time.sleep(SEND_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log_message(f"❌ Error: {e}")
            time.sleep(5)

    log_message("🛑 Power Monitor Service Stopped")

if __name__ == "__main__":
    main()