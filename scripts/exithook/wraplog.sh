#!/system/bin/sh
# wraplog.sh — the wrap.<pkg>[*] property value for the exithook evidence run.
# The zygote execs THIS script (same pid chain), it logs the invocation
# (proving the wrap property fired for that process name + showing the exact
# argv AMS/Zygote hands over), then execs the real seccomp wrapper.
# NOTE: the log file is pre-created by CI with 0666 — the wrapped process
# runs as the APP uid and /data/local/tmp is not app-writable by default.
LOG=/data/local/tmp/wraplog.txt
{ echo "wrap enter pid=$$ args=[$*]"; } >> "$LOG" 2>/dev/null
exec /data/local/tmp/wrap282 "$@"
