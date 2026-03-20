#!/usr/bin/env bash

set -Eeuo pipefail

readonly SESSION_NAME="twitter-auto-poster"
readonly ROOT_DIR="${HOME}/code/twitter-auto-poster"

if [ ! -d "${ROOT_DIR}" ]; then
  echo "エラー: ~/code/twitter-auto-poster が存在しません" >&2
  exit 1
fi

cd "${ROOT_DIR}"

export LESS="-R"
export EDITOR=nano
export TERM=xterm-256color

# ===== Robust SSH Agent Auto Start =====
if ! ssh-add -l >/dev/null 2>&1; then
  echo "[devinit] starting new ssh-agent..."
  eval "$(ssh-agent -s)" >/dev/null
  ssh-add ~/.ssh/id_ed25519 >/dev/null 2>&1 || true
fi

echo "Copilot CLI をスマホ表示向けモードで起動しています"

readonly LOG_FILE="${ROOT_DIR}/twitter-auto-poster.log"

die() {
  echo "devinit.sh: $*" >&2
  exit 1
}

escape() {
  printf '%q' "$1"
}

attach_or_switch() {
  if [[ -n "${TMUX:-}" ]]; then
    exec tmux switch-client -t "${SESSION_NAME}"
  fi
  exec tmux attach-session -t "${SESSION_NAME}"
}

session_is_healthy() {
  local pane_count

  window_name="$(tmux display-message -p -t ${SESSION_NAME}:0 '#W')"
  [[ "${window_name}" == "dev" ]] || return 1

  pane_count="$(tmux list-panes -t "${SESSION_NAME}:0" 2>/dev/null | wc -l | tr -d ' ')"
  [[ "${pane_count}" -eq 3 ]] || return 1

  titles="$(tmux list-panes -t "${SESSION_NAME}:0" -F '#{pane_title}' 2>/dev/null)"
  for expected_title in copilot logs git; do
    grep -qx "${expected_title}" <<<"${titles}" || return 1
  done
}

validate_paths() {
  [[ -d "${ROOT_DIR}" ]] || die "root directory not found: ${ROOT_DIR}"
  [[ -d "${ROOT_DIR}/scripts" ]] || die "scripts directory not found"
  [[ -d "${ROOT_DIR}/config" ]] || die "config directory not found"
}

create_layout() {
  tmux new-session -d -s "${SESSION_NAME}" -n dev -c "${ROOT_DIR}"

  tmux set-option -g mouse on
  tmux set-option -g aggressive-resize on
  tmux set-option -g history-limit 50000
  tmux set-option -g remain-on-exit on

  # 3ペイン構成: copilot(メイン) | logs | git
  tmux split-window -h -t "${SESSION_NAME}:0.0" -c "${ROOT_DIR}"
  tmux split-window -v -t "${SESSION_NAME}:0.1" -c "${ROOT_DIR}"

  tmux setw -t "${SESSION_NAME}:0" pane-border-status top
  tmux select-pane -t "${SESSION_NAME}:0.0" -T copilot
  tmux select-pane -t "${SESSION_NAME}:0.1" -T logs
  tmux select-pane -t "${SESSION_NAME}:0.2" -T git

  tmux select-pane -t "${SESSION_NAME}:0.0"
}

start_commands() {
  local copilot_cmd logs_cmd git_cmd

  gh auth status >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol ssh --web

  copilot_cmd="cd $(escape "${ROOT_DIR}") && copilot --yolo --add-github-mcp-toolset all --add-dir ~/code/twitter-auto-poster"
  logs_cmd="cd ${ROOT_DIR} && touch $(escape "${LOG_FILE}") && tail -F $(escape "${LOG_FILE}")"
  git_cmd="cd ${ROOT_DIR} && echo 'Launching lazygit...' && lazygit"

  tmux send-keys -t "${SESSION_NAME}:0.0" "${copilot_cmd}" C-m
  tmux send-keys -t "${SESSION_NAME}:0.1" "${logs_cmd}" C-m
  tmux send-keys -t "${SESSION_NAME}:0.2" "${git_cmd}" C-m

  # Copilot CLI 起動を少し待ってからペインを拡大
  sleep 2
  tmux select-pane -t "${SESSION_NAME}:0.0"
  tmux resize-pane -Z -t "${SESSION_NAME}:0.0"
  sleep 1
  tmux send-keys -t "${SESSION_NAME}:0.0" C-t
}

main() {
  local current_tmux_session=""

  command -v tmux >/dev/null 2>&1 || die "tmux is not installed."
  command -v lazygit >/dev/null 2>&1 || die "lazygit is not installed."

  if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    if session_is_healthy; then
      attach_or_switch
    fi

    if [[ -n "${TMUX:-}" ]]; then
      current_tmux_session="$(tmux display-message -p '#S' 2>/dev/null || true)"
      [[ "${current_tmux_session}" != "${SESSION_NAME}" ]] || die "既存セッションが不健全です。デタッチ後に再実行してください。"
    fi

    echo "既存 tmux セッション(${SESSION_NAME}) が不完全なため再作成します"
    tmux kill-session -t "${SESSION_NAME}"
  fi

  validate_paths
  touch "${LOG_FILE}"
  create_layout
  start_commands
  attach_or_switch
}

main "$@"
