//! شجرة البرنامج (AST) للغة ضاد.

use dhad_diagnostics::Span;

#[derive(Debug, Clone, PartialEq)]
pub struct Program {
    pub stmts: Vec<Stmt>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Stmt {
    pub kind: StmtKind,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum StmtKind {
    /// `دع اسم = قيمة` أو `ثابت اسم = قيمة`
    Let {
        name: String,
        name_span: Span,
        value: Expr,
        is_const: bool,
    },
    /// `هدف = قيمة`
    Assign {
        target: Expr,
        value: Expr,
    },
    If {
        cond: Expr,
        then: Block,
        elifs: Vec<(Expr, Block)>,
        otherwise: Option<Block>,
    },
    While {
        cond: Expr,
        body: Block,
    },
    For {
        var: String,
        var_span: Span,
        iter: Expr,
        body: Block,
    },
    FnDecl {
        name: String,
        params: Vec<(String, Span)>,
        body: Block,
    },
    Return(Option<Expr>),
    Break,
    Continue,
    /// `استورد رياضيات`
    Import {
        path: Vec<String>,
    },
    /// `اختبر "وصف" { ... }`
    Test {
        name: String,
        body: Block,
    },
    Expr(Expr),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Block {
    pub stmts: Vec<Stmt>,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ExprKind {
    Int(i64),
    Float(f64),
    Str(Vec<StrSeg>),
    Bool(bool),
    Null,
    Ident(String),
    List(Vec<Expr>),
    Dict(Vec<(Expr, Expr)>),
    Binary {
        op: BinOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Unary {
        op: UnOp,
        expr: Box<Expr>,
    },
    Call {
        callee: Box<Expr>,
        args: Vec<Expr>,
    },
    Index {
        obj: Box<Expr>,
        index: Box<Expr>,
    },
    Member {
        obj: Box<Expr>,
        name: String,
    },
    Range {
        from: Box<Expr>,
        to: Box<Expr>,
    },
}

/// جزء من نص: نص حرفي أو تعبير مدمج `${...}`.
#[derive(Debug, Clone, PartialEq)]
pub enum StrSeg {
    Text(String),
    Expr(Expr),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    IntDiv,
    Mod,
    Eq,
    NotEq,
    Lt,
    Gt,
    LtEq,
    GtEq,
    And,
    Or,
    /// `عنصر في مجموعة`
    In,
}

impl BinOp {
    pub fn symbol(self) -> &'static str {
        match self {
            BinOp::Add => "+",
            BinOp::Sub => "-",
            BinOp::Mul => "*",
            BinOp::Div => "/",
            BinOp::IntDiv => "//",
            BinOp::Mod => "%",
            BinOp::Eq => "==",
            BinOp::NotEq => "!=",
            BinOp::Lt => "<",
            BinOp::Gt => ">",
            BinOp::LtEq => "<=",
            BinOp::GtEq => ">=",
            BinOp::And => "و",
            BinOp::Or => "أو",
            BinOp::In => "في",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnOp {
    Neg,
    Not,
}
