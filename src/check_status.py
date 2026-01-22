#!/usr/bin/env python3

import subprocess
import os
from datetime import datetime
import pytz

def check_enhanced_status():
    print("🔌 Enhanced Power Monitor Status")
    print("=" * 50)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if setup is complete
    setup_complete = os.path.exists("/opt/powermonitor/.setup_complete")
    print(f"Setup Complete: {'✅ Yes' if setup_complete else '❌ No'}")
    
    if not setup_complete:
        print("Run setup with: python3 /opt/powermonitor/turnkey_setup.py")
        return
    
    # Check service status
    try:
        result = subprocess.run(['systemctl', 'is-active', 'powermonitor'], 
                              capture_output=True, text=True)
        status = result.stdout.strip()
        
        if status == 'active':
            print("Service Status: ✅ Running")
        elif status == 'inactive':
            print("Service Status: 🔴 Stopped")
        else:
            print(f"Service Status: 🟡 {status}")
    except:
        print("Service Status: ❓ Unknown")
    
    # Check enhanced config
    try:
        with open('/etc/powermonitor/config.conf', 'r') as f:
            config_lines = f.readlines()
        
        print("\nEnhanced Configuration:")
        config_data = {}
        for line in config_lines:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                config_data[key] = value
        
        # Display key info
        for key in ['DEVICE_ID', 'LOCATION_NAME', 'DETECTED_TIMEZONE', 'GRID_VOLTAGE', 'CT_RATING', 'SEND_INTERVAL']:
            if key in config_data:
                icon = {'DEVICE_ID': '📱', 'LOCATION_NAME': '📍', 'DETECTED_TIMEZONE': '🕐',
                       'GRID_VOLTAGE': '⚡', 'CT_RATING': '🔌', 'SEND_INTERVAL': '⏱️'}.get(key, '•')
                print(f"  {icon} {key}: {config_data[key]}")

        # Show local time in detected timezone
        if 'DETECTED_TIMEZONE' in config_data:
            try:
                tz = pytz.timezone(config_data['DETECTED_TIMEZONE'])
                local_time = datetime.now(tz)
                print(f"  🕐 Local Time: {local_time.strftime('%H:%M:%S %Z')}")
            except:
                pass
                
    except:
        print("Configuration: ❌ Not found")
    
    print("\nCommands:")
    print("  sudo systemctl start powermonitor         # Start service")
    print("  sudo systemctl stop powermonitor          # Stop service")
    print("  journalctl -u powermonitor -f             # View live logs")
    print("  python3 /opt/powermonitor/check_status.py # Status check")

if __name__ == "__main__":
    check_enhanced_status()
