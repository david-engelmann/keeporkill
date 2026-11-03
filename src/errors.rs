//! Error types for tameshi, mirroring the Python error classes.
//!
//! A refusal is the plain tameshi error. A pack validation failure and
//! a floor refusal carry their own kinds, as the Python subclasses do,
//! so a refusal can be compared by kind and by wording together.

use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    Refusal,
    PackValidation,
    FloorRefusal,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TameshiError {
    pub kind: ErrorKind,
    pub message: String,
}

impl TameshiError {
    pub fn refusal(message: impl Into<String>) -> Self {
        TameshiError {
            kind: ErrorKind::Refusal,
            message: message.into(),
        }
    }

    pub fn pack_validation(message: impl Into<String>) -> Self {
        TameshiError {
            kind: ErrorKind::PackValidation,
            message: message.into(),
        }
    }

    pub fn floor_refusal(message: impl Into<String>) -> Self {
        TameshiError {
            kind: ErrorKind::FloorRefusal,
            message: message.into(),
        }
    }

    /// The name of the Python error class this kind is the counterpart of.
    pub fn class_name(&self) -> &'static str {
        match self.kind {
            ErrorKind::Refusal => "TameshiError",
            ErrorKind::PackValidation => "PackValidationError",
            ErrorKind::FloorRefusal => "FloorRefusal",
        }
    }
}

impl fmt::Display for TameshiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for TameshiError {}

pub type Result<T> = std::result::Result<T, TameshiError>;
