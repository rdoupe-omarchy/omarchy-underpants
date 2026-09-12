import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root
  property var shell: null
  property var manifest: null
  property string mode: "story"
  property bool requested: false

  // Allowlist only. clearEnvironment drops PYTHON*, LD_*, and ambient PATH
  // before /usr/bin/python3 starts. PATH is fixed for descendant resolvers.
  function launchEnvironment() {
    var env = {
      PATH: "/usr/bin:/bin",
      HOME: Quickshell.env("HOME") || "",
      LANG: Quickshell.env("LANG") || "C.UTF-8"
    }
    var pass = [
      "USER", "LOGNAME",
      "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_SESSION_ID",
      "WAYLAND_DISPLAY", "DISPLAY",
      "HYPRLAND_INSTANCE_SIGNATURE", "OMARCHY_PATH",
      "LC_ALL", "LC_CTYPE"
    ]
    for (var i = 0; i < pass.length; i++) {
      var value = Quickshell.env(pass[i])
      if (value !== undefined && value !== null && String(value) !== "")
        env[pass[i]] = String(value)
    }
    return env
  }

  function open(payload) {
    if (requested) return
    var options = payload
    if (typeof payload === "string") {
      try { options = JSON.parse(payload) } catch (e) { options = null }
    }
    mode = options && options.mode === "zen" ? "zen" : "story"
    requested = true
    Qt.callLater(function() {
      if (root.requested) {
        launcher.environment = root.launchEnvironment()
        launcher.running = true
      }
    })
  }
  function close() {
    requested = false
    if (launcher.running) launcher.signal(15)
  }

  Process {
    id: launcher
    command: ["/usr/bin/python3", decodeURIComponent(Qt.resolvedUrl("screensaver.py").toString().replace(/^file:\/\//, "")), "--launch", "--mode", root.mode]
    clearEnvironment: true
    environment: ({})
    onRunningChanged: {
      if (running || !root.requested) return
      root.requested = false
      if (root.shell) root.shell.hide("douper.underpants")
    }
  }
}
