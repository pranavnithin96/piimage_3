#!/usr/bin/env python3

import spidev
import time
import requests
import json
import math
import signal
import sys
import pytz
from datetime import datetime, timezone

# Configuration - Auto-generated from setup
GRID_VOLTAGE = 120.0
SERVER_URL = "https://linesights.com/api/data"
DEVICE_ID = "powermon_100000008d8d6dc5"
LOCATION_NAME = "Rockhill"
DETECTED_TIMEZONE = "America/New_York"
SEND_INTERVAL = 1

# CT Configuration
CT_CHANNELS = {
    1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5
}

# CT Settings - All CTs have same rating as selected by user
CT_RATING = 30
CT_BURDEN_RESISTOR = 18.0
CT_CALIBRATION = 1.0
CT_REVERSED = True
DEFAULT_CALIBRATION = 0.88

# Hardware configuration
FREQUENCY = 60
ADC_BITS = 1024
NUM_SAMPLES = 500

# Global variables
spi = None
running = True

def signal_handler(sig, frame):
    global running
    log_message("Received shutdown signal, stopping service...")
    running = False
    if spi:
        spi.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def log_message(message):
    """Log message with local timestamp"""
    try:
        # Show local time in logs for readability
        local_tz = pytz.timezone(DETECTED_TIMEZONE)
        local_time = datetime.now(local_tz)
        timestamp = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        print(f"[{timestamp}] {message}")
    except:
        # Fallback to UTC if timezone issues
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def get_utc_timestamp():
    """Get current UTC timestamp in proper ISO 8601 format for server transmission"""
    utc_time = datetime.now(timezone.utc)
    # Return ISO 8601 format with 'Z' suffix (Zulu time indicator for UTC)
    return utc_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'  # Include milliseconds, not microseconds

def get_local_time_info():
    """Get local time information for logging"""
    try:
        local_tz = pytz.timezone(DETECTED_TIMEZONE)
        local_time = datetime.now(local_tz)
        utc_time = datetime.now(timezone.utc)
        
        return {
            'local_time': local_time.strftime('%H:%M:%S %Z'),
            'utc_time': utc_time.strftime('%H:%M:%S UTC'),
            'timezone': DETECTED_TIMEZONE
        }
    except:
        utc_time = datetime.now(timezone.utc)
        return {
            'local_time': utc_time.strftime('%H:%M:%S UTC'),
            'utc_time': utc_time.strftime('%H:%M:%S UTC'), 
            'timezone': 'UTC'
        }

def init_spi():
    global spi
    try:
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 500000
        log_message("✅ SPI initialized successfully")
        return True
    except Exception as e:
        log_message(f"❌ SPI initialization failed: {e}")
        return False

def read_adc(channel):
    """Read single value from ADC channel"""
    if channel < 0 or channel > 7:
        return -1
    try:
        adc = spi.xfer2([1, (8 + channel) << 4, 0])
        data = ((adc[1] & 3) << 8) + adc[2]
        return data
    except Exception as e:
        return -1

def collect_all_ct_samples(num_samples):
    """Collect samples from all 6 CT sensors simultaneously"""
    ct_samples = {ct_num: [] for ct_num in CT_CHANNELS.keys()}
    sample_interval = (8.0 / FREQUENCY) / num_samples

    start_time = time.time()
    for i in range(num_samples):
        for ct_num, channel in CT_CHANNELS.items():
            ct_reading = read_adc(channel)
            if ct_reading >= 0:
                ct_samples[ct_num].append(ct_reading)

        elapsed = time.time() - start_time
        expected = (i + 1) * sample_interval
        if expected > elapsed:
            time.sleep(expected - elapsed)

    return ct_samples

def calculate_power_for_ct(current_samples, ct_num):
    """Calculate power for a single CT sensor"""
    
    if not current_samples or len(current_samples) < 100:
        return None

    num_samples = len(current_samples)
    
    # Board voltage reference (3.3V)
    board_voltage = 3.31
    vref = board_voltage / ADC_BITS
    
    # CT scaling based on user-selected CT rating
    if CT_RATING == 30:
        volts_per_amp = 1.0 / 30  # 30A:1V
    elif CT_RATING == 50:
        volts_per_amp = 1.0 / 50  # 50A:1V  
    elif CT_RATING == 100:
        volts_per_amp = 0.9 / 100  # 100A:0.9V (SCT-T16)
    elif CT_RATING == 200:
        volts_per_amp = 1.0 / 200  # 200A:1V
    else:
        volts_per_amp = 1.0 / CT_RATING  # Generic scaling
    
    current_scaling = (vref * CT_CALIBRATION * DEFAULT_CALIBRATION) / volts_per_amp
    
    # Process current samples
    sum_squares = 0
    sum_values = 0
    
    for sample in current_samples:
        sum_squares += sample * sample
        sum_values += sample
    
    # Calculate RMS current
    avg_raw = sum_values / num_samples
    mean_square = sum_squares / num_samples
    current_rms = math.sqrt(max(0, mean_square - (avg_raw * avg_raw))) * current_scaling
    
    # Debug info
    variation = max(current_samples) - min(current_samples)
    
    # Power calculation
    voltage_fixed = GRID_VOLTAGE
    power_factor = 0.90
    power_calculated = voltage_fixed * abs(current_rms) * power_factor
    
    # Handle CT reversal
    final_current = current_rms
    final_power = power_calculated
    
    if CT_REVERSED:
        if final_power < 0:
            final_power = abs(final_power)
        else:
            final_current = -abs(final_current)
    
    # Apply 1W threshold
    if abs(final_power) < 1.0:
        final_power = 0.0
    
    # Calculate apparent power and power factor
    apparent = voltage_fixed * abs(final_current)
    pf = power_factor if apparent > 0.1 else 0.0
    
    return {
        'power': abs(final_power),
        'current': abs(final_current), 
        'voltage': voltage_fixed,
        'pf': pf,
        'variation': variation
    }

def calculate_all_ct_power(all_ct_samples):
    """Calculate power for all CT sensors"""
    ct_results = {}
    
    for ct_num in CT_CHANNELS.keys():
        if ct_num in all_ct_samples:
            result = calculate_power_for_ct(all_ct_samples[ct_num], ct_num)
            ct_results[ct_num] = result
        else:
            ct_results[ct_num] = None
    
    return ct_results

def send_to_server(data):
    """Send data to server with error handling"""
    try:
        response = requests.post(SERVER_URL, json=data, timeout=10)
        if response.status_code == 200:
            return True, "Success"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection failed"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

def format_ct_results_for_log(ct_results):
    """Format CT results for readable logging"""
    active_cts = []
    total_power = 0
    
    for ct_num, result in ct_results.items():
        if result and result['power'] > 0:
            power = result['power']
            current = result['current']
            variation = result['variation']
            total_power += power
            active_cts.append(f"CT{ct_num}:{power:.1f}W/{current:.3f}A")
    
    if active_cts:
        return f"Total:{total_power:.1f}W | " + " | ".join(active_cts)
    else:
        return "No active loads detected"

def main():
    time_info = get_local_time_info()
    
    log_message(f"🔌 Power Monitor Starting - {LOCATION_NAME}")
    log_message("=" * 60)
    log_message(f"Device ID: {DEVICE_ID}")
    log_message(f"Location: {LOCATION_NAME}")
    log_message(f"Local Time: {time_info['local_time']}")
    log_message(f"UTC Time: {time_info['utc_time']}")
    log_message(f"Timezone: {time_info['timezone']}")
    log_message(f"Voltage: {GRID_VOLTAGE}V")
    log_message(f"CT Rating: {CT_RATING}A (all CTs)")
    log_message(f"Server: {SERVER_URL}")
    log_message("=" * 60)

    if not init_spi():
        log_message("❌ Cannot start without SPI. Check hardware connections.")
        return

    successful_readings = 0
    failed_readings = 0
    successful_uploads = 0
    failed_uploads = 0

    log_message(f"🚀 Service started - monitoring 6x{CT_RATING}A CT sensors")

    while running:
        try:
            all_ct_samples = collect_all_ct_samples(NUM_SAMPLES)
            ct_results = calculate_all_ct_power(all_ct_samples)
            
            if any(result is not None for result in ct_results.values()):
                successful_readings += 1
                
                # Create payload with proper ISO 8601 UTC timestamp
                utc_timestamp = get_utc_timestamp()
                payload = {
                    "device_id": DEVICE_ID,
                    "timestamp": utc_timestamp,  # ISO 8601 format: 2025-07-24T13:30:15.123Z
                    "location": LOCATION_NAME,
                    "timezone": DETECTED_TIMEZONE,
                    "readings": {
                        "cts": {},
                        "voltage_rms": round(GRID_VOLTAGE, 1)
                    }
                }
                
                # Add each CT's data
                for ct_num in range(1, 7):
                    result = ct_results.get(ct_num)
                    if result:
                        payload["readings"]["cts"][f"ct_{ct_num}"] = {
                            "real_power_w": round(result['power'], 1),
                            "amps": round(result['current'], 3),
                            "pf": round(result['pf'], 3)
                        }
                    else:
                        payload["readings"]["cts"][f"ct_{ct_num}"] = {
                            "real_power_w": 0.0,
                            "amps": 0.0,
                            "pf": 0.0
                        }
                
                # Send to server
                success, message = send_to_server(payload)
                
                if success:
                    successful_uploads += 1
                    status = "✅"
                else:
                    failed_uploads += 1
                    status = "❌"
                
                log_line = format_ct_results_for_log(ct_results)
                # Debug: Show timestamp format being sent (remove this line in production)
                # log_message(f"DEBUG: Sending timestamp: {utc_timestamp} (ISO 8601 UTC)")
                log_message(f"{status} {log_line} | {message}")
                
            else:
                failed_readings += 1
                log_message("❌ No valid readings from any CT sensor")
                
            time.sleep(SEND_INTERVAL)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            failed_readings += 1
            log_message(f"❌ Error: {e}")
            time.sleep(5)

    log_message("🛑 Power Monitor Service Stopped")

if __name__ == "__main__":
    main()
