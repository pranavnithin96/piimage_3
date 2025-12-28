#!/bin/bash
echo "🚀 PowerMonitor Complete Installation"
echo "===================================="

# Copy the enhanced setup to current directory if needed
if [ -f "src/turnkey_setup_interactive.py" ]; then
    echo "✅ turnkey_setup_interactive.py found"
    sudo cp src/turnkey_setup_interactive.py enhanced_turnkey_setup.py
else
    echo "❌ turnkey_setup_interactive.py not found!"
    echo "Please check that you have the complete repository."
    exit 1
fi

echo "🚀 Enhanced Power Monitor Deployment"
echo "===================================="

# Step 1: Install dependencies
echo "📦 Installing required dependencies..."
sudo apt update
sudo apt install -y python3-pip python3-requests
pip3 install --break-system-packages pytz requests spidev || sudo apt install -y python3-pytz python3-spidev

# Step 2: Stop any existing services
echo "🛑 Stopping existing services..."
sudo systemctl stop powermonitor 2>/dev/null || true
sudo systemctl disable powermonitor 2>/dev/null || true

# Step 2b: Install systemd service file
echo "📋 Installing systemd service file..."
if [ -f "services/powermonitor.service" ]; then
    sudo cp services/powermonitor.service /etc/systemd/system/
    sudo systemctl daemon-reload
    echo "✅ Service file installed to /etc/systemd/system/"
else
    echo "⚠️  Warning: services/powermonitor.service not found"
    echo "   Service will need to be configured manually"
fi

# Step 3: Use turnkey_setup_interactive.py as enhanced setup
if [ -f "src/turnkey_setup_interactive.py" ]; then
    echo "✅ Using turnkey_setup_interactive.py as enhanced setup"
    enhanced_setup="src/turnkey_setup_interactive.py"
elif [ -f "enhanced_turnkey_setup.py" ]; then
    echo "✅ Found enhanced_turnkey_setup.py"
    enhanced_setup="enhanced_turnkey_setup.py"
else
    echo "❌ No setup script found!"
    exit 1
fi

# Step 4: Install the enhanced setup system
echo "📄 Installing enhanced setup system..."
sudo mkdir -p /opt/powermonitor
sudo mkdir -p /etc/powermonitor
sudo mkdir -p /var/log/powermonitor

# Copy the enhanced setup script
sudo cp "$enhanced_setup" /opt/powermonitor/turnkey_setup.py
sudo chmod +x /opt/powermonitor/turnkey_setup.py
sudo chown pi:pi /opt/powermonitor/turnkey_setup.py
## adding to copy the config file 
sudo cp config/config.conf /etc/powermonitor/

# Step 5: Install main monitoring script
echo "📦 Installing monitoring script..."
sudo cp src/pi_monitor_script.py /opt/powermonitor/pi_monitor_script.py
sudo chmod +x /opt/powermonitor/pi_monitor_script.py
sudo chown pi:pi /opt/powermonitor/pi_monitor_script.py

# Step 5b: Update the auto-setup script for SSH login
echo "🔑 Updating auto-setup for SSH login..."
sudo cp scripts/auto_setup.sh /opt/powermonitor/auto_setup.sh
echo "🔧 Installing interactive setup script..."
sudo cp src/turnkey_setup_interactive.py /opt/powermonitor/turnkey_setup_interactive.py
sudo chmod +x /opt/powermonitor/turnkey_setup_interactive.py

# Note: Lines 48-96 from original deploy_enhanced.sh were malformed and have been removed
# The auto_setup.sh is correctly copied from scripts folder above

sudo chmod +x /opt/powermonitor/auto_setup.sh

# Step 6: Update bashrc if needed
if ! grep -q "auto_setup.sh" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# Enhanced Power Monitor Auto-Setup" >> ~/.bashrc
    echo "/opt/powermonitor/auto_setup.sh" >> ~/.bashrc
    echo "✅ Added enhanced auto-setup to SSH login"
else
    echo "ℹ️  Auto-setup already configured in bashrc"
fi

# Step 7: Create enhanced status check script
echo "🔧 Creating enhanced status check script..."
sudo tee /opt/powermonitor/check_status.py > /dev/null << 'EOF'
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
EOF

sudo chmod +x /opt/powermonitor/check_status.py

# Step 8: Set permissions
sudo chown -R pi:pi /opt/powermonitor
sudo chown -R pi:pi /var/log/powermonitor
sudo chown -R pi:pi /etc/powermonitor
sudo chmod 755 /etc/powermonitor

# Step 10: Enable SPI
echo "🔌 Enabling SPI interface..."
sudo raspi-config nonint do_spi 0

# Step 11: Check if config exists and start service
echo "🚀 Starting PowerMonitor service..."
if [ -f "/etc/powermonitor/config.conf" ]; then
    echo "✅ Configuration found, starting service..."
    sudo systemctl start powermonitor
    sudo systemctl enable powermonitor
    echo "✅ PowerMonitor service started and enabled!"
    echo ""
    echo "📊 Service status:"
    sudo systemctl status powermonitor --no-pager
else
    echo "⚠️  No configuration found yet"
    echo "   Run: python3 /opt/powermonitor/pi_monitor_script.py"
    echo "   to configure the system first"
fi

echo ""
echo "✅ Installation complete!"
echo "🔌 Your PowerMonitor system is now ready!"
echo ""
echo "📋 What was installed:"
echo "  • 6-CT sensor monitoring system"
echo "  • Interactive configuration wizard"
echo "  • Real-time power monitoring engine"
echo "  • Background data buffering"
echo ""
echo "📊 Useful commands:"
echo "  python3 /opt/powermonitor/check_status.py    # Check status"
echo "  sudo systemctl status powermonitor           # Service status"
echo "  journalctl -u powermonitor -f                # View logs"
echo ""
