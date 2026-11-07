pragma Singleton
import QtQuick
import Quickshell
// fixed values instead of Math.random() (pin.py): call site × delegate index → [0, 1), so randomly placed
// things land the same every run, whatever order bindings evaluate in
Singleton {
    function at(site, i) {
        let h = Math.imul(site, 0x9E3779B1) ^ Math.imul(i + 1, 0x85EBCA77);
        h = Math.imul(h ^ (h >>> 15), 0x2C1B3C6D); h = Math.imul(h ^ (h >>> 12), 0x297A2D39); h ^= h >>> 15;
        return (h >>> 0) / 4294967296;
    }
}
