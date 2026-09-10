import QtQuick
import Quickshell.Io

Item {
  id: root
  property var shell: null
  property var manifest: null
  property string mode: "story"
  property bool requested: false

  function open(payload) {
    if (requested) return
    var options = payload
    if (typeof payload === "string") {
      try { options = JSON.parse(payload) } catch (e) { options = null }
    }
    mode = options && options.mode === "zen" ? "zen" : "story"
    requested = true
    Qt.callLater(function() { if (root.requested) launcher.running = true })
  }
  function close() {
    requested = false
    if (launcher.running) launcher.signal(15)
  }

  Process {
    id: launcher
    command: ["python3", decodeURIComponent(Qt.resolvedUrl("screensaver.py").toString().replace(/^file:\/\//, "")), "--launch", "--mode", root.mode]
    onRunningChanged: {
      if (running || !root.requested) return
      root.requested = false
      if (root.shell) root.shell.hide("douper.underpants")
    }
  }
}
