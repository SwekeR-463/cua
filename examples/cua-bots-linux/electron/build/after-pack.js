const fs = require('node:fs')
const path = require('node:path')

exports.default = async function afterPack(context) {
  const executable = path.join(
    context.appOutDir,
    'resources',
    'server',
    'cua-bots-server',
    'cua-bots-server',
  )
  if (fs.existsSync(executable)) fs.chmodSync(executable, 0o755)
  const sandbox = path.join(context.appOutDir, 'chrome-sandbox')
  if (fs.existsSync(sandbox)) fs.chmodSync(sandbox, 0o4755)
}
