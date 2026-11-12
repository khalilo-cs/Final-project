//! خادم اللغة (LSP) للغة ضاد.
//!
//! يعمل عبر stdio بأي محرر يدعم البروتوكول (VS Code، Neovim، Emacs، Helix...).
//! كل تحليل مصدره `dhad-analysis` (المحلل المرجعي نفسه)، فما يراه المحرر هو
//! بالضبط ما سيقوله المترجم.

mod text;

use dhad_analysis::{analyze, catalog, Analysis, SymbolKind};
use dhad_diagnostics::{Diagnostic as DDiag, Severity, Span};
use lsp_server::{Connection, ErrorCode, Message, Notification, Request, Response};
use lsp_types::*;
use serde_json::{json, Value};
use std::collections::HashMap;
use text::{ident_at, LineIndex};

struct Doc {
    text: String,
    index: LineIndex,
    analysis: Analysis,
}

impl Doc {
    fn new(raw: &str) -> Doc {
        let text = dhad_syntax::normalize_source(raw);
        let analysis = analyze(&text);
        let index = LineIndex::new(&text);
        Doc {
            text,
            index,
            analysis,
        }
    }

    fn range(&self, s: Span) -> Range {
        Range::new(
            self.index.position(&self.text, s.start),
            self.index.position(&self.text, s.end),
        )
    }

    fn offset(&self, p: Position) -> usize {
        self.index.offset(&self.text, p)
    }
}

struct Server {
    conn: Connection,
    docs: HashMap<String, Doc>,
}

fn capabilities() -> Value {
    serde_json::to_value(ServerCapabilities {
        text_document_sync: Some(TextDocumentSyncCapability::Kind(TextDocumentSyncKind::FULL)),
        completion_provider: Some(CompletionOptions {
            trigger_characters: Some(vec![".".into()]),
            ..Default::default()
        }),
        hover_provider: Some(HoverProviderCapability::Simple(true)),
        definition_provider: Some(OneOf::Left(true)),
        references_provider: Some(OneOf::Left(true)),
        document_highlight_provider: Some(OneOf::Left(true)),
        document_symbol_provider: Some(OneOf::Left(true)),
        rename_provider: Some(OneOf::Right(RenameOptions {
            prepare_provider: Some(true),
            work_done_progress_options: Default::default(),
        })),
        signature_help_provider: Some(SignatureHelpOptions {
            trigger_characters: Some(vec!["(".into(), ",".into(), "،".into()]),
            retrigger_characters: None,
            work_done_progress_options: Default::default(),
        }),
        code_action_provider: Some(CodeActionProviderCapability::Simple(true)),
        document_formatting_provider: Some(OneOf::Left(true)),
        ..Default::default()
    })
    .unwrap()
}

fn main() {
    let (conn, io) = Connection::stdio();
    if let Err(e) = conn.initialize(capabilities()) {
        eprintln!("ضاد-lsp: فشل التهيئة: {e}");
        return;
    }
    let mut server = Server {
        conn,
        docs: HashMap::new(),
    };
    server.run();
    drop(server);
    let _ = io.join();
}

impl Server {
    fn run(&mut self) {
        while let Ok(msg) = self.conn.receiver.recv() {
            match msg {
                Message::Request(req) => {
                    if self.conn.handle_shutdown(&req).unwrap_or(true) {
                        return;
                    }
                    let id = req.id.clone();
                    let resp = match self.request(req) {
                        Ok(v) => Response::new_ok(id, v),
                        Err((code, m)) => Response::new_err(id, code as i32, m),
                    };
                    let _ = self.conn.sender.send(Message::Response(resp));
                }
                Message::Notification(n) => self.notification(n),
                Message::Response(_) => {}
            }
        }
    }

    fn notification(&mut self, n: Notification) {
        match n.method.as_str() {
            "textDocument/didOpen" => {
                if let Ok(p) = serde_json::from_value::<DidOpenTextDocumentParams>(n.params) {
                    let uri = p.text_document.uri;
                    self.docs
                        .insert(uri.as_str().to_string(), Doc::new(&p.text_document.text));
                    self.publish(&uri);
                }
            }
            "textDocument/didChange" => {
                if let Ok(p) = serde_json::from_value::<DidChangeTextDocumentParams>(n.params) {
                    if let Some(change) = p.content_changes.into_iter().last() {
                        let uri = p.text_document.uri;
                        self.docs
                            .insert(uri.as_str().to_string(), Doc::new(&change.text));
                        self.publish(&uri);
                    }
                }
            }
            "textDocument/didClose" => {
                if let Ok(p) = serde_json::from_value::<DidCloseTextDocumentParams>(n.params) {
                    self.docs.remove(p.text_document.uri.as_str());
                    let params = PublishDiagnosticsParams::new(p.text_document.uri, vec![], None);
                    self.notify("textDocument/publishDiagnostics", params);
                }
            }
            _ => {}
        }
    }

    fn notify(&self, method: &str, params: impl serde::Serialize) {
        let _ = self
            .conn
            .sender
            .send(Message::Notification(Notification::new(
                method.to_string(),
                params,
            )));
    }

    fn publish(&self, uri: &Uri) {
        let Some(doc) = self.docs.get(uri.as_str()) else {
            return;
        };
        let diags = doc
            .analysis
            .diagnostics
            .iter()
            .map(|d| to_lsp_diag(doc, d))
            .collect();
        self.notify(
            "textDocument/publishDiagnostics",
            PublishDiagnosticsParams::new(uri.clone(), diags, None),
        );
    }

    fn doc(&self, uri: &Uri) -> Result<&Doc, (ErrorCode, String)> {
        self.docs
            .get(uri.as_str())
            .ok_or((ErrorCode::InvalidParams, "المستند غير مفتوح".into()))
    }

    fn request(&mut self, req: Request) -> Result<Value, (ErrorCode, String)> {
        fn params<T: serde::de::DeserializeOwned>(v: Value) -> Result<T, (ErrorCode, String)> {
            serde_json::from_value(v).map_err(|e| (ErrorCode::InvalidParams, e.to_string()))
        }
        let v = match req.method.as_str() {
            "textDocument/completion" => {
                let p: CompletionParams = params(req.params)?;
                let doc = self.doc(&p.text_document_position.text_document.uri)?;
                serde_json::to_value(completion(doc, p.text_document_position.position))
            }
            "textDocument/hover" => {
                let p: HoverParams = params(req.params)?;
                let doc = self.doc(&p.text_document_position_params.text_document.uri)?;
                serde_json::to_value(hover(doc, p.text_document_position_params.position))
            }
            "textDocument/definition" => {
                let p: GotoDefinitionParams = params(req.params)?;
                let tdp = p.text_document_position_params;
                let doc = self.doc(&tdp.text_document.uri)?;
                let off = doc.offset(tdp.position);
                let loc = doc.analysis.symbol_at(off).map(|(i, _)| {
                    Location::new(
                        tdp.text_document.uri.clone(),
                        doc.range(doc.analysis.symbols[i].span),
                    )
                });
                serde_json::to_value(loc)
            }
            "textDocument/references" => {
                let p: ReferenceParams = params(req.params)?;
                let tdp = p.text_document_position;
                let doc = self.doc(&tdp.text_document.uri)?;
                let locs: Option<Vec<Location>> = doc
                    .analysis
                    .symbol_at(doc.offset(tdp.position))
                    .map(|(i, _)| {
                        doc.analysis
                            .occurrences(i)
                            .into_iter()
                            .map(|s| Location::new(tdp.text_document.uri.clone(), doc.range(s)))
                            .collect()
                    });
                serde_json::to_value(locs)
            }
            "textDocument/documentHighlight" => {
                let p: DocumentHighlightParams = params(req.params)?;
                let tdp = p.text_document_position_params;
                let doc = self.doc(&tdp.text_document.uri)?;
                let hl: Option<Vec<DocumentHighlight>> = doc
                    .analysis
                    .symbol_at(doc.offset(tdp.position))
                    .map(|(i, _)| {
                        doc.analysis
                            .occurrences(i)
                            .into_iter()
                            .map(|s| DocumentHighlight {
                                range: doc.range(s),
                                kind: Some(DocumentHighlightKind::TEXT),
                            })
                            .collect()
                    });
                serde_json::to_value(hl)
            }
            "textDocument/documentSymbol" => {
                let p: DocumentSymbolParams = params(req.params)?;
                let doc = self.doc(&p.text_document.uri)?;
                serde_json::to_value(DocumentSymbolResponse::Nested(document_symbols(doc)))
            }
            "textDocument/prepareRename" => {
                let p: TextDocumentPositionParams = params(req.params)?;
                let doc = self.doc(&p.text_document.uri)?;
                let r = doc
                    .analysis
                    .symbol_at(doc.offset(p.position))
                    .filter(|(i, _)| doc.analysis.symbols[*i].kind != SymbolKind::Module)
                    .map(|(_, s)| PrepareRenameResponse::Range(doc.range(s)));
                serde_json::to_value(r)
            }
            "textDocument/rename" => {
                let p: RenameParams = params(req.params)?;
                let tdp = p.text_document_position;
                let doc = self.doc(&tdp.text_document.uri)?;
                let new_name = dhad_syntax::normalize_source(&p.new_name);
                let valid = dhad_syntax::tokenize(&new_name)
                    .map(|t| t.len() == 3 && matches!(t[0].tok, dhad_syntax::Tok::Ident(_)))
                    .unwrap_or(false);
                if !valid {
                    return Err((
                        ErrorCode::InvalidParams,
                        format!("«{}» ليس اسمًا صالحًا (قد يكون كلمة محجوزة)", p.new_name),
                    ));
                }
                let Some((i, _)) = doc.analysis.symbol_at(doc.offset(tdp.position)) else {
                    return Ok(Value::Null);
                };
                let edits = doc
                    .analysis
                    .occurrences(i)
                    .into_iter()
                    .map(|s| TextEdit::new(doc.range(s), new_name.clone()))
                    .collect();
                #[allow(clippy::mutable_key_type)]
                let changes = HashMap::from([(tdp.text_document.uri.clone(), edits)]);
                serde_json::to_value(WorkspaceEdit::new(changes))
            }
            "textDocument/signatureHelp" => {
                let p: SignatureHelpParams = params(req.params)?;
                let tdp = p.text_document_position_params;
                let doc = self.doc(&tdp.text_document.uri)?;
                serde_json::to_value(signature_help(doc, tdp.position))
            }
            "textDocument/formatting" => {
                let p: DocumentFormattingParams = params(req.params)?;
                let doc = self.doc(&p.text_document.uri)?;
                let edits = match dhad_fmt::format(&doc.text) {
                    Ok(out) if out != doc.text => {
                        let end = doc.index.position(&doc.text, doc.text.len());
                        Some(vec![TextEdit::new(
                            Range::new(Position::new(0, 0), end),
                            out,
                        )])
                    }
                    Ok(_) => Some(vec![]),
                    Err(_) => None,
                };
                serde_json::to_value(edits)
            }
            "textDocument/codeAction" => {
                let p: CodeActionParams = params(req.params)?;
                let doc = self.doc(&p.text_document.uri)?;
                serde_json::to_value(code_actions(doc, &p))
            }
            other => {
                return Err((ErrorCode::MethodNotFound, format!("غير مدعوم: {other}")));
            }
        };
        v.map_err(|e| (ErrorCode::InternalError, e.to_string()))
    }
}

fn to_lsp_diag(doc: &Doc, d: &DDiag) -> Diagnostic {
    let range = d
        .span
        .map(|s| doc.range(s))
        .unwrap_or_else(|| Range::new(Position::new(0, 0), Position::new(0, 0)));
    let mut message = d.message.clone();
    if let Some(h) = &d.help {
        message.push_str("\nمساعدة: ");
        message.push_str(h);
    }
    Diagnostic {
        range,
        severity: Some(match d.severity {
            Severity::Error => DiagnosticSeverity::ERROR,
            Severity::Warning => DiagnosticSeverity::WARNING,
        }),
        code: Some(NumberOrString::String(d.code_str())),
        source: Some("ضاد".into()),
        message,
        tags: (d.code == 3001).then(|| vec![DiagnosticTag::UNNECESSARY]),
        data: d.help.as_ref().map(|h| json!({ "help": h })),
        ..Default::default()
    }
}

fn md(value: String) -> Hover {
    Hover {
        contents: HoverContents::Markup(MarkupContent {
            kind: MarkupKind::Markdown,
            value,
        }),
        range: None,
    }
}

fn code_block(s: &str) -> String {
    format!("```dhad\n{s}\n```")
}

fn hover(doc: &Doc, pos: Position) -> Option<Hover> {
    let off = doc.offset(pos);
    if let Some((_, m, member)) = doc
        .analysis
        .member_refs
        .iter()
        .find(|(s, _, _)| s.start <= off && off <= s.end)
    {
        let item = catalog::module_member(m, member)?;
        return Some(md(format!(
            "{}\n\n{}\n\n*من وحدة {m}*",
            code_block(&format!("{m}.{}", item.signature)),
            item.doc
        )));
    }
    if let Some((i, _)) = doc.analysis.symbol_at(off) {
        let s = &doc.analysis.symbols[i];
        let head = match s.kind {
            SymbolKind::Function => format!("دالة {}({})", s.name, s.params.join("، ")),
            SymbolKind::Module => {
                let (_, desc, items) = catalog::module(&s.name)?;
                let names: Vec<&str> = items.iter().map(|i| i.name).collect();
                return Some(md(format!(
                    "{}\n\n{desc}\n\nالأعضاء: {}",
                    code_block(&format!("استورد {}", s.name)),
                    names.join("، ")
                )));
            }
            kind => {
                let t = s.value_type.map(|t| format!(": {t}")).unwrap_or_default();
                let kw = if kind == SymbolKind::Constant {
                    "ثابت"
                } else {
                    "دع"
                };
                if matches!(kind, SymbolKind::Variable | SymbolKind::Constant) {
                    format!("{kw} {}{t}", s.name)
                } else {
                    format!("({}) {}", kind.label(), s.name)
                }
            }
        };
        let mut out = code_block(&head);
        if let Some(d) = &s.doc {
            out.push_str("\n\n");
            out.push_str(d);
        }
        out.push_str(&format!("\n\n*{}*", s.kind.label()));
        return Some(md(out));
    }
    let (word, _) = ident_at(&doc.text, off)?;
    let word = dhad_syntax::unicode::strip_tashkeel(&word);
    if let Some(b) = catalog::builtin(&word) {
        return Some(md(format!(
            "{}\n\n{}\n\n*دالة مدمجة*",
            code_block(b.signature),
            b.doc
        )));
    }
    if let Some(k) = catalog::keyword(&word) {
        return Some(md(format!(
            "{}\n\n{}\n\n*كلمة مفتاحية*",
            code_block(k.signature),
            k.doc
        )));
    }
    None
}

fn keyword_snippet(k: &str) -> Option<&'static str> {
    Some(match k {
        "إذا" => "إذا ${1:الشرط} {\n\t$0\n}",
        "طالما" => "طالما ${1:الشرط} {\n\t$0\n}",
        "لكل" => "لكل ${1:ع} في ${2:١..١٠} {\n\t$0\n}",
        "دالة" => "دالة ${1:الاسم}(${2}) {\n\t$0\n}",
        "اختبر" => "اختبر \"${1:الوصف}\" {\n\tتأكد($0)\n}",
        "دع" => "دع ${1:الاسم} = $0",
        _ => return None,
    })
}

fn completion(doc: &Doc, pos: Position) -> CompletionResponse {
    let off = doc.offset(pos);
    let before = &doc.text[..off];
    let partial_start = before
        .char_indices()
        .rev()
        .take_while(|(_, c)| text::is_ident_char(*c))
        .last()
        .map(|(i, _)| i)
        .unwrap_or(off);
    if before[..partial_start].ends_with('.') {
        let obj_end = partial_start - 1;
        let obj_start = before[..obj_end]
            .char_indices()
            .rev()
            .take_while(|(_, c)| text::is_ident_char(*c))
            .last()
            .map(|(i, _)| i)
            .unwrap_or(obj_end);
        let module = &before[obj_start..obj_end];
        let items = catalog::module(module)
            .map(|(_, _, items)| {
                items
                    .iter()
                    .map(|i| CompletionItem {
                        label: i.name.into(),
                        kind: Some(if i.signature.contains('(') {
                            CompletionItemKind::FUNCTION
                        } else {
                            CompletionItemKind::CONSTANT
                        }),
                        detail: Some(i.signature.into()),
                        documentation: Some(Documentation::String(i.doc.into())),
                        ..Default::default()
                    })
                    .collect()
            })
            .unwrap_or_default();
        return CompletionResponse::Array(items);
    }

    let mut items = Vec::new();
    for k in catalog::KEYWORDS {
        let snippet = keyword_snippet(k.name);
        items.push(CompletionItem {
            label: k.name.into(),
            kind: Some(if snippet.is_some() {
                CompletionItemKind::SNIPPET
            } else {
                CompletionItemKind::KEYWORD
            }),
            detail: Some(k.signature.into()),
            documentation: Some(Documentation::String(k.doc.into())),
            insert_text: snippet.map(String::from),
            insert_text_format: snippet.map(|_| InsertTextFormat::SNIPPET),
            sort_text: Some(format!("2{}", k.name)),
            ..Default::default()
        });
    }
    for b in catalog::BUILTINS {
        items.push(CompletionItem {
            label: b.name.into(),
            kind: Some(CompletionItemKind::FUNCTION),
            detail: Some(b.signature.into()),
            documentation: Some(Documentation::String(b.doc.into())),
            sort_text: Some(format!("1{}", b.name)),
            ..Default::default()
        });
    }
    let imported: Vec<&str> = doc
        .analysis
        .symbols
        .iter()
        .filter(|s| s.kind == SymbolKind::Module)
        .map(|s| s.name.as_str())
        .collect();
    for (m, desc, _) in catalog::MODULES {
        if !imported.contains(m) {
            items.push(CompletionItem {
                label: m.to_string(),
                kind: Some(CompletionItemKind::MODULE),
                detail: Some(format!("{desc} (سيُضاف الاستيراد)")),
                additional_text_edits: Some(vec![TextEdit::new(
                    Range::new(Position::new(0, 0), Position::new(0, 0)),
                    format!("استورد {m}\n"),
                )]),
                sort_text: Some(format!("3{m}")),
                ..Default::default()
            });
        }
    }
    let mut seen = std::collections::HashSet::new();
    for s in &doc.analysis.symbols {
        if !seen.insert(s.name.clone()) {
            continue;
        }
        let kind = match s.kind {
            SymbolKind::Function => CompletionItemKind::FUNCTION,
            SymbolKind::Constant => CompletionItemKind::CONSTANT,
            SymbolKind::Module => CompletionItemKind::MODULE,
            _ => CompletionItemKind::VARIABLE,
        };
        let detail = match s.kind {
            SymbolKind::Function => format!("دالة {}({})", s.name, s.params.join("، ")),
            k => k.label().to_string(),
        };
        items.push(CompletionItem {
            label: s.name.clone(),
            kind: Some(kind),
            detail: Some(detail),
            documentation: s.doc.clone().map(Documentation::String),
            sort_text: Some(format!("0{}", s.name)),
            ..Default::default()
        });
    }
    CompletionResponse::Array(items)
}

fn document_symbols(doc: &Doc) -> Vec<DocumentSymbol> {
    doc.analysis
        .symbols
        .iter()
        .filter(|s| s.top_level && s.kind != SymbolKind::Module)
        .map(|s| {
            #[allow(deprecated)]
            DocumentSymbol {
                name: s.name.clone(),
                detail: Some(match s.kind {
                    SymbolKind::Function => format!("({})", s.params.join("، ")),
                    k => k.label().into(),
                }),
                kind: match s.kind {
                    SymbolKind::Function => lsp_types::SymbolKind::FUNCTION,
                    SymbolKind::Constant => lsp_types::SymbolKind::CONSTANT,
                    _ => lsp_types::SymbolKind::VARIABLE,
                },
                tags: None,
                deprecated: None,
                range: doc.range(s.decl_span),
                selection_range: doc.range(s.span),
                children: None,
            }
        })
        .collect()
}

fn signature_help(doc: &Doc, pos: Position) -> Option<SignatureHelp> {
    let off = doc.offset(pos);
    let before: Vec<char> = doc.text[..off].chars().collect();
    let (mut depth, mut commas, mut in_str) = (0i32, 0u32, false);
    let mut i = before.len();
    while i > 0 {
        i -= 1;
        match before[i] {
            '"' => in_str = !in_str,
            _ if in_str => {}
            ')' | ']' | '}' => depth += 1,
            '[' | '{' => depth -= 1,
            '(' if depth == 0 => break,
            '(' => depth -= 1,
            ',' | '،' if depth == 0 => commas += 1,
            _ => {}
        }
        if i == 0 {
            return None;
        }
    }
    let name_end = i;
    let mut start = name_end;
    while start > 0 && text::is_ident_char(before[start - 1]) {
        start -= 1;
    }
    let name: String = before[start..name_end].iter().collect();
    let name = dhad_syntax::unicode::strip_tashkeel(&name);
    if name.is_empty() {
        return None;
    }
    let is_member = start > 0 && before[start - 1] == '.';
    let (label, params, documentation): (String, Vec<String>, Option<String>) = if is_member {
        let mut ms = start - 1;
        while ms > 0 && text::is_ident_char(before[ms - 1]) {
            ms -= 1;
        }
        let module: String = before[ms..start - 1].iter().collect();
        let item = catalog::module_member(&module, &name)?;
        (
            item.signature.into(),
            split_params(item.signature),
            Some(item.doc.into()),
        )
    } else if let Some(s) = doc
        .analysis
        .symbols
        .iter()
        .rev()
        .find(|s| s.name == name && s.kind == SymbolKind::Function)
    {
        (
            format!("{}({})", s.name, s.params.join("، ")),
            s.params.clone(),
            s.doc.clone(),
        )
    } else {
        let b = catalog::builtin(&name)?;
        (
            b.signature.into(),
            split_params(b.signature),
            Some(b.doc.into()),
        )
    };
    Some(SignatureHelp {
        signatures: vec![SignatureInformation {
            label,
            documentation: documentation.map(Documentation::String),
            parameters: Some(
                params
                    .into_iter()
                    .map(|p| ParameterInformation {
                        label: ParameterLabel::Simple(p),
                        documentation: None,
                    })
                    .collect(),
            ),
            active_parameter: None,
        }],
        active_signature: Some(0),
        active_parameter: Some(commas),
    })
}

/// معاملات توقيع مثل «تقريب(عدد، خانات؟) ← عدد».
fn split_params(sig: &str) -> Vec<String> {
    let Some(open) = sig.find('(') else {
        return vec![];
    };
    let Some(close) = sig[open..].find(')') else {
        return vec![];
    };
    sig[open + 1..open + close]
        .split(['،', ','])
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

fn code_actions(doc: &Doc, p: &CodeActionParams) -> Vec<CodeActionOrCommand> {
    let mut actions = Vec::new();
    for d in &p.context.diagnostics {
        let Some(help) = d
            .data
            .as_ref()
            .and_then(|v| v.get("help"))
            .and_then(|v| v.as_str())
        else {
            continue;
        };
        let code = match &d.code {
            Some(NumberOrString::String(s)) => s.clone(),
            _ => continue,
        };
        #[allow(clippy::mutable_key_type)]
        let edit = |edits: Vec<TextEdit>| {
            WorkspaceEdit::new(HashMap::from([(p.text_document.uri.clone(), edits)]))
        };
        if code == "ضاد-1001" {
            if let Some(name) = help.split('«').nth(1).and_then(|s| s.split('»').next()) {
                actions.push(CodeActionOrCommand::CodeAction(CodeAction {
                    title: format!("استبدل بـ «{name}»"),
                    kind: Some(CodeActionKind::QUICKFIX),
                    diagnostics: Some(vec![d.clone()]),
                    edit: Some(edit(vec![TextEdit::new(d.range, name.to_string())])),
                    is_preferred: Some(true),
                    ..Default::default()
                }));
            }
            if let Some(module) = help.strip_prefix("أضف في أول البرنامج: استورد ")
            {
                actions.push(CodeActionOrCommand::CodeAction(CodeAction {
                    title: format!("أضف: استورد {module}"),
                    kind: Some(CodeActionKind::QUICKFIX),
                    diagnostics: Some(vec![d.clone()]),
                    edit: Some(edit(vec![TextEdit::new(
                        Range::new(Position::new(0, 0), Position::new(0, 0)),
                        format!("استورد {module}\n"),
                    )])),
                    is_preferred: Some(true),
                    ..Default::default()
                }));
            }
        }
        if code == "ضاد-3001" {
            let name = doc
                .text
                .get(doc.offset(d.range.start)..doc.offset(d.range.end))
                .unwrap_or("");
            actions.push(CodeActionOrCommand::CodeAction(CodeAction {
                title: format!("أعد التسمية إلى «_{name}» لإسكات التحذير"),
                kind: Some(CodeActionKind::QUICKFIX),
                diagnostics: Some(vec![d.clone()]),
                edit: Some(edit(vec![TextEdit::new(
                    Range::new(d.range.start, d.range.start),
                    "_".into(),
                )])),
                ..Default::default()
            }));
        }
    }
    actions
}
