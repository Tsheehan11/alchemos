#!/usr/bin/env fish
# STARK OS ambient lights installer. Run once: fish ~/.config/govee/install.fish
set -l dir ~/.config/govee
set -l bin ~/.local/bin/stark-govee

echo ":: linking stark-govee"
chmod +x $dir/stark-govee.py
mkdir -p ~/.local/bin
ln -sf $dir/stark-govee.py $bin

echo ":: saving strip IP"
$bin setup; or exit 1

if not command -q cava
    echo ":: installing cava (music sync)"
    sudo pacman -S --needed --noconfirm cava
end

echo ":: installing boot/shutdown service (needs sudo)"
set -l u (id -un)
sed -e "s|@USER@|$u|g" -e "s|@HOME@|$HOME|g" $dir/system/stark-govee-power.service \
    | sudo tee /etc/systemd/system/stark-govee-power.service >/dev/null
# suspend/resume is handled by the daemon through a logind sleep inhibitor now
sudo rm -f /usr/lib/systemd/system-sleep/stark-govee
sudo systemctl daemon-reload
sudo systemctl enable --now stark-govee-power.service   # plays the boot animation now as a test

echo ":: adding daemon to Hyprland autostart"
set -l hc ~/.config/hypr/hyprland.conf
if not grep -q 'stark-govee daemon' $hc
    printf '\n# STARK OS ambient lights\nexec-once = ~/.local/bin/stark-govee daemon\n' >> $hc
end

echo ":: starting daemon"
pkill -f '[s]tark-govee daemon'
sleep 4   # let the boot animation finish first
hyprctl dispatch exec "$bin daemon" >/dev/null

echo ":: done. Try: stark-govee status"
