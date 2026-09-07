use super::*;
use pretty_assertions::assert_eq;

#[test]
fn scope_context_counts_xml_escaping_and_rejects_control_paths() -> Result<()> {
    assert_eq!(
        xml_bytes("/mnt/c/Program Files/O'Reilly<&>\"é")?,
        "/mnt/c/Program Files/O&apos;Reilly&lt;&amp;&gt;&quot;é".len()
    );
    assert!(xml_bytes("/tmp/line\nbreak").is_err());
    Ok(())
}
