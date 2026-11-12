//! بيئات التنفيذ (النطاقات اللغوية).

use crate::value::Value;
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;

struct Var {
    value: Value,
    is_const: bool,
}

struct Scope {
    vars: HashMap<String, Var>,
    parent: Option<Env>,
}

/// نطاق قابل للمشاركة؛ الدوال تلتقطه كإغلاق.
#[derive(Clone)]
pub struct Env(Rc<RefCell<Scope>>);

pub enum AssignErr {
    NotFound,
    Const,
}

impl Default for Env {
    fn default() -> Self {
        Self::new()
    }
}

impl Env {
    pub fn new() -> Env {
        Env(Rc::new(RefCell::new(Scope {
            vars: HashMap::new(),
            parent: None,
        })))
    }

    pub fn child(&self) -> Env {
        Env(Rc::new(RefCell::new(Scope {
            vars: HashMap::new(),
            parent: Some(self.clone()),
        })))
    }

    pub fn define(&self, name: &str, value: Value, is_const: bool) {
        self.0
            .borrow_mut()
            .vars
            .insert(name.to_string(), Var { value, is_const });
    }

    pub fn get(&self, name: &str) -> Option<Value> {
        let scope = self.0.borrow();
        if let Some(v) = scope.vars.get(name) {
            return Some(v.value.clone());
        }
        scope.parent.as_ref().and_then(|p| p.get(name))
    }

    pub fn assign(&self, name: &str, value: Value) -> Result<(), AssignErr> {
        let mut scope = self.0.borrow_mut();
        if let Some(v) = scope.vars.get_mut(name) {
            if v.is_const {
                return Err(AssignErr::Const);
            }
            v.value = value;
            return Ok(());
        }
        match &scope.parent {
            Some(p) => p.assign(name, value),
            None => Err(AssignErr::NotFound),
        }
    }

    /// كل الأسماء المرئية من هذا النطاق (لاقتراح الأسماء القريبة وللإكمال).
    pub fn visible_names(&self) -> Vec<String> {
        let mut names = Vec::new();
        let mut cur = Some(self.clone());
        while let Some(env) = cur {
            let scope = env.0.borrow();
            names.extend(scope.vars.keys().cloned());
            cur = scope.parent.clone();
        }
        names.sort();
        names.dedup();
        names
    }
}
