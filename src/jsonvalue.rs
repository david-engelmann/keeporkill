//! A JSON value with the readings the Python language gives it.
//!
//! An object keeps its fields in the order they were written, and
//! equality reads the Python way. Two objects are equal when they
//! carry the same fields with equal values, without regard to the
//! order the fields stand in, and numbers compare across their kinds
//! the way Python compares them, so a whole number and that same
//! number written with a decimal point count as the same number, and
//! a boolean counts as its number where a number stands beside it. A
//! whole number and a decimal stay apart as spellings, so a reading
//! that asks what kind of number a value carries can still tell them
//! apart the way the Python type checks do. A whole number too large
//! for the machine word is carried with its exact digits, as the
//! Python whole number is carried, and a not a number value stands
//! equal to nothing, not even to another not a number value, as the
//! Python comparison reads it.

/// The deepest nesting the document reader reads. A document nested
/// deeper than this is refused as not valid JSON, under obligation
/// RFIX-7, so a hostile document is refused instead of overflowing
/// the stack.
pub const MAX_NESTING_DEPTH: usize = 4000;

/// A JSON value as the Python reader produces one.
#[derive(Debug, Clone)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Int(i64),
    /// A whole number beyond the machine word, carried as its exact
    /// decimal digits in the spelling the document gave it, which
    /// the JSON grammar keeps canonical.
    BigInt(String),
    Float(f64),
    Text(String),
    List(Vec<JsonValue>),
    Object(Vec<(String, JsonValue)>),
}

impl JsonValue {
    /// Look a field up by name, as a mapping access on a present key.
    pub fn get(&self, key: &str) -> Option<&JsonValue> {
        match self {
            JsonValue::Object(fields) => fields
                .iter()
                .find(|(name, _)| name == key)
                .map(|(_, value)| value),
            _ => None,
        }
    }

    pub fn as_text(&self) -> Option<&str> {
        match self {
            JsonValue::Text(text) => Some(text),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&[JsonValue]> {
        match self {
            JsonValue::List(items) => Some(items),
            _ => None,
        }
    }

    pub fn as_object(&self) -> Option<&Vec<(String, JsonValue)>> {
        match self {
            JsonValue::Object(fields) => Some(fields),
            _ => None,
        }
    }

    pub fn is_object(&self) -> bool {
        matches!(self, JsonValue::Object(_))
    }

    /// Whether this value is a whole number, as the Python type
    /// check on a read value reads one, a whole number of any size
    /// counting and a boolean not counting.
    pub fn is_whole(&self) -> bool {
        matches!(self, JsonValue::Int(_) | JsonValue::BigInt(_))
    }

    /// The exact digits of a whole number, sign included, in the
    /// canonical spelling the Python language writes the number in.
    pub fn whole_digits(&self) -> Option<String> {
        match self {
            JsonValue::Int(whole) => Some(whole.to_string()),
            JsonValue::BigInt(digits) => Some(digits.clone()),
            _ => None,
        }
    }

    /// Whether this value is a whole number standing at or above
    /// zero, as the Python whole number checks in the canary
    /// readings read one.
    pub fn is_nonnegative_whole(&self) -> bool {
        match self {
            JsonValue::Int(whole) => *whole >= 0,
            JsonValue::BigInt(digits) => !digits.starts_with('-'),
            _ => false,
        }
    }
}

/// The exact digits of the whole number a finite whole valued
/// decimal stands for, where it stands for one at all.
fn decimal_whole_digits(value: f64) -> Option<String> {
    if !value.is_finite() || value.fract() != 0.0 {
        return None;
    }
    if value == 0.0 {
        return Some("0".to_string());
    }
    Some(format!("{:.0}", value))
}

/// The digits a value counts as in a numeric comparison, a boolean
/// counting as its number and a whole number of any size counting
/// by its exact digits, where the value is a whole number at all in
/// that reading.
fn counted_digits(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::Bool(word) => Some(if *word { "1" } else { "0" }.to_string()),
        JsonValue::Int(whole) => Some(whole.to_string()),
        JsonValue::BigInt(digits) => Some(digits.clone()),
        _ => None,
    }
}

/// Whether two values stand as numbers at all in the Python
/// reading, and where they do, whether those numbers are equal.
/// The Python compares a whole number and a decimal by their exact
/// values, so a decimal counts against a whole number only through
/// the exact digits of the whole number the decimal stands for, and
/// a not a number value is equal to nothing, not even to another
/// not a number value.
fn numeric_equality(left: &JsonValue, right: &JsonValue) -> Option<bool> {
    match (left, right) {
        (JsonValue::Float(a), JsonValue::Float(b)) => Some(a == b),
        (JsonValue::Float(a), _) => {
            counted_digits(right).map(|digits| decimal_whole_digits(*a) == Some(digits))
        }
        (_, JsonValue::Float(b)) => {
            counted_digits(left).map(|digits| decimal_whole_digits(*b) == Some(digits))
        }
        _ => match (counted_digits(left), counted_digits(right)) {
            (Some(a), Some(b)) => Some(a == b),
            _ => None,
        },
    }
}

impl PartialEq for JsonValue {
    fn eq(&self, other: &JsonValue) -> bool {
        use JsonValue::*;
        if let Some(equal) = numeric_equality(self, other) {
            return equal;
        }
        match (self, other) {
            (Null, Null) => true,
            (Text(left), Text(right)) => left == right,
            (List(left), List(right)) => {
                left.len() == right.len() && left.iter().zip(right.iter()).all(|(a, b)| a == b)
            }
            (Object(left), Object(right)) => {
                left.len() == right.len()
                    && left.iter().all(|(key, value)| match other.get(key) {
                        Some(found) => found == value,
                        None => false,
                    })
            }
            _ => false,
        }
    }
}

/// What a document can fail to be, read by the document reader.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseError {
    Invalid,
    DuplicateKey(String),
}

struct Parser {
    chars: Vec<char>,
    pos: usize,
}

impl Parser {
    fn peek(&self) -> Option<char> {
        self.chars.get(self.pos).copied()
    }

    fn bump(&mut self) -> Option<char> {
        let current = self.peek();
        if current.is_some() {
            self.pos += 1;
        }
        current
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(' ' | '\t' | '\n' | '\r')) {
            self.pos += 1;
        }
    }

    fn expect(&mut self, word: &str) -> Result<(), ParseError> {
        for expected in word.chars() {
            if self.bump() != Some(expected) {
                return Err(ParseError::Invalid);
            }
        }
        Ok(())
    }

    fn parse_value(&mut self, depth: usize) -> Result<JsonValue, ParseError> {
        self.skip_whitespace();
        match self.peek() {
            Some('{') => self.parse_object(depth),
            Some('[') => self.parse_list(depth),
            Some('"') => Ok(JsonValue::Text(self.parse_string()?)),
            Some('t') => {
                self.expect("true")?;
                Ok(JsonValue::Bool(true))
            }
            Some('f') => {
                self.expect("false")?;
                Ok(JsonValue::Bool(false))
            }
            Some('n') => {
                self.expect("null")?;
                Ok(JsonValue::Null)
            }
            Some('N') => {
                self.expect("NaN")?;
                Ok(JsonValue::Float(f64::NAN))
            }
            Some('I') => {
                self.expect("Infinity")?;
                Ok(JsonValue::Float(f64::INFINITY))
            }
            Some('-') => {
                if self.chars.get(self.pos + 1) == Some(&'I') {
                    self.pos += 1;
                    self.expect("Infinity")?;
                    Ok(JsonValue::Float(f64::NEG_INFINITY))
                } else {
                    self.parse_number()
                }
            }
            Some(digit) if digit.is_ascii_digit() => self.parse_number(),
            _ => Err(ParseError::Invalid),
        }
    }

    fn parse_object(&mut self, depth: usize) -> Result<JsonValue, ParseError> {
        if depth > MAX_NESTING_DEPTH {
            return Err(ParseError::Invalid);
        }
        self.bump();
        let mut fields: Vec<(String, JsonValue)> = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some('}') {
            self.bump();
            return Ok(JsonValue::Object(fields));
        }
        loop {
            self.skip_whitespace();
            if self.peek() != Some('"') {
                return Err(ParseError::Invalid);
            }
            let key = self.parse_string()?;
            self.skip_whitespace();
            if self.bump() != Some(':') {
                return Err(ParseError::Invalid);
            }
            let value = self.parse_value(depth + 1)?;
            fields.push((key, value));
            self.skip_whitespace();
            match self.bump() {
                Some(',') => continue,
                Some('}') => {
                    // The duplicate reading stands where the Python
                    // object pairs hook stands, at the close of the
                    // object, so the repeated key named is the first
                    // key in the object that stands twice, and an
                    // inner object reports its own repeated key before
                    // the object holding it reports one of its own.
                    let mut seen: Vec<&String> = Vec::new();
                    for (name, _) in &fields {
                        if seen.contains(&name) {
                            return Err(ParseError::DuplicateKey(name.clone()));
                        }
                        seen.push(name);
                    }
                    return Ok(JsonValue::Object(fields));
                }
                _ => return Err(ParseError::Invalid),
            }
        }
    }

    fn parse_list(&mut self, depth: usize) -> Result<JsonValue, ParseError> {
        if depth > MAX_NESTING_DEPTH {
            return Err(ParseError::Invalid);
        }
        self.bump();
        let mut items = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(']') {
            self.bump();
            return Ok(JsonValue::List(items));
        }
        loop {
            let value = self.parse_value(depth + 1)?;
            items.push(value);
            self.skip_whitespace();
            match self.bump() {
                Some(',') => continue,
                Some(']') => return Ok(JsonValue::List(items)),
                _ => return Err(ParseError::Invalid),
            }
        }
    }

    fn parse_string(&mut self) -> Result<String, ParseError> {
        self.bump();
        let mut text = String::new();
        loop {
            match self.bump() {
                None => return Err(ParseError::Invalid),
                Some('"') => return Ok(text),
                Some('\\') => match self.bump() {
                    Some('"') => text.push('"'),
                    Some('\\') => text.push('\\'),
                    Some('/') => text.push('/'),
                    Some('b') => text.push('\u{0008}'),
                    Some('f') => text.push('\u{000C}'),
                    Some('n') => text.push('\n'),
                    Some('r') => text.push('\r'),
                    Some('t') => text.push('\t'),
                    Some('u') => {
                        let first = self.parse_hex_quad()?;
                        if (0xD800..0xDC00).contains(&first) {
                            // A high surrogate stands only as half of a
                            // pair. A lone surrogate is refused, as the
                            // port contract states, because the text type
                            // here holds no such string.
                            if self.bump() != Some('\\') || self.bump() != Some('u') {
                                return Err(ParseError::Invalid);
                            }
                            let second = self.parse_hex_quad()?;
                            if !(0xDC00..0xE000).contains(&second) {
                                return Err(ParseError::Invalid);
                            }
                            let combined = 0x10000 + ((first - 0xD800) << 10) + (second - 0xDC00);
                            text.push(char::from_u32(combined).ok_or(ParseError::Invalid)?);
                        } else if (0xDC00..0xE000).contains(&first) {
                            return Err(ParseError::Invalid);
                        } else {
                            text.push(char::from_u32(first).ok_or(ParseError::Invalid)?);
                        }
                    }
                    _ => return Err(ParseError::Invalid),
                },
                Some(control) if (control as u32) < 0x20 => {
                    return Err(ParseError::Invalid);
                }
                Some(other) => text.push(other),
            }
        }
    }

    fn parse_hex_quad(&mut self) -> Result<u32, ParseError> {
        let mut value: u32 = 0;
        for _ in 0..4 {
            let digit = self.bump().ok_or(ParseError::Invalid)?;
            let part = digit.to_digit(16).ok_or(ParseError::Invalid)?;
            value = value * 16 + part;
        }
        Ok(value)
    }

    fn parse_number(&mut self) -> Result<JsonValue, ParseError> {
        let start = self.pos;
        if self.peek() == Some('-') {
            self.bump();
        }
        match self.peek() {
            Some('0') => {
                self.bump();
            }
            Some(digit) if digit.is_ascii_digit() => {
                while matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                    self.bump();
                }
            }
            _ => return Err(ParseError::Invalid),
        }
        let mut decimal = false;
        if self.peek() == Some('.') {
            decimal = true;
            self.bump();
            if !matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                return Err(ParseError::Invalid);
            }
            while matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                self.bump();
            }
        }
        if matches!(self.peek(), Some('e' | 'E')) {
            decimal = true;
            self.bump();
            if matches!(self.peek(), Some('+' | '-')) {
                self.bump();
            }
            if !matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                return Err(ParseError::Invalid);
            }
            while matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                self.bump();
            }
        }
        let token: String = self.chars[start..self.pos].iter().collect();
        if !decimal {
            if let Ok(whole) = token.parse::<i64>() {
                return Ok(JsonValue::Int(whole));
            }
            // A whole number beyond the machine word is carried with
            // its exact digits, as the Python whole number is.
            return Ok(JsonValue::BigInt(token));
        }
        token
            .parse::<f64>()
            .map(JsonValue::Float)
            .map_err(|_| ParseError::Invalid)
    }
}

/// Parse a document, as the Python reader parses one, refusing a key
/// that stands twice in one object and naming that key, and refusing
/// a document nested deeper than the bound the reader states.
pub fn parse(text: &str) -> Result<JsonValue, ParseError> {
    let mut parser = Parser {
        chars: text.chars().collect(),
        pos: 0,
    };
    let value = parser.parse_value(1)?;
    parser.skip_whitespace();
    if parser.pos != parser.chars.len() {
        return Err(ParseError::Invalid);
    }
    Ok(value)
}
