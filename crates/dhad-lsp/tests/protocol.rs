//! اختبار تكامل: تشغيل خادم اللغة الحقيقي ومحاورته عبر JSON-RPC كما يفعل المحرر.

use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

struct Client {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: i64,
    notifications: Vec<Value>,
}

const URI: &str = "file:///tmp/%D8%A8%D8%B1%D9%86%D8%A7%D9%85%D8%AC.%D8%B6%D8%A7%D8%AF";

impl Client {
    fn start() -> Client {
        let mut child = Command::new(env!("CARGO_BIN_EXE_dhad-lsp"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        let pid = child.id();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(30));
            let _ = Command::new("kill").arg(pid.to_string()).status();
        });
        let stdin = child.stdin.take().unwrap();
        let stdout = BufReader::new(child.stdout.take().unwrap());
        let mut c = Client {
            child,
            stdin,
            stdout,
            next_id: 0,
            notifications: vec![],
        };
        let caps = c.request(
            "initialize",
            json!({ "capabilities": {}, "processId": null, "rootUri": null }),
        );
        assert!(caps["capabilities"]["hoverProvider"].as_bool().unwrap());
        c.notify("initialized", json!({}));
        c
    }

    fn send(&mut self, v: Value) {
        let body = v.to_string();
        write!(self.stdin, "Content-Length: {}\r\n\r\n{}", body.len(), body).unwrap();
        self.stdin.flush().unwrap();
    }

    fn read(&mut self) -> Value {
        let mut len = 0;
        loop {
            let mut line = String::new();
            let n = self.stdout.read_line(&mut line).unwrap();
            assert!(n > 0, "انتهى اتصال الخادم (انهيار أو مهلة)");
            let line = line.trim();
            if line.is_empty() {
                break;
            }
            if let Some(v) = line.strip_prefix("Content-Length: ") {
                len = v.parse().unwrap();
            }
        }
        let mut buf = vec![0; len];
        self.stdout.read_exact(&mut buf).unwrap();
        serde_json::from_slice(&buf).unwrap()
    }

    fn notify(&mut self, method: &str, params: Value) {
        self.send(json!({ "jsonrpc": "2.0", "method": method, "params": params }));
    }

    fn request(&mut self, method: &str, params: Value) -> Value {
        self.next_id += 1;
        let id = self.next_id;
        self.send(json!({ "jsonrpc": "2.0", "id": id, "method": method, "params": params }));
        loop {
            let msg = self.read();
            if msg.get("id") == Some(&json!(id)) {
                assert!(msg.get("error").is_none(), "{method}: {msg}");
                return msg["result"].clone();
            }
            self.notifications.push(msg);
        }
    }

    fn open(&mut self, text: &str) -> Vec<Value> {
        self.notify(
            "textDocument/didOpen",
            json!({ "textDocument": { "uri": URI, "languageId": "dhad", "version": 1, "text": text } }),
        );
        self.wait_diagnostics()
    }

    fn change(&mut self, text: &str, version: i64) -> Vec<Value> {
        self.notify(
            "textDocument/didChange",
            json!({ "textDocument": { "uri": URI, "version": version }, "contentChanges": [{ "text": text }] }),
        );
        self.wait_diagnostics()
    }

    fn wait_diagnostics(&mut self) -> Vec<Value> {
        loop {
            let msg = self.read();
            if msg["method"] == "textDocument/publishDiagnostics" {
                return msg["params"]["diagnostics"].as_array().unwrap().clone();
            }
        }
    }

    fn at(&mut self, method: &str, line: u32, character: u32) -> Value {
        let mut params = json!({ "textDocument": { "uri": URI }, "position": { "line": line, "character": character } });
        if method == "textDocument/references" {
            params["context"] = json!({ "includeDeclaration": true });
        }
        self.request(method, params)
    }

    fn shutdown(mut self) {
        self.request("shutdown", Value::Null);
        self.notify("exit", Value::Null);
        assert!(self.child.wait().unwrap().success());
    }
}

/// موضع (سطر، عمود UTF-16) لأول ظهور لـ `needle` في السطر المعطى.
fn pos(text: &str, line: usize, needle: &str) -> (u32, u32) {
    let l = text.lines().nth(line).unwrap();
    let byte = l.find(needle).unwrap();
    (line as u32, l[..byte].encode_utf16().count() as u32)
}

const PROGRAM: &str = "استورد رياضيات
## يحسب مربع العدد
دالة مربع(ن) {
    أرجع ن * ن
}
دع النتيجة = مربع(٣)
اطبع(النتيجة، رياضيات.جذر(النتيجة))
";

#[test]
fn full_editor_session() {
    let mut c = Client::start();

    // تشخيص: برنامج سليم بلا تشخيصات.
    assert_eq!(c.open(PROGRAM), Vec::<Value>::new());

    // تشخيص: خطأ إملائي في اسم متغير يُبلَّغ مع اقتراح، وتحذير لمتغير غير مستخدم.
    let typo = PROGRAM.replace("اطبع(النتيجة،", "اطبع(النتيجه،");
    let diags = c.change(&typo, 2);
    let err = diags
        .iter()
        .find(|d| d["code"] == "ضاد-1001")
        .expect("1001");
    assert!(err["message"].as_str().unwrap().contains("النتيجة"));
    assert_eq!(err["range"]["start"]["line"], 6);

    // إجراء سريع: استبدال بالاسم المقترح.
    let actions = c.request(
        "textDocument/codeAction",
        json!({ "textDocument": { "uri": URI }, "range": err["range"], "context": { "diagnostics": [err] } }),
    );
    let fix = &actions[0];
    assert_eq!(fix["title"], "استبدل بـ «النتيجة»");
    let new_text = &fix["edit"]["changes"][URI][0]["newText"];
    assert_eq!(new_text, "النتيجة");

    assert!(c.change(PROGRAM, 3).is_empty());

    // تلميح: دالة معرَّفة بتوثيقها.
    let (l, ch) = pos(PROGRAM, 5, "مربع");
    let h = c.at("textDocument/hover", l, ch + 1);
    let v = h["contents"]["value"].as_str().unwrap();
    assert!(
        v.contains("دالة مربع(ن)") && v.contains("يحسب مربع العدد"),
        "{v}"
    );

    // تلميح: عضو وحدة، ودالة مدمجة.
    let (l, ch) = pos(PROGRAM, 6, "جذر");
    let v = c.at("textDocument/hover", l, ch + 1)["contents"]["value"]
        .as_str()
        .unwrap()
        .to_string();
    assert!(v.contains("رياضيات.جذر"), "{v}");
    let v = c.at("textDocument/hover", 6, 1)["contents"]["value"]
        .as_str()
        .unwrap()
        .to_string();
    assert!(v.contains("دالة مدمجة"), "{v}");

    // الانتقال إلى التعريف.
    let (l, ch) = pos(PROGRAM, 6, "النتيجة");
    let def = c.at("textDocument/definition", l, ch + 2);
    assert_eq!(def["range"]["start"]["line"], 5);

    // المراجع: التعريف + استخدامان.
    let refs = c.at("textDocument/references", l, ch + 2);
    assert_eq!(refs.as_array().unwrap().len(), 3);

    // إعادة التسمية.
    let edit = c.request(
        "textDocument/rename",
        json!({ "textDocument": { "uri": URI }, "position": { "line": l, "character": ch + 2 }, "newName": "الناتج" }),
    );
    assert_eq!(edit["changes"][URI].as_array().unwrap().len(), 3);

    // رموز المستند.
    let syms = c.request(
        "textDocument/documentSymbol",
        json!({ "textDocument": { "uri": URI } }),
    );
    let names: Vec<&str> = syms
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, vec!["مربع", "النتيجة"]);

    // إكمال أعضاء الوحدة بعد النقطة.
    let doc = format!("{PROGRAM}رياضيات.");
    c.change(&doc, 4);
    let line = doc.lines().count() as u32 - 1;
    let items = c.at(
        "textDocument/completion",
        line,
        "رياضيات.".encode_utf16().count() as u32,
    );
    let labels: Vec<&str> = items
        .as_array()
        .unwrap()
        .iter()
        .map(|i| i["label"].as_str().unwrap())
        .collect();
    assert!(
        labels.contains(&"جذر") && labels.contains(&"ط"),
        "{labels:?}"
    );

    // إكمال عام: كلمات مفتاحية بمقتطفات، ودوال مدمجة، ورموز البرنامج.
    let doc = format!("{PROGRAM}م");
    c.change(&doc, 5);
    let items = c.at("textDocument/completion", 7, 1);
    let arr = items.as_array().unwrap();
    assert!(arr
        .iter()
        .any(|i| i["label"] == "مربع" && i["detail"] == "دالة مربع(ن)"));
    assert!(arr
        .iter()
        .any(|i| i["label"] == "لكل" && i["insertTextFormat"] == 2));

    // مساعدة التوقيع مع الفاصلة العربية.
    let doc = format!("{PROGRAM}تقريب(٣٫١٤١٥، ");
    c.change(&doc, 6);
    let sh = c.at(
        "textDocument/signatureHelp",
        7,
        "تقريب(٣٫١٤١٥، ".encode_utf16().count() as u32,
    );
    assert_eq!(sh["activeParameter"], 1);
    assert!(sh["signatures"][0]["label"]
        .as_str()
        .unwrap()
        .starts_with("تقريب("));

    // إصلاح الاستيراد الناقص.
    let doc = "اطبع(نصوص.اقلب(\"ضاد\"))\n";
    let diags = c.change(doc, 7);
    let actions = c.request(
        "textDocument/codeAction",
        json!({ "textDocument": { "uri": URI }, "range": diags[0]["range"], "context": { "diagnostics": diags } }),
    );
    assert_eq!(actions[0]["title"], "أضف: استورد نصوص");

    c.shutdown();
}
