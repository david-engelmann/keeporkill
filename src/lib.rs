//! tameshi, the evidence pack tool for checks.
//!
//! This crate is the Rust port of the Python package of the same
//! name, standing under the port obligations of the contract. Slice 1
//! carries the deterministic rendering and the document reader and
//! the evidence pack assembly and the ruling generation, with the
//! validation and normalization readings they stand on, and it proves
//! each against recorded conformance drawn from the landed Python.
//! Slice 2 adds the catchledger document reading whole, the read
//! entry the assembly stands on, proven the same way. The closing
//! slice carries the command line whole into the binary over this
//! library, proven against a recorded battery of invocations.

pub mod dates;
pub mod errors;
pub mod ingest;
pub mod jsonvalue;
pub mod names;
pub mod packs;
pub mod reader;
pub mod render;
pub mod rulings;

pub use errors::{ErrorKind, Result, TameshiError};
pub use jsonvalue::JsonValue;
