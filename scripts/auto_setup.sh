#!/bin/bash

# Enhanced Auto-setup - Always accessible
echo ""
echo "🔌 Power Monitor Manager"
echo "========================"

# Show WiFi status
current_ssid=$(iwgetid -r 2>/dev/null)
if [ -n "$current_ssid" ]; then
    echo "📶 WiFi: $current_ssid"
else
    echo "📶 WiFi: Not connected"
fi

# Check if configuration exists
if [ -f "/etc/powermonitor/config.conf" ]; then
    # Show current device info
    DEVICE_ID=$(grep "DEVICE_ID=" /etc/powermonitor/config.conf 2>/dev/null | cut -d'=' -f2)
    LOCATION=$(grep "LOCATION_NAME=" /etc/powermonitor/config.conf 2>/dev/null | cut -d'=' -f2)

    echo "📱 Device: $DEVICE_ID"
    echo "📍 Location: $LOCATION"

    # Check service status
    if systemctl is-active --quiet powermonitor 2>/dev/null; then
        echo "✅ Service: Running"
    else
        echo "❌ Service: Stopped"
    fi

    echo ""
    echo "Options:"
    echo "  [ENTER] - Open configuration wizard"
    echo "  [w] - WiFi setup"
    echo "  [s] - Show service logs"
    echo "  [r] - Restart service"
    echo "  [q] - Skip"

    read -n 1 -r -p "Choice: " choice
    echo ""

    case $choice in
        w|W)
            if [ -f "/opt/powermonitor/wifi_setup.sh" ]; then
                bash /opt/powermonitor/wifi_setup.sh
            else
                echo "❌ WiFi setup script not found"
            fi
            ;;
        s|S)
            echo "📊 Showing service logs (Ctrl+C to exit)..."
            journalctl -u powermonitor -f
            ;;
        r|R)
            echo "🔄 Restarting service..."
            sudo systemctl restart powermonitor
            sleep 2
            if systemctl is-active --quiet powermonitor 2>/dev/null; then
                echo "✅ Service restarted successfully"
            else
                echo "❌ Service failed to start"
            fi
            ;;
        q|Q)
            echo "Skipping."
            ;;
        *)
            echo "Opening configuration wizard..."
            python3 /opt/powermonitor/turnkey_setup_interactive.py
            ;;
    esac
else
    echo "🆕 No configuration found"
    echo ""

    read -p "Do you need help connecting to WiFi? (y/N): " need_wifi

    if [[ "$need_wifi" =~ ^[Yy]$ ]]; then
        if [ -f "/opt/powermonitor/wifi_setup.sh" ]; then
            bash /opt/powermonitor/wifi_setup.sh
        else
            echo "❌ WiFi setup script not found"
        fi
        echo ""
    fi

    echo "Starting configuration wizard..."
    python3 /opt/powermonitor/turnkey_setup_interactive.py
fi

echo ""
