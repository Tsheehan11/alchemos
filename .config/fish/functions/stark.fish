# Old name for `alc` (the dotfiles repo moved to ~/.alchemos). Still works; says so once per call.
function stark --wraps=alc --description 'deprecated: use alc'
    echo "stark: renamed to alc (AlchemOS); running alc $argv" >&2
    alc $argv
end
