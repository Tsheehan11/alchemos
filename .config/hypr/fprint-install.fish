#!/usr/bin/env fish
# STARK OS fingerprint fix. Run once: fish ~/.config/hypr/fprint-install.fish
# Unwedges the Elan reader now and installs the suspend hook that keeps it working.
set -l elan 04f3:0c88
set -l hook ~/.config/hypr/system/stark-fprintd-sleep

echo ":: installing suspend hook (needs sudo)"
sudo install -m 755 $hook /usr/lib/systemd/system-sleep/stark-fprintd; or exit 1

echo ":: recovering the reader"
# A wedged fprintd ignores SIGTERM, so kill it outright.
sudo systemctl kill --signal=SIGKILL fprintd.service 2>/dev/null
sudo systemctl stop fprintd.service
sudo systemctl reset-failed fprintd.service 2>/dev/null
sudo usbreset $elan
sleep 2
set -l since (date '+%Y-%m-%d %H:%M:%S')
sudo systemctl start fprintd.service
sleep 3

if journalctl -u fprintd --since "$since" --no-pager | grep -q 'machine != NULL'
    echo ":: usbreset wasn't enough, re-authorizing the USB device"
    sudo systemctl stop fprintd.service
    for d in /sys/bus/usb/devices/*
        if test -f $d/idVendor; and test (cat $d/idVendor):(cat $d/idProduct) = $elan
            echo 0 | sudo tee $d/authorized >/dev/null
            sleep 1
            echo 1 | sudo tee $d/authorized >/dev/null
        end
    end
    sleep 2
    sudo systemctl start fprintd.service
    sleep 3
end

echo ":: fprintd log since recovery:"
journalctl -u fprintd --since "$since" --no-pager -o short-precise | tail -n 5
echo ":: touch the sensor"
fprintd-verify
