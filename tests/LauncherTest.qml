import QtQuick
import Quickshell
import "." as Plugin

ShellRoot {
  id: test
  property int exits: 0
  property int stage: 0
  Plugin.Launcher {
    id: plugin
    shell: QtObject {
      function hide(id) {
        if (id !== "douper.underpants") console.error("BAD_ID")
        test.exits++
      }
    }
  }
  Component.onCompleted: {
    plugin.open('{"mode":"zen"}')
    plugin.close() // Cancel before Qt.callLater: must not spawn.
  }
  Timer {
    interval: 100
    repeat: true
    running: true
    onTriggered: {
      if (test.stage === 0) {
        if (plugin.requested || test.exits !== 0) console.error("BAD_CANCEL")
        plugin.open('{"mode":"zen"}')
        plugin.open('{"mode":"story"}') // Duplicate summon must not change mode.
        if (plugin.mode !== "zen") console.error("BAD_DUPLICATE")
        test.stage++
      } else if (test.stage === 1 && test.exits === 1) {
        plugin.open("not JSON")
        if (plugin.mode !== "story") console.error("BAD_FALLBACK")
        test.stage++
      } else if (test.stage === 2 && test.exits === 2) {
        plugin.open({mode: "zen"})
        test.stage++
      } else if (test.stage === 3 && test.exits === 3) {
        console.log("LAUNCHER_TEST_PASS")
        Qt.quit()
      }
    }
  }
  Timer {
    interval: 5000
    running: true
    onTriggered: { console.error("TEST_TIMEOUT"); Qt.quit() }
  }
}
