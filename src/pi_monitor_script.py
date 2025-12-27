#!/usr/bin/env python3
"""
Raspberry Pi Power Monitor
- Reads CT sensors from MCP3008 over SPI
- Calculates RMS current and power
- Sends JSON payloads to a server
- First-time setup wizard -> /etc/powermonitor/config.conf
- Features: Background HTTP, connection pooling, local buffering
"""

import os, sys, json, time, math, signal, spidev, pytz
import threading
import queue
from datetime import datetime, timezone

# Import requests with session support
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

CT_CALIBRATION     = 1.0
DEFAULT_CALIBRATION = 0.88

CT_CHANNELS       = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
FREQUENCY         = 60
ADC_MAX_CODE      = 1023.0
NUM_SAMPLES       = 500

# Globals
spi = None
running = True

# ============================================================
# Performance: Background sending with buffering
# ============================================================
BUFFER_FILE = "/var/log/powermonitor/buffer.json"
MAX_BUFFER_SIZE = 1000  # Max readings to buffer locally
BUFFER_SAVE_INTERVAL = 300  # Save buffer to disk every 5 minutes
send_queue = queue.Queue(maxsize=MAX_BUFFER_SIZE)
http_session = None
sender_thread = None
last_buffer_save = 0  # Track last periodic save time

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
    tz_name     = input(f"Timezone (IANA) [{DETECTED_TIMEZONE}]: ").strip() or DETECTED_TIMEZONE

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write(f"DEVICE_ID={device_id}\n")
        f.write(f"LOCATION_NAME={location}\n")
        f.write(f"SERVER_URL={server_url}\n")
        f.write(f"GRID_VOLTAGE={grid_voltage}\n")
        f.write(f"CT_RATING={ct_rating}\n")
        f.write(f"SEND_INTERVAL={send_interval}\n")
        f.write(f"DETECTED_TIMEZONE={tz_name}\n")

    print(f"\n✅ Config saved to {CONFIG_PATH}")
    return {
        "DEVICE_ID": device_id,
        "LOCATION_NAME": location,
        "SERVER_URL": server_url,
        "GRID_VOLTAGE": grid_voltage,
        "CT_RATING": ct_rating,
        "SEND_INTERVAL": send_interval,
        "DETECTED_TIMEZONE": tz_name,
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
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

def validate_config(cfg):
    """Validate config values and return safe defaults if invalid"""
    errors = []

    # Validate GRID_VOLTAGE
    try:
        voltage = float(cfg.get("GRID_VOLTAGE", GRID_VOLTAGE))
        if voltage < 100 or voltage > 250:
            errors.append(f"GRID_VOLTAGE={voltage} out of range (100-250), using {GRID_VOLTAGE}")
            voltage = GRID_VOLTAGE
    except ValueError:
        errors.append(f"GRID_VOLTAGE invalid, using {GRID_VOLTAGE}")
        voltage = GRID_VOLTAGE

    # Validate CT_RATING
    try:
        ct = int(cfg.get("CT_RATING", CT_RATING))
        if ct not in [30, 50, 100, 200]:
            errors.append(f"CT_RATING={ct} not supported (30/50/100/200), using {CT_RATING}")
            ct = CT_RATING
    except ValueError:
        errors.append(f"CT_RATING invalid, using {CT_RATING}")
        ct = CT_RATING

    # Validate SEND_INTERVAL
    try:
        interval = int(cfg.get("SEND_INTERVAL", SEND_INTERVAL))
        if interval < 1 or interval > 60:
            errors.append(f"SEND_INTERVAL={interval} out of range (1-60), using {SEND_INTERVAL}")
            interval = SEND_INTERVAL
    except ValueError:
        errors.append(f"SEND_INTERVAL invalid, using {SEND_INTERVAL}")
        interval = SEND_INTERVAL

    # Validate SERVER_URL
    server = cfg.get("SERVER_URL", SERVER_URL)
    if not server.startswith("http://") and not server.startswith("https://"):
        errors.append(f"SERVER_URL must start with http:// or https://, using {SERVER_URL}")
        server = SERVER_URL

    # Print any validation errors
    for error in errors:
        print(f"⚠️ Config warning: {error}")

    return {
        "DEVICE_ID": cfg.get("DEVICE_ID", DEVICE_ID),
        "LOCATION_NAME": cfg.get("LOCATION_NAME", LOCATION_NAME),
        "SERVER_URL": server,
        "GRID_VOLTAGE": voltage,
        "CT_RATING": ct,
        "SEND_INTERVAL": interval,
        "DETECTED_TIMEZONE": cfg.get("DETECTED_TIMEZONE", DETECTED_TIMEZONE)
    }

cfg = load_config()
validated = validate_config(cfg)
DEVICE_ID         = validated["DEVICE_ID"]
LOCATION_NAME     = validated["LOCATION_NAME"]
SERVER_URL        = validated["SERVER_URL"]
GRID_VOLTAGE      = validated["GRID_VOLTAGE"]
CT_RATING         = validated["CT_RATING"]
SEND_INTERVAL     = validated["SEND_INTERVAL"]
DETECTED_TIMEZONE = validated["DETECTED_TIMEZONE"]

# ============================================================
# Logging & time
# ============================================================
# Cache timezone object for performance (created once, used many times)
_cached_timezone = None

def get_local_timezone():
    """Get cached timezone object"""
    global _cached_timezone
    if _cached_timezone is None:
        try:
            _cached_timezone = pytz.timezone(DETECTED_TIMEZONE)
        except Exception:
            _cached_timezone = timezone.utc
    return _cached_timezone

def log_message(message: str):
    try:
        local_tz = get_local_timezone()
        local_time = datetime.now(local_tz)
        timestamp = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
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
    """Read ADC value from specified channel (0-7)"""
    if channel < 0 or channel > 7:
        return -1
    try:
        adc = spi.xfer2([1, (8 + channel) << 4, 0])
        return ((adc[1] & 3) << 8) + adc[2]
    except Exception as e:
        # SPI errors can happen occasionally, don't flood logs
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
    """Return CT output voltage per amp based on CT rating.

    Most CTs output 1V at rated current, but some 100A CTs
    output 0.9V at 100A (manufacturer variance).
    """
    CT_OUTPUT_VOLTAGE = {
        30: 1.0,    # 30A CT outputs 1.0V at 30A
        50: 1.0,    # 50A CT outputs 1.0V at 50A
        100: 0.9,   # 100A CT outputs 0.9V at 100A (common variant)
        200: 1.0,   # 200A CT outputs 1.0V at 200A
    }
    output_v = CT_OUTPUT_VOLTAGE.get(rating, 1.0)
    return output_v / float(rating)

def calculate_power_for_ct(samples, ct_num):
    """Calculate power from CT samples using RMS calculation"""
    if not samples or len(samples) < 100:
        return None

    num = len(samples)
    v_per_code = 3.31 / ADC_MAX_CODE
    scaling = (v_per_code * CT_CALIBRATION * DEFAULT_CALIBRATION) / volts_per_amp(CT_RATING)

    # Calculate RMS current using standard deviation method
    # RMS = sqrt(mean(x²) - mean(x)²) for AC signals centered around DC offset
    sum_squares = sum(s*s for s in samples)
    sum_values = sum(samples)
    avg_raw = sum_values / num
    mean_square = sum_squares / num
    variance = max(0, mean_square - (avg_raw * avg_raw))
    current_rms = math.sqrt(variance) * scaling

    # Track signal variation for diagnostics
    variation = max(samples) - min(samples)

    # Assumed power factor (0.9 is typical for residential loads)
    # Note: True PF would require voltage waveform measurement
    pf = 0.9

    # Calculate real power (W) = V × I × PF
    power = GRID_VOLTAGE * current_rms * pf

    # Filter out noise floor (readings below 1W are likely noise)
    if power < 1.0:
        power = 0.0
        current_rms = 0.0
        pf = 0.0

    return {
        "power": round(power, 2),
        "current": round(current_rms, 4),
        "voltage": GRID_VOLTAGE,
        "pf": pf,
        "variation": variation
    }

def calculate_all_ct_power(all_samples):
    return {ct: calculate_power_for_ct(all_samples.get(ct), ct) for ct in CT_CHANNELS}

# ============================================================
# Networking - Optimized with connection pooling & background sending
# ============================================================
def init_http_session():
    """Initialize HTTP session with connection pooling for faster requests"""
    global http_session
    http_session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.1,
        status_forcelist=[500, 502, 503, 504]
    )

    # Mount adapter with connection pooling
    adapter = HTTPAdapter(
        pool_connections=1,
        pool_maxsize=5,
        max_retries=retry_strategy
    )
    http_session.mount("https://", adapter)
    http_session.mount("http://", adapter)

    # Set default headers
    http_session.headers.update({
        'Content-Type': 'application/json',
        'Connection': 'keep-alive'
    })

    log_message("✅ HTTP session initialized with connection pooling")
    return http_session

def load_buffer_from_disk():
    """Load any buffered data from disk (from previous offline period)"""
    try:
        if os.path.exists(BUFFER_FILE):
            with open(BUFFER_FILE, 'r') as f:
                buffered = json.load(f)
            if buffered:
                loaded_count = 0
                for item in buffered:
                    try:
                        send_queue.put_nowait(item)
                        loaded_count += 1
                    except queue.Full:
                        dropped = len(buffered) - loaded_count
                        log_message(f"⚠️ Queue full, dropped {dropped} old readings")
                        break
                log_message(f"📦 Loaded {loaded_count} buffered readings from disk")
            os.remove(BUFFER_FILE)
    except Exception as e:
        log_message(f"⚠️ Could not load buffer: {e}")

def save_buffer_to_disk(drain_queue=True):
    """Save pending queue items to disk for persistence

    Args:
        drain_queue: If True, empties the queue (for shutdown)
                     If False, copies items back to queue (for periodic save)
    """
    try:
        items = []
        # Get all items from queue
        while not send_queue.empty():
            try:
                items.append(send_queue.get_nowait())
            except queue.Empty:
                break

        if items:
            os.makedirs(os.path.dirname(BUFFER_FILE), exist_ok=True)
            with open(BUFFER_FILE, 'w') as f:
                json.dump(items, f)
            log_message(f"💾 Saved {len(items)} readings to disk buffer")

            # If not draining, put items back in queue
            if not drain_queue:
                for item in items:
                    try:
                        send_queue.put_nowait(item)
                    except queue.Full:
                        break
    except Exception as e:
        log_message(f"⚠️ Could not save buffer: {e}")

def clear_buffer_file():
    """Delete buffer file when queue is empty and all data sent"""
    try:
        if os.path.exists(BUFFER_FILE):
            os.remove(BUFFER_FILE)
            log_message("🗑️ Buffer file cleared - all data sent successfully")
    except Exception as e:
        log_message(f"⚠️ Could not clear buffer file: {e}")

def send_to_server_direct(data, timeout=3):
    """Direct HTTP send using session (faster due to connection reuse)"""
    try:
        r = http_session.post(SERVER_URL, json=data, timeout=timeout)
        if r.status_code == 200:
            return True, "Success"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection failed"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

def background_sender():
    """Background thread that sends queued data to server"""
    global running, last_buffer_save
    consecutive_failures = 0
    last_buffer_save = time.time()
    queue_was_full = False  # Track if we had buffered data

    while running:
        try:
            current_time = time.time()

            # Periodic buffer save (every 5 minutes) - protects against power loss
            if current_time - last_buffer_save > BUFFER_SAVE_INTERVAL:
                if not send_queue.empty():
                    save_buffer_to_disk(drain_queue=False)  # Save but keep in queue
                    queue_was_full = True
                last_buffer_save = current_time

            # Wait for data with timeout (allows clean shutdown)
            try:
                data = send_queue.get(timeout=1.0)
            except queue.Empty:
                # Queue is empty - clear disk buffer if we had data before
                if queue_was_full:
                    clear_buffer_file()
                    queue_was_full = False
                continue

            # Try to send
            success, msg = send_to_server_direct(data)

            if success:
                consecutive_failures = 0
                # Mark that we're processing buffered data
                if send_queue.qsize() > 0:
                    queue_was_full = True
            else:
                consecutive_failures += 1
                queue_was_full = True  # We have unsent data

                # Re-queue failed data if server is down (limit retries to prevent infinite loop)
                if consecutive_failures < 10:
                    try:
                        send_queue.put_nowait(data)
                    except queue.Full:
                        # Queue is full - log data loss
                        log_message(f"⚠️ Buffer full, dropping reading from {data.get('timestamp', 'unknown')}")
                else:
                    # Too many failures - drop this reading to prevent infinite retry
                    log_message(f"⚠️ Too many failures, dropping reading from {data.get('timestamp', 'unknown')}")

                # Back off if many failures (use short sleeps to allow quick shutdown)
                if consecutive_failures > 5:
                    backoff_time = min(consecutive_failures, 30)
                    # Sleep in 1-second intervals to check for shutdown
                    for _ in range(backoff_time):
                        if not running:
                            break
                        time.sleep(1)

        except Exception as e:
            log_message(f"⚠️ Sender thread error: {e}")
            time.sleep(1)

    # Save remaining queue to disk on shutdown
    save_buffer_to_disk(drain_queue=True)

def queue_for_sending(data):
    """Queue data for background sending (non-blocking)"""
    try:
        send_queue.put_nowait(data)
        return True, f"Queued ({send_queue.qsize()} pending)"
    except queue.Full:
        return False, "Buffer full"

def start_sender_thread():
    """Start the background sender thread"""
    global sender_thread
    # Not a daemon thread - we want it to finish saving before exit
    sender_thread = threading.Thread(target=background_sender, daemon=False)
    sender_thread.start()
    log_message("🚀 Background sender thread started")

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
    """Handle shutdown signals gracefully - allows buffer to be saved"""
    global running
    log_message("Received shutdown signal, stopping service...")
    running = False
    # Don't call sys.exit() here - let main() finish and save buffer

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup():
    """Clean up resources on shutdown"""
    global spi
    # Wait for sender thread to finish saving buffer
    if sender_thread and sender_thread.is_alive():
        log_message("Waiting for sender thread to finish...")
        sender_thread.join(timeout=5)

    # Close SPI
    if spi:
        try:
            spi.close()
            log_message("SPI closed")
        except Exception as e:
            log_message(f"⚠️ Error closing SPI: {e}")

def main():
    global running  # Need to modify global for signal to sender thread

    log_message(f"🔌 Power Monitor Starting - {LOCATION_NAME}")
    log_message("="*60)
    log_message(f"Device ID: {DEVICE_ID}")
    log_message(f"Location: {LOCATION_NAME}")
    log_message(f"Voltage: {GRID_VOLTAGE}V | CT Rating: {CT_RATING}A | Interval: {SEND_INTERVAL}s")
    log_message(f"Server: {SERVER_URL}")
    log_message("="*60)

    # Initialize optimized networking
    init_http_session()
    load_buffer_from_disk()
    start_sender_thread()

    if not init_spi():
        log_message("❌ Cannot start without SPI. Check wiring.")
        log_message("Shutting down...")
        running = False  # Signal sender thread to stop
        cleanup()
        return

    log_message("⚡ Fast mode: Background sending enabled")

    while running:
        try:
            loop_start = time.time()

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

                # Non-blocking queue instead of blocking HTTP call
                ok, msg = queue_for_sending(payload)
                status = "✅" if ok else "⚠️"

                loop_time = (time.time() - loop_start) * 1000
                log_message(f"{status} {format_ct_results_for_log(results)} | {msg} | {loop_time:.0f}ms")
            else:
                log_message("❌ No valid readings from CTs")

            # Sleep remaining time to maintain interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, SEND_INTERVAL - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log_message(f"❌ Error: {e}")
            time.sleep(5)

    log_message("🛑 Power Monitor Service Stopped")
    # Note: buffer is saved by background_sender() when it exits
    # cleanup() waits for sender thread to finish
    cleanup()

if __name__ == "__main__":
    main()