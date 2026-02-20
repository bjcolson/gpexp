#!/usr/bin/env bash
# Toggle GitHub repo visibility between private and public

current=$(gh repo view --json visibility -q .visibility)
if [ "$current" = "PRIVATE" ]; then
    gh repo edit --visibility public --accept-visibility-change-consequences
    echo "Switched to public"
else
    gh repo edit --visibility private --accept-visibility-change-consequences
    echo "Switched to private"
fi
