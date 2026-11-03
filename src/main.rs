//! The tameshi command line shell over the Rust library.
//!
//! The shell carries the one library behaviour this slice gives that
//! takes a filesystem input end to end, the ruling generation of
//! obligation PORT-5, under the rule subcommand. The Python command
//! line remains the full command line of the tool in this slice, as
//! obligation PORT-6 states.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use tameshi::jsonvalue::JsonValue;
use tameshi::reader;
use tameshi::render;
use tameshi::rulings;

struct RuleArgs {
    pack: PathBuf,
    ruling: String,
    expires: Option<String>,
    today: Option<String>,
    out: PathBuf,
}

fn take_value(args: &[String], position: &mut usize, flag: &str) -> Result<String, String> {
    *position += 1;
    args.get(*position)
        .cloned()
        .ok_or_else(|| format!("the {flag} argument needs a value"))
}

fn parse_rule_args(args: &[String]) -> Result<RuleArgs, String> {
    let mut pack: Option<PathBuf> = None;
    let mut ruling: Option<String> = None;
    let mut expires: Option<String> = None;
    let mut today: Option<String> = None;
    let mut out: Option<PathBuf> = None;
    let mut position = 0;
    while position < args.len() {
        match args[position].as_str() {
            "--pack" => pack = Some(PathBuf::from(take_value(args, &mut position, "--pack")?)),
            "--ruling" => ruling = Some(take_value(args, &mut position, "--ruling")?),
            "--expires" => expires = Some(take_value(args, &mut position, "--expires")?),
            "--today" => today = Some(take_value(args, &mut position, "--today")?),
            "--out" => out = Some(PathBuf::from(take_value(args, &mut position, "--out")?)),
            other => return Err(format!("an unknown argument was given ({other})")),
        }
        position += 1;
    }
    Ok(RuleArgs {
        pack: pack.ok_or("the --pack argument is required")?,
        ruling: ruling.ok_or("the --ruling argument is required")?,
        expires,
        today,
        out: out.ok_or("the --out argument is required")?,
    })
}

fn write_text(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|_| {
            format!(
                "the output directory {} could not be created",
                parent.display()
            )
        })?;
    }
    std::fs::write(path, text)
        .map_err(|_| format!("the output file {} could not be written", path.display()))
}

fn run_rule(args: &[String]) -> Result<(), String> {
    let parsed = parse_rule_args(args)?;
    let pack = reader::read_json_file(&parsed.pack, "evidence pack").map_err(|e| e.message)?;
    let expiry = parsed.expires.map(JsonValue::Text);
    let today = parsed.today.map(JsonValue::Text);
    let (record, body) =
        rulings::generate_ruling(&pack, &parsed.ruling, expiry.as_ref(), today.as_ref())
            .map_err(|e| e.message)?;
    let check = pack
        .get("check")
        .and_then(|item| item.as_text())
        .unwrap_or("");
    let slug = rulings::ruling_slug(check);
    write_text(
        &parsed.out.join(format!("ruling-{slug}.json")),
        &render::render_json(&record),
    )?;
    write_text(&parsed.out.join(format!("ruling-{slug}.md")), &body)?;
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let outcome = match args.first().map(|arg| arg.as_str()) {
        Some("rule") => run_rule(&args[1..]),
        _ => Err("usage: tameshi rule --pack PACK --ruling WORD [--expires DATE] [--today DATE] --out DIR".to_string()),
    };
    match outcome {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}
