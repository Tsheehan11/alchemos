#!/usr/bin/env fish
# STARK OS lock screen + fingerprint fix. Run once: fish ~/.config/hypr/fprint-install.fish
# Installs the hyprlock PAM stack and the suspend hooks, unwedges the Elan reader now.
set -l elan 04f3:0c88
set -l sys ~/.config/hypr/system

echo ":: installing /etc/pam.d/hyprlock and the suspend hooks (needs sudo)"
sudo install -m 644 -b --suffix=.orig $sys/hyprlock.pam /etc/pam.d/hyprlock; or exit 1
sudo install -m 755 $sys/stark-fprintd-sleep /usr/lib/systemd/system-sleep/stark-fprintd; or exit 1
sudo install -m 755 $sys/stark-thaw-sleep /usr/lib/systemd/system-sleep/stark-thaw; or exit 1

echo ":: faillock: lock after 5 wrong passwords (was 3), unlock_time stays 10 min"
set -l fl /etc/security/faillock.conf
# Keep the first original; re-runs don't overwrite it. Drop any active deny line, then
# put deny = 5 right under the stock "# deny = 3" comment.
sudo cp -n $fl $fl.orig; or exit 1
sudo sed -i -E '/^[[:space:]]*deny[[:space:]]*=/d; s/^# deny = 3$/&\ndeny = 5/' $fl; or exit 1
if not grep -qx 'deny = 5' $fl
    echo "!! couldn't set deny = 5 in $fl (no '# deny = 3' line); add it by hand"
end

# The old hook masked fprintd before sleep; make sure no mask is left behind.
sudo systemctl unmask --runtime --quiet fprintd.service
faillock --user (id -un) --reset

echo ":: recovering the reader"
# A wedged fprintd ignores SIGTERM, so kill it outright. Nothing may be using it now:
# don't run this while the lock screen is up.
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
