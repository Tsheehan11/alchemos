-- ── Peek (Super + D) ─────────────────────────
-- Show the desktop: every window on the active workspace goes to special:peek<id> (hidden,
-- nothing is closed), and Super + D again brings them back.
--
-- Hyprland is the state: a workspace is peeked while special:peek<id> holds windows. Lua
-- state is wiped by every config reload, and windows outlive the HUD, so nothing else
-- keeps a copy that could go stale. The HUD (quickshell/Peek.qml) follows the same
-- workspaces and calls restore() / restore_all() for the safety restores (lock, dock
-- change, a new window on a peeked workspace, start-up) and go() for the Super+Tab
-- overview, through
--   hyprctl eval 'require("stark.peek").restore_all()'
local M = {}

local PREFIX = "special:peek"

local function stash(id)
    for _, ws in ipairs(hl.get_workspaces()) do
        if ws.name == PREFIX .. id then return ws end
    end
end

local function move(win, workspace)
    hl.dispatch(hl.dsp.window.move({ window = "address:" .. win.address, workspace = workspace, follow = false }))
end

-- Bring workspace id's windows back. focus: also focus the one that had focus last (which
-- switches to that workspace); the safety restores leave your view where it is.
function M.restore(id, focus)
    local ws = stash(id)
    if not ws then return false end
    local last
    for _, win in ipairs(hl.get_workspace_windows(ws)) do
        move(win, id)
        if not last or win.focus_history_id < last.focus_history_id then last = win end
    end
    if focus and last then hl.dispatch(hl.dsp.focus({ window = "address:" .. last.address })) end
    return true
end

-- Overview pick: bring the workspace's windows back first, then go there
function M.go(id)
    M.restore(id, true)
    hl.dispatch(hl.dsp.focus({ workspace = id }))
end

function M.restore_all()
    for _, ws in ipairs(hl.get_workspaces()) do
        local id = ws.name:match("^" .. PREFIX .. "(%-?%d+)$")
        if id then M.restore(tonumber(id)) end
    end
end

function M.toggle()
    local ws = hl.get_active_workspace()
    if not ws or ws.special then return end   -- a scratchpad (music, …) is showing
    if M.restore(ws.id, true) then return end
    for _, win in ipairs(hl.get_workspace_windows(ws)) do
        move(win, PREFIX .. ws.id)
    end
end

return M
