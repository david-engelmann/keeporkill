//! Check names read as file name slugs, the reading the report
//! module gives a check name when it writes a pack or a ruling out.

/// Slugify a check name the way the Python reading slugifies it. The
/// name is lowered, every run of characters outside the plain letters
/// and digits becomes one hyphen, the hyphens at the edges are
/// stripped, the slug is cut at forty eight characters and stripped
/// of a trailing hyphen the cut may leave, and a name with nothing
/// left in it reads as the word check.
pub fn slugify_check(check: &str) -> String {
    let lowered: String = check.chars().flat_map(|c| c.to_lowercase()).collect();
    let mut raw = String::new();
    let mut in_separator_run = false;
    for ch in lowered.chars() {
        if ch.is_ascii_lowercase() || ch.is_ascii_digit() {
            raw.push(ch);
            in_separator_run = false;
        } else if !in_separator_run {
            raw.push('-');
            in_separator_run = true;
        }
    }
    let stripped = raw.trim_matches('-');
    let base = if stripped.is_empty() {
        "check".to_string()
    } else {
        stripped.to_string()
    };
    let truncated: String = base.chars().take(48).collect();
    let cut = truncated.trim_end_matches('-');
    if cut.is_empty() {
        "check".to_string()
    } else {
        cut.to_string()
    }
}
