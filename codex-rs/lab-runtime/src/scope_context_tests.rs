use super::*;

#[test]
fn scope_context_accepts_xml_characters_and_rejects_control_paths() -> Result<()> {
    validate_path("/mnt/c/Program Files/O'Reilly<&>\"é")?;
    assert!(validate_path("/tmp/line\nbreak").is_err());
    Ok(())
}
