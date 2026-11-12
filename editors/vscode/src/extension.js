// إضافة VS Code للغة ضاد: تشغّل خادم اللغة dhad-lsp وتضيف أوامر التشغيل والاختبار والشرح.
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

/** @type {LanguageClient | undefined} */
let client;

function config() {
  return vscode.workspace.getConfiguration("dhad");
}

async function startClient(context) {
  const command = config().get("serverPath") || "dhad-lsp";
  client = new LanguageClient(
    "dhad",
    "ضاد",
    { run: { command, transport: TransportKind.stdio }, debug: { command, transport: TransportKind.stdio } },
    {
      documentSelector: [{ language: "dhad" }],
      outputChannelName: "ضاد — خادم اللغة",
    },
  );
  try {
    await client.start();
  } catch (err) {
    const choice = await vscode.window.showErrorMessage(
      `تعذّر تشغيل خادم لغة ضاد (${command}). ثبّته بـ: cargo install --path crates/dhad-lsp`,
      "فتح الإعدادات",
    );
    if (choice) vscode.commands.executeCommand("workbench.action.openSettings", "dhad.serverPath");
  }
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function shellQuote(s) {
  return `'${String(s).replace(/'/g, `'\\''`)}'`;
}

function runInTerminal(subcommand) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "dhad") {
    vscode.window.showWarningMessage("افتح ملف ضاد أولًا.");
    return;
  }
  editor.document.save().then(() => {
    const cli = config().get("cliPath") || "dhad";
    const digits = config().get("easternDigits") ? " --أرقام-شرقية" : "";
    let term = vscode.window.terminals.find((t) => t.name === "ضاد");
    if (!term) term = vscode.window.createTerminal({ name: "ضاد" });
    term.show(true);
    term.sendText(`${shellQuote(cli)} ${subcommand}${digits} ${shellQuote(editor.document.uri.fsPath)}`);
  });
}

async function explain() {
  const code = await vscode.window.showInputBox({
    prompt: "رقم كود الخطأ",
    placeHolder: "مثال: 1003 أو ١٠٠٣",
  });
  if (!code) return;
  const cli = config().get("cliPath") || "dhad";
  const { execFile } = require("node:child_process");
  execFile(cli, ["شرح", code], (err, stdout, stderr) => {
    if (err && !stdout) {
      vscode.window.showErrorMessage(stderr || String(err));
      return;
    }
    vscode.workspace
      .openTextDocument({ content: stdout, language: "markdown" })
      .then((doc) => vscode.window.showTextDocument(doc, { preview: true }));
  });
}

async function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("dhad.run", () => runInTerminal("شغّل")),
    vscode.commands.registerCommand("dhad.test", () => runInTerminal("اختبر")),
    vscode.commands.registerCommand("dhad.explain", explain),
    vscode.commands.registerCommand("dhad.restartServer", async () => {
      if (client) await client.stop();
      await startClient(context);
    }),
  );
  await startClient(context);
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
