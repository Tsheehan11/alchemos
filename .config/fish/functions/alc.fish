function alc --wraps='git --git-dir=$HOME/.alchemos --work-tree=$HOME' --description 'AlchemOS dotfiles (bare repo ~/.alchemos)'
    git --git-dir=$HOME/.alchemos --work-tree=$HOME $argv
end
