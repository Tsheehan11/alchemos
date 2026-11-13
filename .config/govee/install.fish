#!/usr/bin/env fish
# AlchemOS ambient lights installer. Run once: fish ~/.config/govee/install.fish
set -l dir ~/.config/govee
set -l bin ~/.local/bin/alchemos-govee

echo ":: linking alchemos-govee"
chmod +x $dir/alchemos-govee.py
mkdir -p ~/.local/bin
ln -sf $dir/alchemos-govee.py $bin

echo ":: saving strip IP"
$bin setup; or exit 1

if not command -q cava
    echo ":: installing cava (music sync)"
    sudo pacman -S --needed --noconfirm cava
end

echo ":: installing boot/shutdown service (needs sudo)"
set -l u (id -un)
sed -e "s|@USER@|$u|g" -e "s|@HOME@|$HOME|g" $dir/system/alchemos-govee-power.service \
    | sudo tee /etc/systemd/system/alchemos-govee-power.service >/dev/null
# the pre-AlchemOS unit, if this machine still has it
if test -e /etc/systemd/system/stark-govee-power.service
    sudo systemctl disable stark-govee-power.service
    sudo rm -f /etc/systemd/system/stark-govee-power.service
end
# suspend/resume (the dim glow before sleep) is handled by the daemon through a logind sleep
# inhibitor; the old system-sleep hook only ever logged "strip not reachable" (Wi-Fi already down)
sudo rm -f /usr/lib/systemd/system-sleep/alchemos-govee /usr/lib/systemd/system-sleep/stark-govee
sudo systemctl daemon-reload
sudo systemctl enable --now alchemos-govee-power.service   # plays the boot animation now as a test

echo ":: adding daemon to Hyprland autostart"
set -l hc ~/.config/hypr/alchemos/autostart.lua
if not grep -q 'alchemos-govee daemon' $hc
    printf '\n-- AlchemOS ambient lights\nhl.on("hyprland.start", function() hl.exec_cmd("~/.local/bin/alchemos-govee daemon") end)\n' >> $hc
end

echo ":: starting daemon"
pkill -f '[a]lchemos-govee daemon'; pkill -f '[s]tark-govee daemon'
sleep 4   # let the boot animation finish first
hyprctl dispatch "hl.dsp.exec_cmd(\"$bin daemon\")" >/dev/null

echo ":: done. Try: alchemos-govee status"
