set shell := ["bash", "-cu"]

dev:
  ./devinit.sh

stop:
  tmux kill-session -t twitter-auto-poster

logs:
  tail -F twitter-auto-poster.log
