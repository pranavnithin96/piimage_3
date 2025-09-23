#!/bin/bash
echo "🚀 PowerMonitor Complete Installation"
echo "===================================="

# Copy the enhanced setup to current directory if needed
if [ -f "src/turnkey_setup_interactive.py" ]; then
    echo "✅ turnkey_setup_interactive.py found"
    cp src/turnkey_setup_interactive.py enhanced_turnkey_setup.py
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
pip3 install pytz requests spidev

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

# Step 3: Check if enhanced setup script exists
if [ ! -f "enhanced_turnkey_setup.py" ]; then
    echo "❌ enhanced_turnkey_setup.py not found!"
    echo ""
    echo "Please save the enhanced setup script as 'enhanced_turnkey_setup.py' first:"
    echo "1. Copy the enhanced turnkey setup code from Claude"
    echo "2. Save it as: enhanced_turnkey_setup.py"
    echo "3. Run this deployment script again"
    exit 1
fi

echo "✅ Found enhanced_turnkey_setup.py"

# Step 4: Install the enhanced setup system
echo "📄 Installing enhanced setup system..."
sudo mkdir -p /opt/powermonitor
sudo mkdir -p /etc/powermonitor
sudo mkdir -p /var/log/powermonitor

# Copy the enhanced setup script
sudo cp enhanced_turnkey_setup.py /opt/powermonitor/turnkey_setup.py
sudo chmod +x /opt/powermonitor/turnkey_setup.py
sudo chown pi:pi /opt/powermonitor/turnkey_setup.py

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
        for key in ['DEVICE_ID', 'LOCATION_NAME', 'TIMEZONE', 'VOLTAGE', 'CT_RATING']:
            if key in config_data:
                icon = {'DEVICE_ID': '📱', 'LOCATION_NAME': '📍', 'TIMEZONE': '🕐', 
                       'VOLTAGE': '⚡', 'CT_RATING': '🔌'}.get(key, '•')
                print(f"  {icon} {key}: {config_data[key]}")
        
        # Show local time in detected timezone
        if 'TIMEZONE' in config_data:
            try:
                tz = pytz.timezone(config_data['TIMEZONE'])
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

# Step 8: Create enhanced SD card preparation script
echo "💾 Creating enhanced SD card preparation script..."
sudo tee /opt/powermonitor/prepare_sd_card.sh > /dev/null << 'EOF'
#!/bin/bash

# Enhanced SD Card Preparation Script
echo "🔌 Preparing Enhanced SD Card for Deployment"
echo "============================================"

# Remove setup complete marker
if [ -f "/opt/powermonitor/.setup_complete" ]; then
    sudo rm /opt/powermonitor/.setup_complete
    echo "✅ Removed setup completion marker"
fi

# Remove any existing config
if [ -f "/etc/powermonitor/config.conf" ]; then
    sudo rm /etc/powermonitor/config.conf
    echo "✅ Removed existing configuration"
fi

# Stop and disable service if running
sudo systemctl stop powermonitor 2>/dev/null
sudo systemctl disable powermonitor 2>/dev/null
echo "✅ Stopped and disabled service"

# Remove any existing power monitor script
if [ -f "/opt/powermonitor/pi_monitor_script.py" ]; then
    sudo rm /opt/powermonitor/pi_monitor_script.py
    echo "✅ Removed existing monitor script"
fi

# Clean logs
sudo rm -f /var/log/powermonitor/*
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s
echo "✅ Cleared log files"

# Remove SSH host keys (will be regenerated on first boot)
sudo rm -f /etc/ssh/ssh_host_*
echo "✅ Removed SSH host keys (will regenerate)"

# Clear bash history
history -c
> ~/.bash_history
echo "✅ Cleared bash history"

# Remove any temporary files
sudo rm -f /tmp/powermonitor*
echo "✅ Cleaned temporary files"

echo ""
echo "🎯 Enhanced SD Card is ready for imaging!"
echo ""
echo "Features in this image:"
echo "  ✅ Custom device naming"
echo "  ✅ Automatic timezone detection" 
echo "  ✅ 6-CT sensor monitoring"
echo "  ✅ ISO 8601 UTC timestamps"
echo "  ✅ Professional setup wizard"
echo ""
echo "Next steps:"
echo "1. Shutdown: sudo shutdown -h now"
echo "2. Create SD card image"
echo "3. Flash to new cards for deployment"
echo ""
echo "Deployment experience:"
echo "  • Flash image → Boot Pi → SSH in"
echo "  • Setup wizard runs automatically"
echo "  • User enters device name & location"
echo "  • Timezone detected automatically"
echo "  • Monitoring starts immediately"
echo ""
EOF

sudo chmod +x /opt/powermonitor/prepare_sd_card.sh

# Step 9: Set permissions
sudo chown -R pi:pi /opt/powermonitor
sudo chown -R pi:pi /var/log/powermonitor
sudo chown -R pi:pi /etc/powermonitor
sudo chmod 755 /etc/powermonitor

# Step 10: Enable SPI
echo "🔌 Enabling SPI interface..."
sudo raspi-config nonint do_spi 0

echo ""
echo "✅ Enhanced Power Monitor Deployment Complete!"
echo ""
echo "🎯 What's installed:"
echo "   • Enhanced setup wizard with custom device naming"
echo "   • Automatic timezone detection and UTC timestamps"
echo "   • Professional SSH login experience"
echo "   • 6-CT sensor monitoring system"
echo "   • ISO 8601 timestamp formatting"
echo ""
echo "🧪 Testing:"
echo "   python3 /opt/powermonitor/turnkey_setup.py"
echo ""
echo "📊 Status check:"
echo "   python3 /opt/powermonitor/check_status.py"
echo ""
echo "💾 Prepare for SD card imaging:"
echo "   /opt/powermonitor/prepare_sd_card.sh"
echo ""
echo "🚀 Ready for professional deployment!"
echo ""

echo ""
echo "✅ Installation complete!"
echo "🔌 Your PowerMonitor system is now ready!"
echo ""
echo "📋 What was installed:"
echo "  • Interactive setup framework"
echo "  • Professional SSH interface"
echo "  • Real-time monitoring engine"
echo "  • Complete configuration system"
echo ""
echo "🚀 Next: SSH into this Pi and the setup wizard will run automatically!"