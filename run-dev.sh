while true; do
  change=$(inotifywait -e close_write,moved_to,create .)
  change=${change#./ * }
  if [ "$change" = "powercisco.py" ]; then python3.4 ./powercisco.py $@; fi
done
