# uwcs: open VS Code on the UWaterloo CS student servers (Remote-SSH).
#   uwcs              → uwcs (linux.student.cs.uwaterloo.ca, load-balanced), home folder
#   uwcs 004          → uwcs-004 (ubuntu2404-004), home folder
#   uwcs 004 ~/cs136  → that host, that folder
# Host aliases live in ~/.ssh/config. Also on the radial launcher (UW CS).
function uwcs --description 'Open VS Code on the UWaterloo CS servers'
    set -l host uwcs
    if set -q argv[1]; and test -n "$argv[1]"
        set host uwcs-(string replace -r '^uwcs-?' '' -- $argv[1])
    end

    # Ask the server for the folder: ~ → $HOME. Uses (or opens) the shared
    # ControlMaster connection, so VS Code's own login after this is instant.
    set -l want '~'
    set -q argv[2]; and set want $argv[2]
    set -l err (mktemp)
    set -l dir (ssh -o BatchMode=yes $host "cd $want && pwd" 2>$err)
    if test $status -ne 0 -o -z "$dir"
        # "UNKNOWN port 65535" = stark-uwcs-proxy couldn't reach the host and has
        # already said so (terminal or window); anything else, show ssh's error
        if not string match -q '*UNKNOWN port 65535*' -- (cat $err)
            string replace -a \r '' -- (cat $err) | string match -v -r '^\s*$' > $err.msg
            test -s $err.msg; or echo "ssh $host failed" > $err.msg
            if isatty stdout
                cat $err.msg >&2
            else
                stark-uwcs-proxy --show $err.msg   # launched from the HUD: small window
            end
            rm -f $err.msg
        end
        rm -f $err
        return 1
    end
    rm -f $err
    code --remote ssh-remote+$host $dir
end
